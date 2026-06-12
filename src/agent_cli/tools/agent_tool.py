"""Agent 工具 — 子 Agent 调用。

允许 Agent 在任务中派生新的子 Agent 执行独立任务。
子 Agent 拥有独立的消息列表，但继承父 Agent 的工具集。
"""

from __future__ import annotations

import logging
from typing import Any

from agent_cli.core.loop import AgentLoop
from agent_cli.subagent.manager import SubagentManager

from .base import BaseTool, SafetyLevel, ToolSpec

logger = logging.getLogger(__name__)


class AgentTool(BaseTool):
    """子 Agent 调用工具。

    在 Agent Loop 中创建一个独立的子 Agent 来执行指定任务。
    子 Agent 拥有独立的上下文和消息列表，但共享当前工具集。
    适用于需要并行探索、独立文件操作或复杂任务拆解的场景。

    使用方式:
        创建时传入 provider 和 tools 引用，execute() 时自动创建
        临时 AgentLoop + SubagentManager 来执行子任务。
    """

    def __init__(
        self,
        provider: Any | None = None,
        tools: Any | None = None,
        max_iterations: int = 10,
    ):
        """初始化 Agent 工具。

        Args:
            provider: IModelProvider 实例。为 None 时 execute 返回占位消息。
            tools: ToolRegistry 实例（引用）。
            max_iterations: 子 Agent 最大循环迭代次数。
        """
        self._provider = provider
        self._tools = tools
        self._max_iterations = max_iterations

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="agent",
            description="创建一个子 Agent 来独立执行指定任务。"
            "子 Agent 拥有独立的上下文，但共享当前工具集。"
            "适用于需要并行探索、独立文件操作或复杂任务拆解的场景。",
            parameters={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "子 Agent 需要执行的任务描述",
                    },
                    "context": {
                        "type": "string",
                        "description": "传递给子 Agent 的上下文信息（可选）",
                    },
                },
                "required": ["task"],
            },
            handler=self.execute,
            safety=SafetyLevel.SENSITIVE,
        )

    def execute(  # type: ignore[override]
        self, task: str, context: str | None = None, **kwargs: Any
    ) -> dict:
        """执行子 Agent 任务。

        流程:
          1. 检查 provider 是否可用
          2. 创建临时的 AgentLoop + SubagentManager
          3. 派生子 Agent 执行任务
          4. 返回结构化结果

        Args:
            task: 子任务描述。
            context: 可选的上下文信息。

        Returns:
            {"result": str, "task": str, "status": str}
        """
        if self._provider is None or self._tools is None:
            return {
                "result": "[占位] 子 Agent 功能需要在启动时指定模型 Provider。"
                "请通过 --provider 参数指定模型（如 --provider anthropic）。",
                "task": task,
                "status": "unavailable",
            }

        try:
            # 创建临时子 Agent 运行时
            sub_loop = AgentLoop(
                provider=self._provider,
                tools=self._tools,
                max_iterations=self._max_iterations,
            )
            mgr = SubagentManager(sub_loop, max_iterations=self._max_iterations)
            result = mgr.spawn(task, context={"text": context} if context else None)

            logger.info(
                "子 Agent 完成: task='%s' success=%s output_len=%d",
                task[:60],
                result.success,
                len(result.output),
            )

            return {
                "result": result.output,
                "task": task,
                "status": "completed" if result.success else "error",
            }

        except Exception as e:
            logger.error("子 Agent 执行失败: %s — %s", task[:60], e)
            return {
                "result": f"执行失败: {e}",
                "task": task,
                "status": "error",
            }
