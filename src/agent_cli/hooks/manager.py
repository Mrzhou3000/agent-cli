"""HookManager — 钩子系统。

设计哲学（来源：learn-claude-code）：
  Hook 机制使得所有扩展都"挂在循环上"而非"写进循环里"。
  新增功能 = 注册新 handler，无需修改循环代码。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# Event types
PRE_LOOP = "pre_loop"
PRE_TOOL = "pre_tool"
POST_TOOL = "post_tool"
POST_LOOP = "post_loop"


class HookManager:
    """钩子管理器。

    4 个标准 Hook 点：
      pre_loop(messages) → messages       # 循环开始前，可修改消息列表
      pre_tool(block)    → block          # 工具执行前，可修改调用参数
      post_tool(block, result) → None     # 工具执行后
      post_loop(response) → response      # 循环结束后（文本回复）

    Usage:
        hooks = HookManager()
        hooks.on("pre_tool", my_handler)
        hooks.trigger("pre_tool", block)
    """

    VALID_EVENTS = {PRE_LOOP, PRE_TOOL, POST_TOOL, POST_LOOP}

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {e: [] for e in self.VALID_EVENTS}

    def on(self, event: str, handler: Callable) -> None:
        """注册 Hook 处理器。

        Args:
            event: 事件名（PRE_LOOP, PRE_TOOL, POST_TOOL, POST_LOOP）。
            handler: 回调函数。

        Raises:
            ValueError: 事件名无效。
        """
        if event not in self.VALID_EVENTS:
            raise ValueError(f"无效事件: '{event}'。有效事件: {self.VALID_EVENTS}")
        self._handlers[event].append(handler)
        logger.debug("注册 Hook: %s → %s", event, handler.__name__)

    def off(self, event: str, handler: Callable | None = None) -> None:
        """移除 Hook 处理器。

        Args:
            event: 事件名。
            handler: 要移除的处理器。为 None 时移除该事件所有处理器。
        """
        if event in self.VALID_EVENTS:
            if handler:
                self._handlers[event] = [h for h in self._handlers[event] if h != handler]
            else:
                self._handlers[event].clear()

    def trigger(self, event: str, *args: Any, **kwargs: Any) -> list[Any]:
        """触发 Hook 事件。

        Args:
            event: 事件名。
            *args, **kwargs: 传递给 handler 的参数。

        Returns:
            所有 handler 的返回值列表。
        """
        if event not in self.VALID_EVENTS:
            logger.warning("触发未知事件: %s", event)
            return []

        results = []
        for handler in self._handlers[event]:
            try:
                result = handler(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error("Hook 处理器异常 [%s → %s]: %s", event, handler.__name__, e)
        return results

    @property
    def registered_events(self) -> dict[str, list[str]]:
        """获取已注册的事件及其处理器列表。"""
        return {e: [h.__name__ for h in handlers] for e, handlers in self._handlers.items()}
