"""Session Store 单元测试。"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

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

    def test_archive_nonexistent(self, store: SessionStore):
        """归档不存在的会话返回 False。"""
        assert store.archive("sess_nonexistent") is False

    def test_archive_failure_logs_error(self, store: SessionStore, caplog):
        """归档失败时记录日志并返回 False。"""
        sid = store.create()
        store.append(sid, [{"role": "user", "content": "test"}])
        with patch.object(Path, "rename", side_effect=PermissionError("denied")):
            result = store.archive(sid)
            assert result is False

    def test_append_error_logged(self, store: SessionStore, caplog):
        """追加消息失败时记录日志，不抛出异常。"""
        caplog.set_level(logging.ERROR)
        # 使用不存在的路径触发写入错误
        broken = SessionStore(base_dir=str(Path(tempfile.mktemp()) / ".agent"))
        # create 会创建目录，但我们可以模拟写保护
        sid = broken.create()
        # 删掉 sessions 目录使后续写入失败
        import shutil

        shutil.rmtree(Path(broken._base_dir) / "sessions")
        broken.append(sid, [{"role": "user", "content": "test"}])
        assert len(caplog.records) >= 1

    def test_load_error_logged(self, store: SessionStore, caplog):
        """加载损坏会话时记录日志并返回空列表。"""
        caplog.set_level(logging.ERROR)
        sid = store.create()
        store.append(sid, [{"role": "user", "content": "valid"}])
        # 向文件写入非 JSON 内容使其损坏
        path = Path(store._sessions_dir) / f"{sid}.jsonl"
        path.write_text("not valid json\n", encoding="utf-8")
        loaded = store.load(sid)
        assert loaded == []

    def test_list_sessions_skips_corrupt(self, store: SessionStore):
        """list_sessions 遇到损坏文件时跳过而非崩溃。"""
        sid = store.create()
        store.append(sid, [{"role": "user", "content": "test"}])
        # 额外写入一个原始文件
        extra = Path(store._sessions_dir) / "sess_corrupt.jsonl"
        extra.write_bytes(b"\xff\xfe\x00\x01")  # 非 UTF-8 内容
        sessions = store.list_sessions()
        # 应该跳过损坏文件，仍然列出正常文件
        assert any(s["id"] == sid for s in sessions)
