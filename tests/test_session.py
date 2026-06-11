"""Session Store 单元测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from agent_cli.session.store import SessionStore, generate_session_id


class TestSessionStore:
    """SessionStore 核心功能测试。"""

    @pytest.fixture
    def store(self) -> SessionStore:
        with tempfile.TemporaryDirectory() as td:
            yield SessionStore(base_dir=str(Path(td) / ".agent"))

    def test_create_session(self, store: SessionStore):
        """测试创建会话。"""
        sid = store.create()
        assert sid.startswith("sess_")

    def test_append_and_load(self, store: SessionStore):
        """测试追加和读取消息。"""
        sid = store.create()
        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！我是助手。"},
        ]
        store.append(sid, messages)
        loaded = store.load(sid)
        assert len(loaded) == 2
        assert loaded[0]["role"] == "user"

    def test_load_nonexistent(self, store: SessionStore):
        """测试加载不存在的会话。"""
        msgs = store.load("sess_nonexistent")
        assert msgs == []

    def test_delete(self, store: SessionStore):
        """测试删除会话。"""
        sid = store.create()
        assert store.delete(sid) is True
        assert store.delete(sid) is False  # 已删除

    def test_list_sessions(self, store: SessionStore):
        """测试列出会话。"""
        s1 = store.create()
        store.append(s1, [{"role": "user", "content": "test"}])
        sessions = store.list_sessions()
        assert len(sessions) >= 1

    def test_find_by_keyword(self, store: SessionStore):
        """测试按关键词搜索会话。"""
        sid = store.create()
        store.append(sid, [{"role": "user", "content": "Python 开发笔记"}])
        results = store.find_by_keyword("Python")
        assert len(results) >= 1
        assert any(r["id"] == sid for r in results)

    def test_find_by_keyword_no_match(self, store: SessionStore):
        """测试搜索无匹配。"""
        sid = store.create()
        store.append(sid, [{"role": "user", "content": "Hello World"}])
        results = store.find_by_keyword("NonexistentKeywordXYZ")
        assert len(results) == 0

    def test_get_recent(self, store: SessionStore):
        """测试获取最近会话。"""
        store.create()
        s2 = store.create()
        store.append(s2, [{"role": "user", "content": "test"}])

        recent = store.get_recent(count=5)
        assert len(recent) >= 2

    def test_get_recent_limit(self, store: SessionStore):
        """测试最近会话的数量限制。"""
        for _ in range(5):
            store.create()
        recent = store.get_recent(count=3)
        assert len(recent) <= 3

    def test_generate_session_id(self):
        """测试会话 ID 生成。"""
        sid = generate_session_id()
        assert sid.startswith("sess_")
        parts = sid.split("_")
        assert len(parts) >= 4

    def test_archive(self, store: SessionStore):
        """测试归档会话。"""
        sid = store.create()
        store.append(sid, [{"role": "user", "content": "test"}])
        assert store.archive(sid) is True
        # 归档后不能再从活跃列表加载
        assert store.load(sid) == []

    def test_find_by_keyword_max_results(self, store: SessionStore):
        """测试搜索关键词的 max_results 限制。"""
        for i in range(3):
            sid = store.create()
            store.append(sid, [{"role": "user", "content": f"Python topic {i}"}])
        results = store.find_by_keyword("Python", max_results=2)
        assert len(results) <= 2
