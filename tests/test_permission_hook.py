"""Permission Hook 单元测试。

测试 PermissionHook 与 AgentLoop 的集成层。
"""

from __future__ import annotations

from agent_cli.permissions.engine import PermissionEngine
from agent_cli.permissions.hook import PermissionHook, create_permission_hook
from agent_cli.tools.base import SafetyLevel


class _FakeToolCall:
    """模拟 Agent Loop 传入的工具调用对象。"""

    def __init__(self, name: str):
        self.name = name


class TestPermissionHook:
    """PermissionHook 核心功能测试。"""

    # ── 初始化 ─────────────────────────────────────────────────

    def test_init_default_engine(self):
        """默认构造使用 PermissionEngine 实例。"""
        hook = PermissionHook()
        assert isinstance(hook.engine, PermissionEngine)
        assert hook.engine is not None

    def test_init_custom_engine(self):
        """可传入自定义 PermissionEngine。"""
        engine = PermissionEngine()
        hook = PermissionHook(engine=engine)
        assert hook.engine is engine

    def test_init_zero_counts(self):
        """初始化后检查计数器为 0。"""
        hook = PermissionHook()
        stats = hook.get_stats()
        assert stats["total_checks"] == 0
        assert stats["denied"] == 0
        assert stats["asked"] == 0

    # ── check_tool 返回值的语义 ──────────────────────────────

    def test_check_tool_allow_returns_none(self):
        """allow 决策 → check_tool 返回 None。"""
        engine = PermissionEngine()
        engine.allow("bash")
        hook = PermissionHook(engine=engine)
        result = hook.check_tool(_FakeToolCall("bash"))
        assert result is None

    def test_check_tool_deny_returns_string(self):
        """deny 决策 → check_tool 返回错误消息字符串。"""
        engine = PermissionEngine()
        engine.deny("bash")
        hook = PermissionHook(engine=engine)
        result = hook.check_tool(_FakeToolCall("bash"))
        assert isinstance(result, str)
        assert "权限拒绝" in result
        assert "bash" in result

    def test_check_tool_always_ask_returns_string(self):
        """always_ask 决策 → check_tool 返回提示字符串。"""
        engine = PermissionEngine()
        engine.always_ask("web_fetch")
        hook = PermissionHook(engine=engine)
        result = hook.check_tool(_FakeToolCall("web_fetch"))
        assert isinstance(result, str)
        assert "需要确认" in result

    def test_check_tool_ask_returns_none(self):
        """ask 决策 → check_tool 返回 None（温和询问，默认放行）。"""
        hook = PermissionHook()
        # 敏感工具默认就是 ask
        result = hook.check_tool(_FakeToolCall("bash"))
        assert result is None

    # ── _get_tool_safety ─────────────────────────────────────

    def test_safety_for_dangerous_tools(self):
        """bash/write/edit 为 SENSITIVE 等级。"""
        hook = PermissionHook()
        assert hook._get_tool_safety("bash") == SafetyLevel.SENSITIVE.value
        assert hook._get_tool_safety("write") == SafetyLevel.SENSITIVE.value
        assert hook._get_tool_safety("edit") == SafetyLevel.SENSITIVE.value

    def test_safety_for_always_ask_tools(self):
        """web_fetch/agent 为 ALWAYS_ASK 等级。"""
        hook = PermissionHook()
        assert hook._get_tool_safety("web_fetch") == SafetyLevel.ALWAYS_ASK.value
        assert hook._get_tool_safety("agent") == SafetyLevel.ALWAYS_ASK.value

    def test_safety_for_safe_tools(self):
        """read/glob/grep 为 SAFE 等级。"""
        hook = PermissionHook()
        assert hook._get_tool_safety("read") == SafetyLevel.SAFE.value
        assert hook._get_tool_safety("glob") == SafetyLevel.SAFE.value
        assert hook._get_tool_safety("grep") == SafetyLevel.SAFE.value

    def test_safety_unknown_tool_defaults_safe(self):
        """未知工具默认返回 SAFE。"""
        hook = PermissionHook()
        assert hook._get_tool_safety("unknown_tool") == SafetyLevel.SAFE.value

    # ── check_tool 与 safety 集成测试 ────────────────────────

    def test_safe_tool_allowed_by_default(self):
        """安全工具（read）默认 allow → check_tool 返回 None。"""
        hook = PermissionHook()
        result = hook.check_tool(_FakeToolCall("read"))
        assert result is None

    def test_sensitive_tool_asked_by_default(self):
        """敏感工具（bash）默认 ask → check_tool 返回 None。"""
        hook = PermissionHook()
        result = hook.check_tool(_FakeToolCall("bash"))
        assert result is None

    def test_always_ask_tool_asked_by_default(self):
        """always_ask 工具（web_fetch）默认 ask → check_tool 返回 None。"""
        hook = PermissionHook()
        result = hook.check_tool(_FakeToolCall("web_fetch"))
        assert result is None

    def test_denied_tool_override_safety(self):
        """自定义 deny 覆盖安全等级。"""
        engine = PermissionEngine()
        engine.deny("read")  # 即使是 safe 等级
        hook = PermissionHook(engine=engine)
        result = hook.check_tool(_FakeToolCall("read"))
        assert isinstance(result, str)
        assert "权限拒绝" in result

    def test_allowed_tool_override_safety(self):
        """自定义 allow 覆盖安全等级。"""
        engine = PermissionEngine()
        engine.allow("web_fetch")  # 即使是 always_ask 等级
        hook = PermissionHook(engine=engine)
        result = hook.check_tool(_FakeToolCall("web_fetch"))
        assert result is None

    # ── tool_call 非标准对象 ─────────────────────────────────

    def test_check_tool_with_string(self):
        """当 tool_call 没有 .name 属性时，使用 str() 兜底。"""
        hook = PermissionHook()
        # 传入字符串而非对象 → 不会崩溃
        result = hook.check_tool("unknown_tool_str")
        # 未知工具默认 safe → allow → None
        assert result is None

    def test_check_tool_with_dict(self):
        """当 tool_call 是 dict 时，使用 str() 兜底。"""
        hook = PermissionHook()
        result = hook.check_tool({"type": "tool_call"})
        assert result is None

    # ── 统计计数 ─────────────────────────────────────────────

    def test_stats_count_checks(self):
        """每次 check_tool 调用增加 total_checks。"""
        hook = PermissionHook()
        assert hook.get_stats()["total_checks"] == 0
        hook.check_tool(_FakeToolCall("read"))
        assert hook.get_stats()["total_checks"] == 1
        hook.check_tool(_FakeToolCall("bash"))
        assert hook.get_stats()["total_checks"] == 2

    def test_stats_count_denied(self):
        """deny 决策增加 denied 计数。"""
        engine = PermissionEngine()
        engine.deny("bash")
        hook = PermissionHook(engine=engine)
        hook.check_tool(_FakeToolCall("bash"))
        stats = hook.get_stats()
        assert stats["denied"] == 1
        assert stats["asked"] == 0

    def test_stats_count_asked(self):
        """always_ask 决策增加 asked 计数。"""
        engine = PermissionEngine()
        engine.always_ask("web_fetch")
        hook = PermissionHook(engine=engine)
        hook.check_tool(_FakeToolCall("web_fetch"))
        stats = hook.get_stats()
        assert stats["asked"] == 1

    def test_stats_includes_rules(self):
        """get_stats 包含来自 engine 的规则信息。"""
        engine = PermissionEngine()
        engine.allow("bash")
        engine.deny("write")
        hook = PermissionHook(engine=engine)
        stats = hook.get_stats()
        assert "rules" in stats
        assert stats["rules"]["bash"] == "allow"
        assert stats["rules"]["write"] == "deny"

    # ── check_tool 调用链 ──────────────────────────────────

    def test_multiple_checks_accumulate(self):
        """多次调用 check_tool 正确累积统计。"""
        engine = PermissionEngine()
        engine.deny("bash")
        hook = PermissionHook(engine=engine)
        hook.check_tool(_FakeToolCall("read"))  # allow
        hook.check_tool(_FakeToolCall("bash"))  # deny
        hook.check_tool(_FakeToolCall("write"))  # ask
        hook.check_tool(_FakeToolCall("web_fetch"))  # ask
        stats = hook.get_stats()
        assert stats["total_checks"] == 4
        assert stats["denied"] == 1
        assert stats["asked"] == 2  # write 的 ask + web_fetch 的 ask


class TestCreatePermissionHook:
    """create_permission_hook 工厂函数测试。"""

    def test_returns_hook_and_hookmanager(self):
        """工厂函数返回 (PermissionHook, HookManager) 元组。"""
        perm_hook, hooks = create_permission_hook()
        from agent_cli.hooks.manager import HookManager

        assert isinstance(perm_hook, PermissionHook)
        assert isinstance(hooks, HookManager)

    def test_hook_has_rules_file(self):
        """默认 hook 包含来自新 engine 的规则。"""
        perm_hook, _hooks = create_permission_hook()
        assert perm_hook.engine is not None
        assert perm_hook.get_stats()["total_checks"] == 0

    def test_hook_engine_check_works(self):
        """工厂创建的 hook 可以正常做权限检查。"""
        perm_hook, _hooks = create_permission_hook()
        result = perm_hook.check_tool(_FakeToolCall("read"))
        assert result is None  # safe 工具默认 allow
