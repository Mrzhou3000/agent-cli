"""Permission Engine 单元测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from agent_cli.permissions.engine import PermissionEngine


class TestPermissionEngine:
    """PermissionEngine 核心功能测试。"""

    @pytest.fixture
    def engine(self) -> PermissionEngine:
        return PermissionEngine()

    def test_safe_allowed(self, engine: PermissionEngine):
        """安全操作默认为 allow。"""
        assert engine.check("read", "safe") == "allow"

    def test_sensitive_asks(self, engine: PermissionEngine):
        """敏感操作默认为 ask。"""
        assert engine.check("bash", "sensitive") == "ask"

    def test_dangerous_denied(self, engine: PermissionEngine):
        """危险操作默认为 deny。"""
        assert engine.check("rm", "dangerous") == "deny"

    def test_allow_rule(self, engine: PermissionEngine):
        """测试永久允许。"""
        engine.allow("bash")
        assert engine.check("bash", "sensitive") == "allow"

    def test_deny_rule(self, engine: PermissionEngine):
        """测试永久拒绝。"""
        engine.deny("write")
        assert engine.check("write", "safe") == "deny"

    def test_revoke_rule(self, engine: PermissionEngine):
        """测试撤销规则。"""
        engine.allow("bash")
        engine.revoke("bash")
        # 撤销后恢复默认行为
        assert engine.check("bash", "sensitive") == "ask"

    def test_clear_rules(self, engine: PermissionEngine):
        """测试清除所有规则。"""
        engine.allow("bash")
        engine.allow("read")
        engine.clear()
        assert engine.check("bash", "sensitive") == "ask"
        assert engine.check("read", "safe") == "allow"

    def test_persistence(self):
        """测试规则持久化。"""
        with tempfile.TemporaryDirectory() as td:
            rules_file = str(Path(td) / "permissions.json")
            # 创建引擎并添加规则
            e1 = PermissionEngine(rules_file=rules_file)
            e1.allow("bash")
            # 新引擎应加载已有规则
            e2 = PermissionEngine(rules_file=rules_file)
            assert e2.check("bash", "sensitive") == "allow"

    def test_always_ask(self, engine: PermissionEngine):
        """测试总是询问。"""
        engine.always_ask("web_fetch")
        assert engine.check("web_fetch", "always_ask") == "always_ask"

    def test_set_rule_allow(self, engine: PermissionEngine):
        """测试 set_rule 设置 allow。"""
        engine.set_rule("bash", "allow")
        assert engine.check("bash", "sensitive") == "allow"

    def test_set_rule_deny(self, engine: PermissionEngine):
        """测试 set_rule 设置 deny。"""
        engine.set_rule("read", "deny")
        assert engine.check("read", "safe") == "deny"

    def test_set_rule_always_ask(self, engine: PermissionEngine):
        """测试 set_rule 设置 always_ask。"""
        engine.set_rule("web_fetch", "always_ask")
        assert engine.check("web_fetch", "always_ask") == "always_ask"

    def test_set_rule_ask_revokes(self, engine: PermissionEngine):
        """测试 set_rule 设置 ask 会撤销规则。"""
        engine.set_rule("bash", "allow")
        assert "bash" in engine.get_rules()
        engine.set_rule("bash", "ask")
        assert "bash" not in engine.get_rules()

    def test_get_rules(self, engine: PermissionEngine):
        """测试获取规则。"""
        engine.allow("bash")
        engine.deny("write")
        rules = engine.get_rules()
        assert rules["bash"] == "allow"
        assert rules["write"] == "deny"
        assert len(rules) == 2

    def test_describe_empty(self, engine: PermissionEngine):
        """测试空规则描述。"""
        desc = engine.describe()
        assert "当前无自定义权限规则" in desc

    def test_describe_with_rules(self, engine: PermissionEngine):
        """测试有规则时的描述。"""
        engine.allow("bash")
        engine.deny("write")
        desc = engine.describe()
        assert "bash" in desc
        assert "write" in desc
        assert "allow" in desc or "✅" in desc
        assert "deny" in desc or "❌" in desc

    def test_get_stats_empty(self, engine: PermissionEngine):
        """测试空统计。"""
        stats = engine.get_stats()
        assert stats["total_rules"] == 0
        assert stats["decisions"]["allow"] == 0

    def test_get_stats_with_rules(self, engine: PermissionEngine):
        """测试有规则时的统计。"""
        engine.allow("bash")
        engine.deny("write")
        engine.always_ask("web_fetch")
        stats = engine.get_stats()
        assert stats["total_rules"] == 3
        assert stats["decisions"]["allow"] == 1
        assert stats["decisions"]["deny"] == 1
        assert stats["decisions"]["always_ask"] == 1

    def test_safety_map_always_ask(self, engine: PermissionEngine):
        """测试 always_ask 安全等级默认行为。"""
        # 没有自定义规则时，always_ask 默认返回 ask
        decision = engine.check("web_fetch", "always_ask")
        assert decision == "ask"
