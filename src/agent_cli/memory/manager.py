"""MemoryManager — 三级记忆协调器。

整合 FileMemory + SessionMemory + ProjectMemory 三层级。
提供统一的读写接口，供 AgentLoop 调用。
"""

from __future__ import annotations

import logging
from typing import Any

from agent_cli.memory.file_memory import FileMemory, MemoryEntry
from agent_cli.memory.project_memory import ProjectMemory
from agent_cli.memory.session_memory import SessionMemory

logger = logging.getLogger(__name__)


class MemoryManager:
    """三级记忆协调器。

    统一管理文件级（长期）、会话级（短期）、项目级记忆。
    AgentLoop 通过此接口访问所有记忆层。

    Usage:
        mm = MemoryManager(base_dir=".agent")
        mm.write_note("用户偏好", "喜欢简洁回答")
        results = mm.search("Python")
        ctx = mm.build_context()
    """

    def __init__(self, base_dir: str = ".agent"):
        self.file = FileMemory(base_dir=base_dir)
        self.session = SessionMemory(base_dir=base_dir)
        self.project = ProjectMemory(base_dir=base_dir)

    def write_note(
        self,
        name: str,
        content: str,
        tags: list[str] | None = None,
        description: str = "",
    ) -> str:
        """写入一条文件级记忆。

        Args:
            name: 记忆名称。
            content: 记忆内容。
            tags: 标签列表。
            description: 描述。

        Returns:
            文件路径。
        """
        metadata: dict[str, Any] = {}
        if tags:
            metadata["tags"] = tags
        return self.file.write(name, content, metadata=metadata, description=description)

    def read_note(self, name: str) -> MemoryEntry | None:
        """读取一条文件级记忆。"""
        return self.file.read(name)

    def search(self, query: str = "", tags: list[str] | None = None) -> list[MemoryEntry]:
        """搜索所有文件级记忆。"""
        return self.file.search(query=query, tags=tags)

    def build_context(self, keywords: str = "") -> str:
        """构建注入到系统提示中的上下文。

        聚合三层记忆中与当前任务相关的信息。

        Args:
            keywords: 当前任务关键信息。

        Returns:
            格式化的上下文字符串。
        """
        parts: list[str] = []

        # 1. 项目级记忆
        project_content = self.project.read()
        if project_content:
            parts.append("[项目记忆]\n" + project_content[:2000])

        # 2. 文件级记忆（按标签）
        mem_entries = self.search(query=keywords) if keywords else self.file.list_all()[:5]

        if mem_entries:
            mem_text = "\n".join(
                f"- [{e.name}] {e.description}: {e.content[:200]}" for e in mem_entries
            )
            parts.append(f"[文件记忆]\n{mem_text}")

        # 3. 历史会话
        recent = self.session.get_recent_sessions(limit=3)
        if recent:
            session_lines = [
                f"- {s['id']}: {s['message_count']} 条消息 ({s['created'][:10]})" for s in recent
            ]
            parts.append("[最近会话]\n" + "\n".join(session_lines))

        return "\n\n".join(parts)
