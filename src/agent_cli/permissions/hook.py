"""Permission Hook — 权限引擎与 Hook 系统的集成。

将 PermissionEngine 注册为 PRE_TOOL hook，在实际工具执行前
检查权限决策，实现四级权限的完整闭环。

Usage:
    hook = PermissionHook(engine)
    hooks.on(PRE_TOOL, hook.check_tool)
"""

from __future__ import annotations

import logging
from typing import Any

from agent_cli.hooks.manager import HookManager
from agent_cli.permissions.engine import PermissionEngine
from agent_cli.tools.base import SafetyLevel

logger = logging.getLogger(__name__)


class PermissionHook:
    """权限 Hook — 集成 PermissionEngine 到 AgentLoop。

    注册到 PRE_TOOL 事件点，在工具执行前检查权限。
    返回的 decision 可以被 Hook 链中的后续处理器消费。

    Usage:
        engine = PermissionEngine(rules_file=".agent/permissions.json")
        perm_hook = PermissionHook(engine)
        hooks.on(PRE_TOOL, perm_hook.check_tool)
    """

    def __init__(self, engine: PermissionEngine | None = None):
        self._engine = engine or PermissionEngine()
        self._check_count = 0
        self._denied_count = 0
        self._asked_count = 0

    @property
    def engine(self) -> PermissionEngine:
        return self._engine

    def check_tool(self, tool_call: Any) -> str | None:
        """PRE_TOOL handler: 检查工具调用的权限。

        Args:
            tool_call: 工具调用对象（须有 .name 属性）。

        Returns:
            决策字符串，或 None（允许执行）。
        """
        tool_name = getattr(tool_call, "name", str(tool_call))
        self._check_count += 1

        # 从 ToolRegistry 获取安全等级
        safety = self._get_tool_safety(tool_name)

        decision = self._engine.check(tool_name, safety)
        logger.debug("权限检查 [%s]: %s → %s", tool_name, safety, decision)

        if decision == "deny":
            self._denied_count += 1
            msg = f"❌ 权限拒绝: 工具 '{tool_name}' 已被禁止使用。"
            logger.warning(msg)
            return msg

        if decision == "always_ask":
            self._asked_count += 1
            msg = f"❓ 需要确认: 工具 '{tool_name}' 需要用户确认才能使用。"
            logger.info(msg)
            return msg

        if decision == "ask":
            self._asked_count += 1
            # ask 是温和的询问，不强制阻止
            logger.info("权限询问 [%s]: 默认放行", tool_name)
            return None

        # allow
        return None

    def _get_tool_safety(self, tool_name: str) -> str:
        """获取工具的安全等级描述。

        尝试遍历已知的 SafetyLevel 来做简单判断。
        如果无法获取，默认返回 "safe"。
        """
        try:
            # 根据工具名推断安全等级
            dangerous_tools = {"bash", "write", "edit"}
            always_ask_tools = {"web_fetch", "agent"}
            safe_tools = {"read", "glob", "grep"}

            if tool_name in dangerous_tools:
                return SafetyLevel.SENSITIVE.value
            if tool_name in always_ask_tools:
                return SafetyLevel.ALWAYS_ASK.value
            if tool_name in safe_tools:
                return SafetyLevel.SAFE.value
        except Exception:
            pass

        return SafetyLevel.SAFE.value

    def get_stats(self) -> dict:
        """获取权限检查统计。"""
        return {
            "total_checks": self._check_count,
            "denied": self._denied_count,
            "asked": self._asked_count,
            "rules": self._engine.get_rules(),
        }


def create_permission_hook(
    rules_file: str = ".agent/permissions.json",
) -> tuple[PermissionHook, HookManager]:
    """便捷工厂：创建权限引擎 + Hook 的一体化配置。

    Args:
        rules_file: 权限规则文件路径。

    Returns:
        (PermissionHook, HookManager) 元组。
    """
    engine = PermissionEngine(rules_file=rules_file)
    perm_hook = PermissionHook(engine)

    hooks = HookManager()

    from agent_cli.hooks.manager import PRE_TOOL

    hooks.on(PRE_TOOL, perm_hook.check_tool)
    logger.info("权限 Hook 已注册，规则文件: %s", rules_file)

    return perm_hook, hooks
