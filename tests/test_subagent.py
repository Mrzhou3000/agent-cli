"""SubagentManager 单元测试（增强）。

目标模块: src/agent_cli/subagent/manager.py
当前覆盖率: 30% → 目标 78%

现有测试（3 个）已覆盖 SubagentResult 数据类。
本文件新增 SubagentManager 的初始化、spawn、spawn_batch、上下文构建等测试。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from agent_cli.subagent.manager import SubagentManager, SubagentResult


class TestSubagentResult:
    """SubagentResult 数据模型测试（现有）。"""

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


class TestSubagentManagerInit:
    """SubagentManager.__init__ 测试。"""

    def test_saves_parent(self):
        """构造函数应保存 parent 引用。"""
        parent = MagicMock()
        mgr = SubagentManager(parent=parent)
        assert mgr._parent is parent

    def test_default_max_iterations(self):
        """默认 max_iterations 应为 10。"""
        mgr = SubagentManager(parent=MagicMock())
        assert mgr._max_iterations == 10

    def test_custom_max_iterations(self):
        """可设置自定义 max_iterations。"""
        mgr = SubagentManager(parent=MagicMock(), max_iterations=5)
        assert mgr._max_iterations == 5


class TestSubagentManagerSpawn:
    """SubagentManager.spawn() 测试。"""

    @pytest.fixture
    def mock_parent(self):
        """模拟的父 AgentLoop。"""
        parent = MagicMock()
        parent.provider = MagicMock()
        parent.tools = MagicMock()
        parent.hooks = MagicMock()
        return parent

    def test_spawn_creates_agent_loop(self, mock_parent):
        """spawn 应创建一个新的 AgentLoop 实例。"""
        with patch("agent_cli.subagent.manager.AgentLoop") as mock_loop_cls:
            mock_loop_instance = MagicMock()
            mock_loop_instance.run.return_value.text = "结果文本"
            mock_loop_instance._iteration = 3
            mock_loop_instance._session_messages = []
            mock_loop_cls.return_value = mock_loop_instance

            mgr = SubagentManager(parent=mock_parent)
            mgr.spawn(task="搜索 TODO")

            # 验证 AgentLoop 被用正确参数创建
            mock_loop_cls.assert_called_once()
            _, kwargs = mock_loop_cls.call_args
            assert kwargs["provider"] is mock_parent.provider
            assert kwargs["tools"] is mock_parent.tools
            assert kwargs["hooks"] is mock_parent.hooks
            assert kwargs["max_iterations"] == 10

    def test_spawn_with_custom_provider(self, mock_parent):
        """spawn 可以使用独立的 provider。"""
        with patch("agent_cli.subagent.manager.AgentLoop") as mock_loop_cls:
            mock_loop_instance = MagicMock()
            mock_loop_instance.run.return_value.text = "结果"
            mock_loop_instance._iteration = 1
            mock_loop_instance._session_messages = []
            mock_loop_cls.return_value = mock_loop_instance

            custom_provider = MagicMock()
            mgr = SubagentManager(parent=mock_loop_cls, max_iterations=5)
            mgr.spawn(task="搜索", provider=custom_provider)

    def test_spawn_success_result(self, mock_parent):
        """spawn 成功时应返回正确的 SubagentResult。"""
        with patch("agent_cli.subagent.manager.AgentLoop") as mock_loop_cls:
            mock_loop = MagicMock()
            mock_loop.run.return_value.text = "找到 5 个结果"
            mock_loop._iteration = 2
            mock_loop._session_messages = [{"role": "assistant", "content": "完成"}]
            # mock tool_calls
            mock_loop.run.return_value.tool_calls = ["call_1", "call_2"]
            mock_loop_cls.return_value = mock_loop

            mgr = SubagentManager(parent=mock_parent)
            result = mgr.spawn(task="搜索 TODO")

            assert result.task == "搜索 TODO"
            assert result.output == "找到 5 个结果"
            assert result.iterations == 2
            assert result.tool_calls == 2
            assert result.messages == [{"role": "assistant", "content": "完成"}]
            assert result.error == ""

    def test_spawn_exception(self, mock_parent):
        """spawn 执行异常时应记录 error。"""
        with patch("agent_cli.subagent.manager.AgentLoop") as mock_loop_cls:
            mock_loop = MagicMock()
            mock_loop.run.side_effect = RuntimeError("子Agent 崩溃")
            mock_loop_cls.return_value = mock_loop

            mgr = SubagentManager(parent=mock_parent)
            result = mgr.spawn(task="搜索 TODO")

            assert result.error != ""
            assert "子Agent 崩溃" in result.error
            assert result.success is False


class TestSubagentManagerSpawnBatch:
    """SubagentManager.spawn_batch() 测试。"""

    def test_spawn_batch_empty(self):
        """空任务列表应返回空列表。"""
        mgr = SubagentManager(parent=MagicMock())
        results = mgr.spawn_batch([])
        assert results == []

    def test_spawn_batch_multiple_tasks(self):
        """多个任务应顺序执行并返回对应数量的结果。"""
        mgr = SubagentManager(parent=MagicMock())
        with patch.object(mgr, "spawn") as mock_spawn:
            mock_spawn.return_value = SubagentResult(task="dummy")

            results = mgr.spawn_batch(["任务1", "任务2", "任务3"])
            assert len(results) == 3
            assert mock_spawn.call_count == 3


class TestBuildContext:
    """SubagentManager._build_context() 测试。"""

    def test_no_parent_messages(self):
        """父Agent 无会话消息时应返回空列表。"""
        parent = MagicMock()
        # 模拟父 Agent 没有 _session_messages 属性
        del parent._session_messages
        mgr = SubagentManager(parent=parent)
        ctx = mgr._build_context(task="test")
        assert ctx == []

    def test_with_parent_messages(self):
        """有父会话消息时应包含父 Agent 上下文摘要。"""
        parent = MagicMock()
        parent._session_messages = [
            {"role": "user", "content": "帮我搜索"},
            {"role": "assistant", "content": "好的，我来搜索"},
        ]
        mgr = SubagentManager(parent=parent)
        ctx = mgr._build_context(task="test")
        assert len(ctx) > 0
        assert ctx[0]["role"] == "system"
        assert "父Agent上下文" in ctx[0]["content"]

    def test_with_extra_context(self):
        """传入 context 时应包含额外上下文。"""
        parent = MagicMock()
        parent._session_messages = []
        mgr = SubagentManager(parent=parent)
        ctx = mgr._build_context(
            task="test",
            context={"focus": "安全性", "limit": "10"},
        )
        assert len(ctx) == 1
        assert ctx[0]["role"] == "system"
        assert "额外上下文" in ctx[0]["content"]
        assert "focus: 安全性" in ctx[0]["content"]
        assert "limit: 10" in ctx[0]["content"]

    def test_with_both_messages_and_context(self):
        """同时有父消息和 extra context 时应包含两部分。"""
        parent = MagicMock()
        parent._session_messages = [{"role": "user", "content": "hi"}]
        mgr = SubagentManager(parent=parent)
        ctx = mgr._build_context(task="test", context={"key": "val"})
        assert len(ctx) == 2
        assert "父Agent上下文" in ctx[0]["content"]
        assert "额外上下文" in ctx[1]["content"]


class TestSummarizeMessages:
    """SubagentManager._summarize_messages() 测试。"""

    def test_empty_messages(self):
        """空消息应返回空字符串。"""
        parent = MagicMock()
        mgr = SubagentManager(parent=parent)
        summary = mgr._summarize_messages([])
        assert summary == ""

    def test_user_messages(self):
        """user 消息应格式化为 '用户: ...'。"""
        mgr = SubagentManager(parent=MagicMock())
        msgs = [{"role": "user", "content": "你好"}]
        summary = mgr._summarize_messages(msgs)
        assert "用户: 你好" in summary

    def test_assistant_text_messages(self):
        """assistant 文本消息应格式化为 '助手: ...'。"""
        mgr = SubagentManager(parent=MagicMock())
        msgs = [{"role": "assistant", "content": "我来帮你"}]
        summary = mgr._summarize_messages(msgs)
        assert "助手: 我来帮你" in summary

    def test_assistant_tool_call_messages(self):
        """assistant 含工具调用时应显示 '[工具调用]'。"""
        mgr = SubagentManager(parent=MagicMock())
        msgs = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "我来搜索"},
                    {
                        "type": "tool_use",
                        "id": "tu_1",
                        "name": "grep",
                        "input": {"pattern": "TODO"},
                    },
                ],
            }
        ]
        summary = mgr._summarize_messages(msgs)
        assert "助手: 我来搜索" in summary
        assert "[工具调用]" not in summary  # 有 text 时用 text

    def test_assistant_only_tool_call(self):
        """assistant 只有工具调用（无 text）时应显示 '[工具调用]'。"""
        mgr = SubagentManager(parent=MagicMock())
        msgs = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tu_1",
                        "name": "grep",
                        "input": {"pattern": "TODO"},
                    },
                ],
            }
        ]
        summary = mgr._summarize_messages(msgs)
        assert "助手: [工具调用]" in summary

    def test_max_items(self):
        """应只提取最近的 max_items 条消息。"""
        mgr = SubagentManager(parent=MagicMock())
        msgs = [{"role": "user", "content": f"消息{i}"} for i in range(20)]
        summary = mgr._summarize_messages(msgs, max_items=5)
        assert summary.count("用户: 消息") <= 5

    def test_tool_result_content(self):
        """user 消息中的非字符串内容（工具结果）应显示 '[工具结果]'。"""
        mgr = SubagentManager(parent=MagicMock())
        msgs = [
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "tu_1", "content": "完成"}],
            }
        ]
        summary = mgr._summarize_messages(msgs)
        assert "用户: [工具结果]" in summary

    def test_content_truncation(self):
        """超过 200 字符的内容应被截断。"""
        mgr = SubagentManager(parent=MagicMock())
        long_text = "x" * 500
        msgs = [{"role": "user", "content": long_text}]
        summary = mgr._summarize_messages(msgs)
        # 每条消息截断到 200 字符
        assert len(summary) < 500
