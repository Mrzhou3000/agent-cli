"""REPLMode 单元测试。

目标模块: src/agent_cli/ui/repl.py
当前覆盖率: 0% → 目标 73%

策略：
- _handle_command: 直接调用方法，测试各命令分支
- _run_agent: mock AgentLoop
- run: monkeypatch input() 模拟用户输入
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent_cli.ui.repl import REPLExit, REPLMode

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_provider():
    return MagicMock()


@pytest.fixture
def mock_tools():
    return MagicMock()


@pytest.fixture
def mock_session_store():
    store = MagicMock()
    store.create.return_value = "sess_test_123456"
    store.list_sessions.return_value = []
    store.load.return_value = []
    return store


@pytest.fixture
def mock_memory():
    mem = MagicMock()
    mem.build_context.return_value = ""
    mem.file.list_all.return_value = []
    return mem


@pytest.fixture
def mock_compact():
    compact = MagicMock()
    compact.get_stats.return_value = {"compression_count": 3, "last_ratio": 0.45}
    return compact


@pytest.fixture
def mock_metrics():
    metrics = MagicMock()
    metrics.get_tool_summary.return_value = "工具调用: bash(5) read(3)"
    return metrics


@pytest.fixture
def mock_alerts():
    alerts = MagicMock()
    alerts.get_alerts_summary.return_value = "P2: 重试超2次"
    return alerts


@pytest.fixture
def repl(mock_provider, mock_tools, mock_session_store, mock_memory, mock_compact, mock_metrics, mock_alerts):
    """带所有依赖的完整 REPLMode 实例。"""
    return REPLMode(
        provider=mock_provider,
        tools=mock_tools,
        session_store=mock_session_store,
        memory=mock_memory,
        compact=mock_compact,
        max_iterations=20,
        verbose=False,
        metrics=mock_metrics,
        alerts=mock_alerts,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# REPLExit 异常
# ═══════════════════════════════════════════════════════════════════════════════

class TestREPLExit:
    """REPLExit 异常测试。"""

    def test_is_base_exception(self):
        """REPLExit 继承 BaseException 而非 Exception，避免被 except Exception 误捕。"""
        assert issubclass(REPLExit, BaseException)

    def test_can_be_raised(self):
        """REPLExit 可以被 raise 和捕获。"""
        with pytest.raises(REPLExit):
            raise REPLExit()


# ═══════════════════════════════════════════════════════════════════════════════
# REPLMode.__init__
# ═══════════════════════════════════════════════════════════════════════════════

class TestREPLModeInit:
    """REPLMode.__init__ 测试。"""

    def test_default_values(self, mock_provider, mock_tools):
        """默认值应正确初始化。"""
        r = REPLMode(provider=mock_provider, tools=mock_tools)
        assert r._history == []
        assert r._session_id is None
        assert r._resume_session is None
        assert r.verbose is False
        assert r.max_iterations == 20

    def test_custom_values(self, mock_provider, mock_tools):
        """自定义参数应被正确保存。"""
        r = REPLMode(
            provider=mock_provider,
            tools=mock_tools,
            max_iterations=5,
            verbose=True,
            resume_session="sess_abc",
        )
        assert r.max_iterations == 5
        assert r.verbose is True
        assert r._resume_session == "sess_abc"


# ═══════════════════════════════════════════════════════════════════════════════
# _handle_command
# ═══════════════════════════════════════════════════════════════════════════════

class TestHandleCommand:
    """_handle_command 各命令分支测试。"""

    def test_exit_command(self, repl: REPLMode):
        """/exit 应抛出 REPLExit。"""
        with pytest.raises(REPLExit):
            repl._handle_command("/exit")

    def test_quit_command(self, repl: REPLMode):
        """/quit 应抛出 REPLExit。"""
        with pytest.raises(REPLExit):
            repl._handle_command("/quit")

    def test_help_command(self, repl: REPLMode, capsys):
        """/help 应显示帮助文本。"""
        repl._handle_command("/help")
        captured = capsys.readouterr()
        assert "/exit" in captured.out

    def test_question_mark_help(self, repl: REPLMode, capsys):
        """/? 也应显示帮助文本。"""
        repl._handle_command("/?")
        captured = capsys.readouterr()
        assert "/exit" in captured.out

    def test_save_with_session(self, repl: REPLMode, capsys):
        """有 session 时 /save 应保存会话。"""
        repl._session_id = "sess_test"
        repl._history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        repl._handle_command("/save")
        captured = capsys.readouterr()
        assert "已保存" in captured.out
        repl.session_store.append.assert_called_once()

    def test_save_without_session(self, repl: REPLMode, capsys):
        """无 session 时 /save 应提示未创建会话。"""
        repl._session_id = None
        repl._handle_command("/save")
        captured = capsys.readouterr()
        assert "未创建会话" in captured.out

    def test_clear_command(self, repl: REPLMode, capsys):
        """/clear 应清空历史。"""
        repl._history = [{"role": "user", "content": "old"}]
        repl._handle_command("/clear")
        assert repl._history == []
        captured = capsys.readouterr()
        assert "已清空" in captured.out

    def test_stats_with_all(self, repl: REPLMode, capsys):
        """/stats 应显示压缩、消息、指标、告警信息。"""
        repl._history = [{"role": "user", "content": "m1"}, {"role": "assistant", "content": "a1"}]
        repl._handle_command("/stats")
        captured = capsys.readouterr()
        assert "压缩触发" in captured.out
        assert "消息数" in captured.out
        assert "bash(5)" in captured.out

    def test_stats_no_compact(self, mock_provider, mock_tools, mock_metrics, mock_alerts, capsys):
        """无 compact 时 /stats 不应显示压缩信息。"""
        r = REPLMode(provider=mock_provider, tools=mock_tools, metrics=mock_metrics, alerts=mock_alerts)
        r._handle_command("/stats")
        captured = capsys.readouterr()
        assert "压缩触发" not in captured.out
        assert "消息数" in captured.out

    def test_sessions_list(self, repl: REPLMode, capsys):
        """/sessions -l 应列出会话。"""
        repl._handle_command("/sessions --list")
        captured = capsys.readouterr()
        # session_store.list_sessions 返回 []，显示"暂无会话记录"
        assert "暂无会话记录" in captured.out

    def test_sessions_search(self, repl: REPLMode, capsys):
        """/sessions --search=关键词 应搜索会话（命令被转小写，用全小写关键词）。"""
        repl._handle_command("/sessions --search=todo")
        captured = capsys.readouterr()
        repl.session_store.find_by_keyword.assert_called_with("todo")

    def test_sessions_search_no_keyword(self, repl: REPLMode, capsys):
        """/sessions --search= 无关键词应提示。"""
        repl._handle_command("/sessions --search=")
        captured = capsys.readouterr()
        assert "请指定搜索关键词" in captured.out

    def test_sessions_show_id(self, repl: REPLMode, capsys):
        """/sessions <id> 应显示指定会话。"""
        repl.session_store.load.return_value = [{"role": "user", "content": "hello"}]
        repl._handle_command("/sessions sess_123")
        captured = capsys.readouterr()
        repl.session_store.load.assert_called_with("sess_123")

    def test_sessions_without_store(self, mock_provider, mock_tools, capsys):
        """无 session_store 时 /sessions 应提示未启用。"""
        r = REPLMode(provider=mock_provider, tools=mock_tools)
        r._handle_command("/sessions")
        captured = capsys.readouterr()
        assert "会话存储未启用" in captured.out

    def test_resume_existing(self, repl: REPLMode, capsys):
        """/resume <id> 恢复存在的会话。"""
        repl.session_store.load.return_value = [{"role": "user", "content": "old msg"}]
        repl._handle_command("/resume sess_abc")
        assert repl._session_id == "sess_abc"
        assert len(repl._history) == 1
        captured = capsys.readouterr()
        assert "已恢复会话" in captured.out

    def test_resume_nonexistent(self, repl: REPLMode, capsys):
        """/resume <id> 恢复不存在的会话。"""
        repl.session_store.load.return_value = []
        repl._handle_command("/resume sess_nonexist")
        captured = capsys.readouterr()
        assert "会话不存在" in captured.out

    def test_resume_no_id(self, repl: REPLMode, capsys):
        """/resume 不带参数应提示用法。"""
        repl._handle_command("/resume")
        captured = capsys.readouterr()
        assert "用法" in captured.out

    def test_memory_with_memory(self, repl: REPLMode, capsys):
        """有 memory 时 /memory 应列出记忆。"""
        repl._handle_command("/memory")
        captured = capsys.readouterr()
        repl.memory.file.list_all.assert_called_once()

    def test_memory_without_memory(self, mock_provider, mock_tools, capsys):
        """无 memory 时 /memory 应提示。"""
        r = REPLMode(provider=mock_provider, tools=mock_tools)
        r._handle_command("/memory")
        captured = capsys.readouterr()
        assert "记忆系统未启用" in captured.out

    def test_metrics_with_metrics(self, repl: REPLMode, capsys):
        """有 metrics 时 /metrics 应显示指标。"""
        repl._handle_command("/metrics")
        captured = capsys.readouterr()
        assert "bash(5)" in captured.out

    def test_metrics_without_metrics(self, mock_provider, mock_tools, capsys):
        """无 metrics 时 /metrics 应提示。"""
        r = REPLMode(provider=mock_provider, tools=mock_tools)
        r._handle_command("/metrics")
        captured = capsys.readouterr()
        assert "监控系统未启用" in captured.out

    def test_alerts_with_alerts(self, repl: REPLMode, capsys):
        """有 alerts 时 /alerts 应显示告警。"""
        repl._handle_command("/alerts")
        captured = capsys.readouterr()
        assert "P2" in captured.out

    def test_alerts_without_alerts(self, mock_provider, mock_tools, capsys):
        """无 alerts 时 /alerts 应提示。"""
        r = REPLMode(provider=mock_provider, tools=mock_tools)
        r._handle_command("/alerts")
        captured = capsys.readouterr()
        assert "告警系统未启用" in captured.out

    def test_unknown_command(self, repl: REPLMode, capsys):
        """未知命令应提示。"""
        repl._handle_command("/foobar")
        captured = capsys.readouterr()
        assert "未知命令" in captured.out
        assert "foobar" in captured.out


# ═══════════════════════════════════════════════════════════════════════════════
# _run_agent
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunAgent:
    """_run_agent 测试。"""

    def test_run_agent_success(self, repl: REPLMode, capsys):
        """_run_agent 成功时应打印回复。"""
        with patch("agent_cli.ui.repl.AgentLoop") as MockLoop:
            mock_loop = MagicMock()
            mock_loop.run.return_value.text = "你好，我是 Agent"
            mock_loop.run.return_value.tool_calls = []
            mock_loop._iteration = 1
            mock_loop._session_messages = [{"role": "assistant", "content": "你好"}]
            MockLoop.return_value = mock_loop

            repl._run_agent("你好")

            captured = capsys.readouterr()
            assert "你好，我是 Agent" in captured.out

    def test_run_agent_verbose(self, mock_provider, mock_tools, capsys):
        """verbose 模式应显示迭代和工具信息。"""
        r = REPLMode(provider=mock_provider, tools=mock_tools, verbose=True)
        with patch("agent_cli.ui.repl.AgentLoop") as MockLoop:
            mock_loop = MagicMock()
            mock_loop.run.return_value.text = "完成"
            mock_loop.run.return_value.tool_calls = ["tu_1"]
            mock_loop._iteration = 2
            mock_loop._session_messages = []
            MockLoop.return_value = mock_loop

            r._run_agent("搜索")

            captured = capsys.readouterr()
            assert "迭代" in captured.out
            assert "工具" in captured.out

    def test_run_agent_error(self, repl: REPLMode, capsys):
        """_run_agent 异常时应打印错误。"""
        with patch("agent_cli.ui.repl.AgentLoop") as MockLoop:
            mock_loop = MagicMock()
            mock_loop.run.side_effect = RuntimeError("API 错误")
            MockLoop.return_value = mock_loop

            repl._run_agent("查询")

            captured = capsys.readouterr()
            assert "执行出错" in captured.out
            assert "API 错误" in captured.out


# ═══════════════════════════════════════════════════════════════════════════════
# run (主循环)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRun:
    """REPLMode.run() 主循环测试。"""

    def test_run_keyboard_interrupt(self, repl: REPLMode, capsys):
        """Ctrl+C 应退出循环。"""
        with patch("agent_cli.ui.repl.AgentLoop"):
            with patch("builtins.input", side_effect=KeyboardInterrupt):
                repl.run()
                captured = capsys.readouterr()
                assert "再见" in captured.out

    def test_run_eof_error(self, repl: REPLMode, capsys):
        """Ctrl+D (EOFError) 应退出循环。"""
        with patch("agent_cli.ui.repl.AgentLoop"):
            with patch("builtins.input", side_effect=EOFError):
                repl.run()
                captured = capsys.readouterr()
                assert "再见" in captured.out

    def test_run_empty_input(self, repl: REPLMode, capsys):
        """空输入应跳过，直接退出。"""
        with patch("agent_cli.ui.repl.AgentLoop"):
            with patch("builtins.input", side_effect=["", "/exit"]):
                repl.run()
                captured = capsys.readouterr()
                assert "再见" in captured.out

    def test_run_exit_command(self, repl: REPLMode, capsys):
        """/exit 应退出 REPL。"""
        with patch("builtins.input", return_value="/exit"):
            repl.run()
            captured = capsys.readouterr()
            assert "再见" in captured.out

    def test_run_quit_command(self, repl: REPLMode, capsys):
        """/quit 应退出 REPL。"""
        with patch("builtins.input", return_value="/quit"):
            repl.run()
            captured = capsys.readouterr()
            assert "再见" in captured.out

    def test_run_normal_conversation(self, repl: REPLMode, capsys):
        """正常对话应调用 Agent 并打印回复。"""
        with patch("agent_cli.ui.repl.AgentLoop") as MockLoop:
            mock_loop = MagicMock()
            mock_loop.run.return_value.text = "回复内容"
            mock_loop.run.return_value.tool_calls = []
            mock_loop._iteration = 1
            mock_loop._session_messages = [{"role": "assistant", "content": "回复内容"}]
            MockLoop.return_value = mock_loop

            with patch("builtins.input", side_effect=["你好", "/exit"]):
                repl.run()
                captured = capsys.readouterr()
                assert "回复内容" in captured.out

    def test_run_session_creation(self, mock_provider, mock_tools, mock_session_store, capsys):
        """有 session_store 时应创建新会话。"""
        r = REPLMode(provider=mock_provider, tools=mock_tools, session_store=mock_session_store)
        with patch("builtins.input", return_value="/exit"):
            r.run()
            captured = capsys.readouterr()
            assert "会话 ID" in captured.out
            mock_session_store.create.assert_called_once()
