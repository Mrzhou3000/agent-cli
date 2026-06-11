"""SessionMemory 单元测试。

目标模块: src/agent_cli/memory/session_memory.py
当前覆盖率: 39% → 目标 80%

SessionMemory 是 SessionStore 的高层封装，
提供会话摘要、上下文提取等功能。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from agent_cli.memory.session_memory import SessionMemory


@pytest.fixture
def mem() -> SessionMemory:
    """SessionMemory fixture（使用临时目录）。"""
    with TemporaryDirectory() as td:
        yield SessionMemory(base_dir=str(Path(td) / ".agent"))


class TestSessionMemory:
    """SessionMemory 单元测试。"""

    def test_property_store(self, mem: SessionMemory):
        """store 属性应返回 SessionStore 实例。"""
        assert mem.store is not None

    def test_get_recent_sessions_empty(self, mem: SessionMemory):
        """无会话时应返回空列表。"""
        sessions = mem.get_recent_sessions()
        assert sessions == []

    def test_get_recent_sessions_with_data(self, mem: SessionMemory):
        """有会话时返回最近的会话摘要。"""
        sid = mem.store.create()
        mem.store.append(sid, [{"role": "user", "content": "hello"}])
        sessions = mem.get_recent_sessions(limit=5)
        assert len(sessions) >= 1
        assert sessions[0]["id"] == sid

    def test_get_recent_sessions_limit(self, mem: SessionMemory):
        """limit 参数应限制返回数量。"""
        for _ in range(3):
            sid = mem.store.create()
            mem.store.append(sid, [{"role": "user", "content": "test"}])
        sessions = mem.get_recent_sessions(limit=2)
        assert len(sessions) <= 2

    def test_get_session_summary_nonexistent(self, mem: SessionMemory):
        """不存在的会话应返回 None。"""
        summary = mem.get_session_summary("sess_nonexistent")
        assert summary is None

    def test_get_session_summary_existing(self, mem: SessionMemory):
        """存在的会话应返回摘要信息。"""
        sid = mem.store.create()
        mem.store.append(sid, [
            {"role": "user", "content": "帮我搜索"},
            {"role": "assistant", "content": "好的"},
        ])
        summary = mem.get_session_summary(sid)
        assert summary is not None
        assert summary["session_id"] == sid
        assert summary["message_count"] == 2
        assert "帮我搜索" in summary["user_topics"]

    def test_get_relevant_context_no_keyword_match(self, mem: SessionMemory):
        """无关键词匹配应返回空列表。"""
        sid = mem.store.create()
        mem.store.append(sid, [{"role": "user", "content": "Hello World"}])
        results = mem.get_relevant_context("Python")
        assert results == []

    def test_get_relevant_context_keyword_match(self, mem: SessionMemory):
        """有关键词匹配应返回相关消息。"""
        sid = mem.store.create()
        mem.store.append(sid, [
            {"role": "user", "content": "Python 开发"},
            {"role": "assistant", "content": "Python 是很好的语言"},
        ])
        results = mem.get_relevant_context("python")
        assert len(results) >= 1
        assert any("Python" in r["content"] for r in results)

    def test_get_relevant_context_content_list(self, mem: SessionMemory):
        """消息 content 为列表时也能正确搜索。"""
        sid = mem.store.create()
        mem.store.append(sid, [
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "关于 Python 的说明"}],
            }
        ])
        results = mem.get_relevant_context("python")
        assert len(results) >= 1
