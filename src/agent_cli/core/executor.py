"""Executor — 执行层。

在 Agent Loop 的工具执行阶段提供额外服务：
  - 权限检查（委派给 PermissionEngine）
  - 执行结果格式化
  - 错误处理与重试
"""

from __future__ import annotations

import logging
from typing import Any

from agent_cli.permissions.engine import PermissionEngine
from agent_cli.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class Executor:
    """工具执行器。

    在 Agent Loop 与 ToolRegistry 之间提供一层服务：
    1. 权限检查
    2. 执行调度
    3. 异常处理
    """

    def __init__(self, registry: ToolRegistry, permissions: PermissionEngine | None = None):
        self.registry = registry
        self.permissions = permissions or PermissionEngine()

    def execute(self, name: str, **kwargs: Any) -> dict:
        """执行工具（带权限检查和错误处理）。

        Args:
            name: 工具名。
            **kwargs: 工具参数。

        Returns:
            执行结果字典，始终包含 'success' 字段。
        """
        # 1. 检查工具是否存在
        tool = self.registry.get(name)
        if tool is None:
            return {"success": False, "error": f"工具 '{name}' 不存在"}

        # 2. 权限检查
        spec = tool.spec()
        decision = self.permissions.check(name, spec.safety.value)
        if decision == "deny":
            return {"success": False, "error": f"权限拒绝: 操作 '{name}' 被禁止"}
        # ask 决策留给上层（CLI/UI）处理

        # 3. 执行
        try:
            result = self.registry.execute(name, **kwargs)
            if isinstance(result, dict):
                result.setdefault("success", True)
            else:
                result = {"success": True, "result": result}
            return result
        except Exception as e:
            logger.error("工具执行异常: %s — %s", name, e)
            return {"success": False, "error": str(e)}
