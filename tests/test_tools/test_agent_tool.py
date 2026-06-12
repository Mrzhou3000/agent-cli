"""AgentTool 单元测试。

目标模块: src/agent_cli/tools/agent_tool.py

AgentTool 有两种执行路径：
1. _provider is None → 占位模式（返回 unavailable）
2. _provider 注入 → 内部创建 AgentLoop + SubagentManager 执行子任务
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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

    def test_default_no_provider(self):
        """默认构造时 _provider 为 None。"""
        tool = AgentTool()
        assert tool._provider is None
        assert tool._tools is None

    def test_with_provider_and_tools(self):
        """可注入 provider 和 tools。"""
        provider = MagicMock()
        tools = MagicMock()
        tool = AgentTool(provider=provider, tools=tools)
        assert tool._provider is provider
        assert tool._tools is tools

    def test_max_iterations_default(self):
        """默认 max_iterations 为 10。"""
        tool = AgentTool()
        assert tool._max_iterations == 10

    def test_custom_max_iterations(self):
        """可自定义 max_iterations。"""
        tool = AgentTool(max_iterations=5)
        assert tool._max_iterations == 5


class TestAgentToolExecute:
    """AgentTool.execute() 测试。"""

    def test_no_provider_placeholder(self):
        """没有 provider 时应返回 unavailable 状态。"""
        tool = AgentTool()
        result = tool.execute(task="搜索 TODO")
        assert result["status"] == "unavailable"
        assert "占位" in result["result"]
        assert result["task"] == "搜索 TODO"

    def test_no_tools_placeholder(self):
        """没有 tools 时也应返回 unavailable。"""
        tool = AgentTool(provider=MagicMock(), tools=None)
        result = tool.execute(task="搜索 TODO")
        assert result["status"] == "unavailable"

    @patch("agent_cli.tools.agent_tool.SubagentManager")
    @patch("agent_cli.tools.agent_tool.AgentLoop")
    def test_with_provider_success(self, mock_loop, mock_mgr_cls):
        """有 provider 且执行成功时应返回 completed 状态。"""
        provider = MagicMock()
        tools = MagicMock()
        mock_mgr = MagicMock()
        mock_mgr.spawn.return_value.output = "找到 3 个 TODO"
        mock_mgr.spawn.return_value.success = True
        mock_mgr_cls.return_value = mock_mgr

        tool = AgentTool(provider=provider, tools=tools)
        result = tool.execute(task="搜索 TODO", context="project root")

        assert result["status"] == "completed"
        assert result["result"] == "找到 3 个 TODO"
        assert result["task"] == "搜索 TODO"
        # 验证 context 被正确传递
        _call_kwargs = mock_mgr.spawn.call_args.kwargs
        assert _call_kwargs["context"] == {"text": "project root"}

    @patch("agent_cli.tools.agent_tool.SubagentManager")
    @patch("agent_cli.tools.agent_tool.AgentLoop")
    def test_with_provider_no_context(self, mock_loop, mock_mgr_cls):
        """没有 context 时，spawn 的 context 参数应为 None。"""
        mock_mgr = MagicMock()
        mock_mgr.spawn.return_value.output = "完成"
        mock_mgr.spawn.return_value.success = True
        mock_mgr_cls.return_value = mock_mgr

        tool = AgentTool(provider=MagicMock(), tools=MagicMock())
        tool.execute(task="搜索")
        _call_kwargs = mock_mgr.spawn.call_args.kwargs
        assert _call_kwargs["context"] is None

    @patch("agent_cli.tools.agent_tool.SubagentManager")
    @patch("agent_cli.tools.agent_tool.AgentLoop")
    def test_with_provider_exception(self, mock_loop, mock_mgr_cls):
        """spawn 抛出异常时应返回 error 状态。"""
        mock_mgr = MagicMock()
        mock_mgr.spawn.side_effect = RuntimeError("Manager 不可用")
        mock_mgr_cls.return_value = mock_mgr

        tool = AgentTool(provider=MagicMock(), tools=MagicMock())
        result = tool.execute(task="搜索 TODO")
        assert result["status"] == "error"
        assert "Manager 不可用" in result["result"]
