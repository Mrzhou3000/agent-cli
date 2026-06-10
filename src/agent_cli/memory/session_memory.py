"""SessionMemory — 会话级记忆。

包裹 SessionStore，提供会话级记忆的高层接口。
支持最近会话摘要、上下文提取等功能。
"""

from __future__ import annotations

import logging
from typing import Any

from agent_cli.session.store import SessionStore

logger = logging.getLogger(__name__)


class SessionMemory:
    """会话级记忆管理器。

    基于 SessionStore（JSONL），管理当前和近期会话。
    提供会话摘要提取、上下文恢复等高层功能。

    Usage:
        sm = SessionMemory(base_dir=".agent")
        summary = sm.get_recent_summary()
        context = sm.get_relevant_context("Python 项目")
    """

    def __init__(self, base_dir: str = ".agent"):
        self._store = SessionStore(base_dir=base_dir)

    @property
    def store(self) -> SessionStore:
        """底层 SessionStore 实例。"""
        return self._store

    def get_recent_sessions(self, limit: int = 5) -> list[dict[str, Any]]:
        """获取最近的会话摘要。

        Args:
            limit: 返回会话数量。

        Returns:
            会话摘要列表。
        """
        sessions = self._store.list_sessions()
        return sessions[:limit]

    def get_relevant_context(self, keywords: str, max_sessions: int = 3) -> list[dict]:
        """根据关键词搜索历史会话中的相关内容。

        Args:
            keywords: 搜索关键词。
            max_sessions: 搜索的会话数量上限。

        Returns:
            相关消息片段列表。
        """
        sessions = self._store.list_sessions()[:max_sessions]
        results = []
        kw_lower = keywords.lower()

        for sess in sessions:
            messages = self._store.load(sess["id"])
            for msg in messages:
                content = msg.get("content", "")
                if isinstance(content, str) and kw_lower in content.lower():
                    results.append(
                        {
                            "session_id": sess["id"],
                            "role": msg.get("role", ""),
                            "content": content[:500],
                        }
                    )
                elif isinstance(content, list):
                    blocks = [
                        b.get("text", "")
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    text = " ".join(blocks)
                    if kw_lower in text.lower():
                        results.append(
                            {
                                "session_id": sess["id"],
                                "role": msg.get("role", ""),
                                "content": text[:500],
                            }
                        )

        return results

    def get_session_summary(self, session_id: str) -> dict | None:
        """获取单个会话的摘要信息。

        Args:
            session_id: 会话 ID。

        Returns:
            会话摘要，包含消息数、时间、关键主题等。
        """
        messages = self._store.load(session_id)
        if not messages:
            return None

        # 提取前几条用户消息作为主题
        user_messages = []
        for msg in messages[:10]:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    user_messages.append(content[:100])

        return {
            "session_id": session_id,
            "message_count": len(messages),
            "user_topics": user_messages[:5],
        }
