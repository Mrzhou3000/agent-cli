"""AgentTool 单元测试。

目标模块: src/agent_cli/tools/agent_tool.py
当前覆盖率: 0% → 目标 95%

AgentTool 是一个子Agent 调用工具，有两种执行路径：
1. _manager is None → 占位模式（Phase 1 回退）
2. _manager 注入 → 实际派发子Agent
"""

from __future__ import annotations

from unittest.mock import MagicMock

from agent_cli.tools.agent_tool import AgentTool
from agent_cli.tools.base import SafetyLevel


class TestAgentToolSpec:
    """AgentTool.spec() 测试。"""

    def test_spec_name(self):
        """spec() 的 name 应为 agent。"""
        tool = AgentTool()
        spec = tool.spec()
        assert spec.name == "agent"

    def test_spec_safety(self):
        """agent 安全等级应为 SENSITIVE。"""
        tool = AgentTool()
        spec = tool.spec()
        assert spec.safety == SafetyLevel.SENSITIVE

    def test_spec_parameters(self):
        """spec() 参数含 task（必需）和 context（可选）。"""
        tool = AgentTool()
        spec = tool.spec()
        props = spec.parameters.get("properties", {})
        assert "task" in props
        assert "context" in props
        assert "task" in spec.parameters.get("required", [])

    def test_spec_handler(self):
        """spec() 的 handler 应指向 execute 方法。"""
        tool = AgentTool()
        spec = tool.spec()
        assert spec.handler == tool.execute


class TestAgentToolInit:
    """AgentTool.__init__ 测试。"""

    def test_default_no_manager(self):
        """默认构造时 _manager 为 None。"""
        tool = AgentTool()
        assert tool._manager is None

    def test_with_manager(self):
        """可注入自定义 manager。"""
        mgr = MagicMock()
        tool = AgentTool(subagent_manager=mgr)
        assert tool._manager is mgr


class TestAgentToolExecute:
    """AgentTool.execute() 测试。"""

    def test_no_manager_placeholder(self):
        """没有 manager 时应返回 not_implemented 状态。"""
        tool = AgentTool()
        result = tool.execute(task="搜索 TODO")
        assert result["status"] == "not_implemented"
        assert "占位" in result["result"]
        assert result["task"] == "搜索 TODO"

    def test_with_manager_success(self):
        """有 manager 且执行成功时应返回 completed 状态。"""
        mgr = MagicMock()
        mgr.spawn.return_value = MagicMock(__str__=lambda self: "找到 3 个 TODO")
        tool = AgentTool(subagent_manager=mgr)
        result = tool.execute(task="搜索 TODO", context="project root")
        assert result["status"] == "completed"
        assert mgr.spawn.call_count == 1
        # 验证 context 被正确传递
        _call_kwargs = mgr.spawn.call_args.kwargs
        assert _call_kwargs["context"] == {"text": "project root"}

    def test_with_manager_no_context(self):
        """没有 context 时，spawn 的 context 参数应为 None。"""
        mgr = MagicMock()
        mgr.spawn.return_value = MagicMock(__str__=lambda self: "完成")
        tool = AgentTool(subagent_manager=mgr)
        tool.execute(task="搜索")
        _call_kwargs = mgr.spawn.call_args.kwargs
        assert _call_kwargs["context"] is None

    def test_with_manager_exception(self):
        """manager.spawn 抛出异常时应返回 error 状态。"""
        mgr = MagicMock()
        mgr.spawn.side_effect = RuntimeError("Manager 不可用")
        tool = AgentTool(subagent_manager=mgr)
        result = tool.execute(task="搜索 TODO")
        assert result["status"] == "error"
        assert "Manager 不可用" in result["result"]
