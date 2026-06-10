"""Agent Loop — 核心循环。

设计哲学（来源：learn-claude-code）：
  循环本身极其简单（约 60 行），所有复杂机制"挂在循环上"而非"写进循环里"。
  循环骨架在项目演进中从不改变。

Phase 标记（来源：complete-guide_v2）：
  轻量注释标记，为 Hook 提供清晰的插入点。
"""

from __future__ import annotations

import logging

from agent_cli.compact.pipeline import CompactPipeline
from agent_cli.core.provider import IModelProvider, Response
from agent_cli.hooks.manager import (
    POST_LOOP,
    POST_TOOL,
    PRE_LOOP,
    PRE_TOOL,
    HookManager,
)
from agent_cli.memory.manager import MemoryManager
from agent_cli.session.store import SessionStore
from agent_cli.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentLoop:
    """Agent 核心循环。

    Agent Loop 是系统的中央调度器。它管理：
      1. 模型推理（Provider）
      2. 工具调度（ToolRegistry）
      3. 生命周期钩子（HookManager）
      4. 会话持久化（SessionStore）
      5. 上下文压缩（CompactPipeline）
      6. 三级记忆（MemoryManager）

    扩展方式：注册新的 Hook handler 或注册新的工具。
    无需修改循环代码本身。

    Usage:
        loop = AgentLoop(provider=MockProvider(), tools=ToolRegistry())
        result = loop.run("你好")
    """

    def __init__(
        self,
        provider: IModelProvider,
        tools: ToolRegistry,
        hooks: HookManager | None = None,
        session_store: SessionStore | None = None,
        memory: MemoryManager | None = None,
        compact: CompactPipeline | None = None,
        max_iterations: int = 20,
    ):
        self.provider = provider
        self.tools = tools
        self.hooks = hooks or HookManager()
        self.session_store = session_store
        self.memory = memory
        self.compact = compact
        self.max_iterations = max_iterations
        self._iteration = 0
        self._session_messages: list[dict] = []

    def run(
        self,
        prompt: str,
        messages: list[dict] | None = None,
        session_id: str | None = None,
    ) -> Response:
        """运行 Agent 循环。

        Args:
            prompt: 用户输入（当 messages 为 None 时使用）。
            messages: 初始消息列表（用于会话恢复）。
            session_id: 会话 ID（用于持久化）。

        Returns:
            最终 Response 对象。
        """
        # 初始化消息列表
        if messages is None:
            messages = [{"role": "user", "content": prompt}]
            logger.info("Agent Loop 启动: prompt='%s'", prompt[:100])
        else:
            logger.info("Agent Loop 恢复: %d 条消息", len(messages))

        self._iteration = 0
        final_response: Response | None = None
        self._session_messages = list(messages) if messages else []

        # 记忆上下文注入
        if self.memory and messages:
            ctx = self.memory.build_context(keywords=prompt)
            if ctx:
                messages.insert(0, {"role": "system", "content": f"[记忆上下文]\n{ctx[:1500]}"})
                logger.debug("注入记忆上下文: %d 字符", len(ctx))

        while self._iteration < self.max_iterations:
            self._iteration += 1

            # ── Phase 1: 模型推理 ──────────────────────────────
            # pre_loop hook: 可修改消息列表（如注入系统提示）
            self.hooks.trigger(PRE_LOOP, messages)

            logger.debug("[%d/∞] 模型推理中...", self._iteration)
            response = self.provider.invoke(messages, self.tools.schemas())
            messages.append({"role": "assistant", "content": response.content})

            # ── Phase 2: 判断 ──────────────────────────────────
            if response.stop_reason != "tool_use":
                # 文本回复 → 结束循环
                final_response = response
                logger.info(
                    "[%d/∞] 完成: stop_reason=%s (tokens: %s)",
                    self._iteration,
                    response.stop_reason,
                    f"↑{response.usage.input_tokens}↓{response.usage.output_tokens}"
                    if response.usage.input_tokens
                    else "N/A",
                )
                break

            # ── Phase 3: 工具执行 ──────────────────────────────
            for tool_call in response.tool_calls:
                # pre_tool hook: 可修改或阻止工具调用
                self.hooks.trigger(PRE_TOOL, tool_call)

                try:
                    logger.info(
                        "[%d/∞] 工具调用: %s(%s)",
                        self._iteration,
                        tool_call.name,
                        tool_call.input,
                    )
                    result = self.tools.execute(tool_call.name, **tool_call.input)
                except KeyError as e:
                    result = {"error": f"工具不存在: {e}"}
                    logger.warning("[%d/∞] %s", self._iteration, result["error"])
                except Exception as e:
                    result = {"error": str(e)}
                    logger.error("[%d/∞] 工具异常: %s — %s", self._iteration, tool_call.name, e)

                # post_tool hook
                self.hooks.trigger(POST_TOOL, tool_call, result)

                # 结果追加为 tool_result
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_call.id,
                                "content": result,
                            }
                        ],
                    }
                )

            # ── Phase 4: 会话持久化（每轮） ────────────────────
            if self.session_store and session_id:
                self.session_store.append(session_id, messages[-2:])

            # ── Phase 5: 上下文压缩检测 ────────────────────────
            if self.compact and self.compact.should_compact(messages):
                messages = self.compact.compress(messages)
                logger.info("上下文压缩: %d", len(messages))

        # ── 循环结束 ──────────────────────────────────────────────
        if final_response is None:
            final_response = Response(
                stop_reason="max_tokens",
                content=[{"type": "text", "text": f"达到最大迭代次数 ({self.max_iterations})"}],
                text=f"达到最大迭代次数 ({self.max_iterations})",
            )

        # post_loop hook
        self.hooks.trigger(POST_LOOP, final_response)

        # 最终持久化
        if self.session_store and session_id:
            self.session_store.append(session_id, [messages[-1]])

        return final_response
