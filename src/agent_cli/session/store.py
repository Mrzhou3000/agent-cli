"""SessionStore — 会话存储。

设计哲学（来源：14days-build + learn-claude-code）：
  JSONL 文件作为消息总线：零依赖、可调试、天然持久。
  每行一个完整消息对象，追加写入，天然支持流式。
  所有持久化基于文件系统，Git 可追踪，人类可阅读。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Session ID 前缀
SESSION_PREFIX = "sess"


def generate_session_id() -> str:
    """生成会话 ID。"""
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    return f"{SESSION_PREFIX}_{ts}_{short_id}"


class SessionStore:
    """会话存储。

    使用 JSONL（JSON Lines）格式存储消息。
    支持创建、追加、加载和列举会话。

    文件结构:
      .agent/sessions/
      ├── sess_20260610_143022_abc123.jsonl
      └── archives/  (24h 以上归档)

    Usage:
        store = SessionStore(base_dir=".agent")
        sid = store.create()
        store.append(sid, [msg1, msg2])
        messages = store.load(sid)
    """

    def __init__(self, base_dir: str = ".agent"):
        self._base_dir = Path(base_dir)
        self._sessions_dir = self._base_dir / "sessions"
        self._archives_dir = self._base_dir / "archives"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._archives_dir.mkdir(parents=True, exist_ok=True)

    def create(self) -> str:
        """创建新会话，返回会话 ID。

        Returns:
            格式: sess_YYYYMMDD_HHMMSS_xxxxxx
        """
        session_id = generate_session_id()
        # 创建空文件
        path = self._session_path(session_id)
        path.write_text("", encoding="utf-8")
        logger.info("创建会话: %s", session_id)
        return session_id

    def append(self, session_id: str, messages: list[dict]) -> None:
        """追加消息到会话。

        Args:
            session_id: 会话 ID。
            messages: 消息列表，每条追加为一行 JSON。
        """
        path = self._session_path(session_id)
        try:
            with open(path, "a", encoding="utf-8") as f:
                for msg in messages:
                    line = json.dumps(msg, ensure_ascii=False)
                    f.write(line + "\n")
        except Exception as e:
            logger.error("追加消息失败 [%s]: %s", session_id, e)

    def load(self, session_id: str) -> list[dict]:
        """加载会话的所有消息。

        Args:
            session_id: 会话 ID。

        Returns:
            消息列表，按写入顺序排列。
        """
        path = self._session_path(session_id)
        if not path.exists():
            logger.warning("会话不存在: %s", session_id)
            return []

        messages: list[dict] = []
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        messages.append(json.loads(line))
        except Exception as e:
            logger.error("加载会话失败 [%s]: %s", session_id, e)

        return messages

    def list_sessions(self) -> list[dict[str, Any]]:
        """列出所有活跃会话。

        Returns:
            [{"id": "...", "created": "...", "size": 123, "message_count": 5}, ...]
        """
        sessions = []
        for path in sorted(self._sessions_dir.glob(f"{SESSION_PREFIX}_*.jsonl"), reverse=True):
            try:
                stat = path.stat()
                raw = path.read_text(encoding="utf-8")
                msg_count = sum(1 for _ in raw.splitlines() if _.strip())
                sessions.append(
                    {
                        "id": path.stem,
                        "created": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                        "size": stat.st_size,
                        "message_count": msg_count,
                    }
                )
            except Exception:
                continue
        return sessions

    def find_by_keyword(self, keyword: str, max_results: int = 10) -> list[dict[str, Any]]:
        """按关键词搜索会话内容。

        Args:
            keyword: 搜索关键词。
            max_results: 最多返回结果数。

        Returns:
            匹配的会话列表。
        """
        matches: list[dict[str, Any]] = []
        keyword_lower = keyword.lower()

        for path in sorted(self._sessions_dir.glob(f"{SESSION_PREFIX}_*.jsonl"), reverse=True):
            if len(matches) >= max_results:
                break
            try:
                raw = path.read_text(encoding="utf-8")
                if keyword_lower not in raw.lower():
                    continue
                stat = path.stat()
                msg_count = sum(1 for _ in raw.splitlines() if _.strip())
                matches.append(
                    {
                        "id": path.stem,
                        "created": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                        "size": stat.st_size,
                        "message_count": msg_count,
                    }
                )
            except Exception:
                continue

        return matches

    def get_recent(self, count: int = 5) -> list[dict[str, Any]]:
        """获取最近的会话。

        Args:
            count: 返回数量。

        Returns:
            最近的会话列表。
        """
        return self.list_sessions()[:count]

    def delete(self, session_id: str) -> bool:
        """删除会话文件。"""
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()
            logger.info("删除会话: %s", session_id)
            return True
        return False

    def archive(self, session_id: str) -> bool:
        """将会话移至归档目录。"""
        src = self._session_path(session_id)
        if not src.exists():
            return False
        dst = self._archives_dir / src.name
        try:
            src.rename(dst)
            logger.info("归档会话: %s → archives/", session_id)
            return True
        except Exception as e:
            logger.error("归档失败 [%s]: %s", session_id, e)
            return False

    def _session_path(self, session_id: str) -> Path:
        """获取会话文件的完整路径。"""
        return self._sessions_dir / f"{session_id}.jsonl"
