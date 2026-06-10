"""Tests for Phase 3 — Subagent System."""

from __future__ import annotations

from agent_cli.subagent.manager import SubagentResult


class TestSubagentResult:
    """SubagentResult 数据模型测试。"""

    def test_success_property(self):
        """无 error 时 success 应为 True。"""
        result = SubagentResult(task="test")
        assert result.success is True
        assert result.error == ""

    def test_failure_property(self):
        """有 error 时 success 应为 False。"""
        result = SubagentResult(task="test", error="Something went wrong")
        assert result.success is False

    def test_default_values(self):
        """默认值应正确初始化。"""
        result = SubagentResult(task="search")
        assert result.task == "search"
        assert result.output == ""
        assert result.error == ""
        assert result.messages == []
        assert result.tool_calls == 0
        assert result.iterations == 0
