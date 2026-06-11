"""HookManager 单元测试。"""

from __future__ import annotations

import pytest

from agent_cli.hooks.manager import (
    POST_LOOP,
    POST_TOOL,
    PRE_LOOP,
    PRE_TOOL,
    HookManager,
)


class TestHookManager:
    """HookManager 核心功能测试。"""

    @pytest.fixture
    def hooks(self) -> HookManager:
        return HookManager()

    def test_register_and_trigger(self, hooks: HookManager):
        """测试注册和触发。"""
        results = []
        hooks.on(PRE_LOOP, lambda msgs: results.append("pre_loop"))
        hooks.trigger(PRE_LOOP, ["msg"])
        assert results == ["pre_loop"]

    def test_multiple_handlers(self, hooks: HookManager):
        """测试多个处理器。"""
        results = []
        hooks.on(PRE_TOOL, lambda x: results.append("h1"))
        hooks.on(PRE_TOOL, lambda x: results.append("h2"))
        hooks.trigger(PRE_TOOL, "test")
        assert results == ["h1", "h2"]

    def test_invalid_event(self, hooks: HookManager):
        """测试无效事件。"""
        with pytest.raises(ValueError, match="无效事件"):
            hooks.on("invalid_event", lambda: None)

    def test_off_handler(self, hooks: HookManager):
        """测试移除处理器。"""
        results = []

        def handler(x):
            results.append("called")

        hooks.on(PRE_LOOP, handler)
        hooks.off(PRE_LOOP, handler)
        hooks.trigger(PRE_LOOP, [])
        assert results == []

    def test_off_all(self, hooks: HookManager):
        """测试移除所有处理器。"""
        hooks.on(PRE_LOOP, lambda x: 1)
        hooks.on(PRE_LOOP, lambda x: 2)
        hooks.off(PRE_LOOP)
        assert hooks.registered_events.get(PRE_LOOP) == []

    def test_trigger_unknown_event(self, hooks: HookManager):
        """测试触发未知事件不报错。"""
        result = hooks.trigger("unknown", "test")
        assert result == []

    def test_handler_exception_isolation(self, hooks: HookManager):
        """测试 handler 异常不影响其他 handler。"""
        results = []
        hooks.on(PRE_LOOP, lambda msgs: results.append("ok"))
        hooks.on(PRE_LOOP, lambda msgs: 1 / 0)  # 会抛出 ZeroDivisionError
        hooks.on(PRE_LOOP, lambda msgs: results.append("also_ok"))
        hooks.trigger(PRE_LOOP, [])
        assert results == ["ok", "also_ok"]

    def test_trigger_passes_args(self, hooks: HookManager):
        """测试触发时传递参数。"""
        captured = []
        hooks.on(POST_TOOL, lambda block, result: captured.append((block, result)))
        hooks.trigger(POST_TOOL, "block_data", {"success": True})
        assert captured == [("block_data", {"success": True})]

    def test_registered_events(self, hooks: HookManager):
        """测试已注册事件列表。"""
        hooks.on(PRE_LOOP, lambda x: None)
        hooks.on(POST_LOOP, lambda x: None)
        events = hooks.registered_events
        assert PRE_LOOP in events
        assert POST_LOOP in events
