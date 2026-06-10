"""Agent 工具 — 子 Agent 调用。

允许 Agent 在任务中派生新的子 Agent 执行独立任务。
子 Agent 拥有独立的消息列表，但继承父 Agent 的工具集。
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseTool, SafetyLevel, ToolSpec

logger = logging.getLogger(__name__)


class AgentTool(BaseTool):
    """子 Agent 调用工具。

    在 Phase 1 中作为占位实现，返回说明信息。
    Phase 3 实现 SubagentManager 后将注入真正实现。
    """

    def __init__(self, subagent_manager: Any | None = None):
        self._manager = subagent_manager

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

    def execute(self, task: str, context: str | None = None, **kwargs: Any) -> dict:
        if self._manager is None:
            return {
                "result": "[占位] 子 Agent 系统将在 Phase 3 实现。",
                "task": task,
                "status": "not_implemented",
            }
        try:
            result = self._manager.spawn(task, context={"text": context} if context else None)
            return {"result": str(result), "task": task, "status": "completed"}
        except Exception as e:
            logger.error("子 Agent 执行失败: %s — %s", task, e)
            return {"result": f"执行失败: {e}", "task": task, "status": "error"}
