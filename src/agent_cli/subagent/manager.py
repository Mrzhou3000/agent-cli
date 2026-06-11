"""SubagentManager — 子Agent管理系统。

设计依据（规范 4.7）：
  - Agent → 派生子Agent（独立上下文）→ 执行 → 结果回填
  - 共享父Agent工具集，独立消息列表
  - 用于复杂任务拆解、并行探索、独立文件操作

子Agent = 独立消息列表的 Agent Loop 实例。
继承父 Agent 的工具集，但拥有完全独立的上下文。

使用示例:
    sub = SubagentManager(loop_instance)
    result = sub.spawn("搜索项目中所有的 TODO 注释")
    print(result.output)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from agent_cli.core.loop import AgentLoop
from agent_cli.core.provider import IModelProvider

logger = logging.getLogger(__name__)


@dataclass
class SubagentResult:
    """子Agent执行结果。

    Attributes:
        task: 子任务描述。
        output: 文本输出。
        error: 错误信息（如有）。
        messages: 完整消息列表。
        tool_calls: 工具调用次数。
        iterations: 循环迭代次数。
    """

    task: str
    output: str = ""
    error: str = ""
    messages: list[dict] = field(default_factory=list)
    tool_calls: int = 0
    iterations: int = 0

    @property
    def success(self) -> bool:
        """是否执行成功。"""
        return not bool(self.error)


class SubagentManager:
    """子Agent管理器。

    从父 Agent Loop 派生独立子任务。
    子Agent 共享父 Agent 的工具集，但拥有独立上下文。

    特性:
      - 独立消息列表（从父上下文摘要继承）
      - 共享工具集
      - 隔离执行错误
      - 结构化结果回填

    Usage:
        sub_mgr = SubagentManager(parent_loop)
        result = sub_mgr.spawn("搜索 TODO", context={"focus": "代码"})
    """

    def __init__(
        self,
        parent: AgentLoop,
        max_iterations: int = 10,
    ):
        """初始化子Agent管理器。

        Args:
            parent: 父 AgentLoop 实例。
            max_iterations: 子Agent 最大迭代次数。
        """
        self._parent = parent
        self._max_iterations = max_iterations

    def spawn(
        self,
        task: str,
        context: dict | None = None,
        provider: IModelProvider | None = None,
    ) -> SubagentResult:
        """派发一个子Agent执行任务。

        流程:
          1. 从 parent 摘要生成上下文
          2. 创建独立消息列表
          3. 执行子 Agent Loop
          4. 返回结构化结果

        Args:
            task: 子任务描述。
            context: 额外上下文信息（可选）。
            provider: 可选的独立 Provider（默认继承父 Agent）。

        Returns:
            SubagentResult 实例。
        """
        logger.info("子Agent 启动: task='%s'", task[:100])
        result = SubagentResult(task=task)

        # 1. 构建子 Agent 消息列表
        messages = self._build_context(task, context)

        # 2. 创建子 Agent Loop（继承父级 hooks，排除 metrics 避免重复计数）
        sub_hooks = self._build_sub_hooks()
        sub_loop = AgentLoop(
            provider=provider or self._parent.provider,
            tools=self._parent.tools,
            hooks=sub_hooks,
            session_store=None,  # 子Agent 不直接写会话
            memory=None,
            compact=None,
            max_iterations=self._max_iterations,
        )

        # 3. 执行
        try:
            response = sub_loop.run(prompt=task, messages=messages)
            result.output = response.text
            result.iterations = sub_loop._iteration
            result.tool_calls = len(response.tool_calls)
            result.messages = getattr(sub_loop, "_session_messages", [])
            logger.info(
                "子Agent 完成: %d 次迭代, %d 个工具调用",
                result.iterations,
                result.tool_calls,
            )
        except Exception as e:
            error_msg = str(e)
            result.error = error_msg
            logger.error("子Agent 异常: %s", error_msg)

        return result

    def spawn_batch(
        self,
        tasks: list[str],
        context: dict | None = None,
    ) -> list[SubagentResult]:
        """批量执行多个子任务。

        注意: 当前为顺序执行。并行执行将在 Phase 4 实现。

        Args:
            tasks: 任务描述列表。
            context: 共享上下文信息。

        Returns:
            SubagentResult 列表。
        """
        results: list[SubagentResult] = []
        total = len(tasks)

        for i, task in enumerate(tasks, 1):
            logger.info("子Agent [%d/%d]: %s", i, total, task[:80])
            result = self.spawn(task, context=context)
            results.append(result)

        return results

    def _build_context(self, task: str, context: dict | None = None) -> list[dict]:
        """构建子Agent的上下文消息。

        从父 Agent 的 _session_messages 提取摘要，
        再加上本次任务的上下文信息。

        Args:
            task: 任务描述。
            context: 额外上下文。

        Returns:
            初始消息列表。
        """
        messages: list[dict] = []

        # 从父 Agent 继承上下文摘要
        parent_msgs = getattr(self._parent, "_session_messages", [])
        if parent_msgs:
            summary = self._summarize_messages(parent_msgs)
            if summary:
                messages.append({"role": "system", "content": f"[父Agent上下文]\n{summary}"})

        # 添加额外上下文
        if context:
            ctx_lines = []
            for key, value in context.items():
                ctx_lines.append(f"{key}: {value}")
            if ctx_lines:
                messages.append(
                    {"role": "system", "content": "[额外上下文]\n" + "\n".join(ctx_lines)}
                )

        return messages

    def _summarize_messages(self, messages: list[dict], max_items: int = 10) -> str:
        """从父 Agent 消息中提取摘要。

        Args:
            messages: 父 Agent 的消息列表。
            max_items: 最多提取的消息数。

        Returns:
            摘要文本。
        """
        recent = messages[-max_items:]
        lines: list[str] = []

        for msg in recent:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                text = content if isinstance(content, str) else "[工具结果]"
                lines.append(f"用户: {text[:200]}")

            elif role == "assistant":
                if isinstance(content, str):
                    lines.append(f"助手: {content[:200]}")
                elif isinstance(content, list):
                    parts = [
                        b.get("text", "")
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    text = " ".join(parts)
                    lines.append(f"助手: {text[:200] if text else '[工具调用]'}")

        return "\n".join(lines[-max_items:])

    def _build_sub_hooks(self):
        """构建子 Agent 的 HookManager，继承安全/权限 hooks，排除 metrics。

        父级 hooks 中通常包含 metrics 收集 handler（on_pre_loop、on_post_tool、
        on_post_loop），子 Agent 共享这些 handler 会导致工具调用被重复计数。
        本方法复制所有父级 hooks，但跳过 metrics 相关 handler。
        """
        parent_hooks = getattr(self._parent, "hooks", None)
        if parent_hooks is None:
            return None

        from agent_cli.hooks.manager import HookManager

        sub_hooks = HookManager()
        metrics_names = {"on_pre_loop", "on_post_tool", "on_post_loop", "on_pre_tool"}
        for event, handlers in parent_hooks._handlers.items():
            for handler in handlers:
                h_name = getattr(handler, "__name__", "")
                if h_name in metrics_names:
                    continue  # 跳过 metrics 相关的 handler
                sub_hooks.on(event, handler)
        return sub_hooks
