"""ProjectMemory — 项目级记忆。

自动维护 `.agent/project.md` 项目知识文档。
包含项目结构、技术选型、设计决策等信息。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ProjectMemory:
    """项目级记忆管理器。

    管理 `.agent/project.md` — 自动维护的项目知识文档。
    Agent 在每次 loop 间歇自动同步。

    Usage:
        pm = ProjectMemory(base_dir=".agent")
        pm.update("项目结构", "src/agent_cli/main.py — CLI 入口")
        content = pm.read()
    """

    def __init__(self, base_dir: str = ".agent"):
        self._path = Path(base_dir) / "project.md"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def read(self) -> str:
        """读取项目记忆。"""
        if self._path.exists():
            return self._path.read_text(encoding="utf-8")
        return ""

    def update(self, section: str, content: str) -> None:
        """更新项目记忆中的某个章节。

        Args:
            section: 章节标题。
            content: 章节内容。
        """
        current = self.read()
        ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        marker = f"## {section}"
        new_section = f"{marker}\n\n{content.strip()}\n\n_更新于: {ts}_\n"

        if marker in current:
            # 替换已有章节
            lines = current.split("\n")
            new_lines = []
            skip = False
            skip_count = 0
            for line in lines:
                if line.startswith(marker):
                    skip = True
                    skip_count = 0
                    new_lines.append(new_section)
                    continue
                if skip:
                    if skip_count > 0 and line.startswith("## "):
                        skip = False
                        new_lines.append(line)
                    else:
                        skip_count += 1
                    continue
                new_lines.append(line)
            updated = "\n".join(new_lines)
        else:
            # 追加新章节
            updated = current + "\n" + new_section if current else new_section

        self._path.write_text(updated.strip() + "\n", encoding="utf-8")
        logger.info("更新项目记忆: %s", section)

    def append(self, section: str, line: str) -> None:
        """在指定章节追加一行内容。

        Args:
            section: 章节标题。
            line: 追加的内容行。
        """
        current = self.read()
        marker = f"## {section}"
        ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        if marker in current:
            # 在章节末尾追加
            lines = current.split("\n")
            new_lines = []
            in_section = False
            appended = False
            for i, line_text in enumerate(lines):
                new_lines.append(line_text)
                if line_text.startswith(marker):
                    in_section = True
                    continue
                if in_section and (line_text.startswith("## ") or i == len(lines) - 1):
                    if i == len(lines) - 1:
                        new_lines.append(f"- {line}")
                    else:
                        new_lines.insert(-1, f"- {line}")
                    appended = True
                    in_section = False
            if not appended:
                new_lines.append(f"- {line}")
            current = "\n".join(new_lines)
        else:
            current += f"\n## {section}\n- {line}\n_更新于: {ts}_\n"

        self._path.write_text(current.strip() + "\n", encoding="utf-8")
        logger.debug("追加项目记忆: %s/%s", section, line[:50])

    def initialize(self) -> None:
        """初始化项目记忆文件。"""
        if not self._path.exists():
            ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
            content = (
                "# 项目记忆\n\n"
                f"> 自动由 Agent 维护的项目知识文档。\n"
                f"> 初始化于: {ts}\n\n"
                "## 项目信息\n\n"
                "## 技术栈\n\n"
                "## 设计决策\n\n"
                "## 笔记\n\n"
            )
            self._path.write_text(content, encoding="utf-8")
            logger.info("初始化项目记忆")
