"""FileMemory — 文件级记忆。

设计哲学（来源：learn-claude-code）：
  文件级记忆是 Agent 的长期持久知识存储。
  使用 Markdown + YAML Frontmatter 格式，人类可读、Git 可追踪。

格式:
  ---
  name: user-preferences
  description: 用户偏好设置
  metadata:
    type: user
    created: 2026-06-10
    tags: [python, preferences]
  ---
  用户 prefers 使用中文回复
  用户工作在 Python/TypeScript 项目
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# YAML frontmatter 解析正则
_FM_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)


@dataclass
class MemoryEntry:
    """一条记忆条目。"""

    name: str
    description: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    file_path: str = ""

    @property
    def tags(self) -> list[str]:
        """获取标签列表。"""
        tags = self.metadata.get("tags", [])
        if isinstance(tags, str):
            return [t.strip() for t in tags.split(",")]
        return list(tags) if isinstance(tags, list) else []


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """解析 YAML frontmatter。

    Returns:
        (metadata_dict, body_text)
    """
    match = _FM_PATTERN.match(text)
    if not match:
        return {}, text.strip()

    raw_meta = match.group(1)
    body = match.group(2).strip()

    # 简易 YAML 解析（避免依赖 pyyaml）
    metadata = _simple_yaml_parse(raw_meta)
    return metadata, body


def _simple_yaml_parse(text: str) -> dict[str, Any]:
    """简易 YAML frontmatter 解析器。

    支持:
      - 字符串: key: value
      - 嵌套: key:
                sub: value
      - 列表: key: [a, b, c]  或   key:
                                        - a
                                        - b
      - 多行字符串: key: |
                      text
    """
    result: dict[str, Any] = {}
    lines = text.split("\n")
    current_key: str | None = None
    current_list: list[str] | None = None
    in_multiline = False
    multiline_key: str | None = None
    multiline_lines: list[str] = []
    stack: list[tuple[dict[str, Any], str | None]] = [(result, None)]

    for line in lines:
        stripped = line.strip()

        # 多行字符串内容
        if in_multiline:
            if stripped == "" or line.startswith("  "):
                multiline_lines.append(stripped)
                continue
            in_multiline = False
            if multiline_key:
                _set_nested(stack[-1][0], multiline_key, "\n".join(multiline_lines).strip())
            multiline_key = None
            multiline_lines = []

        # 空行或注释
        if not stripped or stripped.startswith("#"):
            continue

        # 列表项
        if stripped.startswith("- ") and current_key:
            current_list = current_list or []
            current_list.append(stripped[2:])
            continue

        # 如果有待处理的列表，保存它
        if current_list is not None and current_key:
            _set_nested(result, current_key, current_list)
            current_list = None

        # 冒号分隔
        if ":" in line:
            colon_pos = line.index(":")
            key = line[:colon_pos].strip()
            value_part = line[colon_pos + 1 :].strip()

            # 多行字符串标记
            if value_part == "|":
                in_multiline = True
                multiline_key = key
                multiline_lines = []
                current_key = key
                continue

            # 列表
            if value_part.startswith("[") and value_part.endswith("]"):
                items = [i.strip().strip("'\"") for i in value_part[1:-1].split(",")]
                _set_nested(result, key, items)
                current_key = key
                continue

            # 嵌套
            if not value_part:
                current_key = key
                continue

            # 普通值
            value: str | int | float | bool = value_part
            if isinstance(value, str):
                if value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                elif value.isdigit():
                    value = int(value)
                elif _is_float(value):
                    value = float(value)
                else:
                    value = value.strip("'\"")

            _set_nested(result, key, value)
            current_key = key

    # Flush
    if current_list is not None and current_key:
        _set_nested(result, current_key, current_list)
    if in_multiline and multiline_key:
        _set_nested(result, multiline_key, "\n".join(multiline_lines).strip())

    return result


def _is_float(s: str) -> bool:
    try:
        float(s)
        return "." in s
    except ValueError:
        return False


def _set_nested(d: dict, key: str, value: Any) -> None:
    """在嵌套字典中设置值（支持点号路径）。"""
    parts = key.split(".")
    for p in parts[:-1]:
        if p not in d:
            d[p] = {}
        d = d[p]
    d[parts[-1]] = value


def _to_yaml_value(value: Any, indent: int = 0) -> str:
    """将 Python 值格式化为 YAML 字符串。"""
    prefix = " " * indent
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        return "\n".join(f"{prefix}- {v}" for v in value)
    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            lines.append(f"{prefix}{k}:")
            lines.append(_to_yaml_value(v, indent + 2))
        return "\n".join(lines)
    return str(value)


def _dict_to_yaml(d: dict, indent: int = 0) -> str:
    """将字典格式化为 YAML 字符串。"""
    lines = []
    for key, value in d.items():
        prefix = " " * indent
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            lines.append(_dict_to_yaml(value, indent + 2))
        elif isinstance(value, list):
            if not value:
                lines.append(f"{prefix}{key}: []")
            else:
                lines.append(f"{prefix}{key}:")
                for item in value:
                    lines.append(f"{prefix}  - {item}")
        else:
            lines.append(f"{prefix}{key}: {_to_yaml_value(value)}")
    return "\n".join(lines)


class FileMemory:
    """文件级记忆管理器。

    管理 `.agent/memory/` 目录下的 Markdown+YAML 记忆文件。
    支持 CRUD、标签搜索、容量控制。

    Usage:
        mem = FileMemory(base_dir=".agent")
        mem.write("user-preferences", "用户喜欢 Python", {"type": "user"})
        entry = mem.read("user-preferences")
        entries = mem.search(tags=["python"])
    """

    def __init__(self, base_dir: str = ".agent"):
        self._mem_dir = Path(base_dir) / "memory"
        self._mem_dir.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        name: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        description: str = "",
    ) -> str:
        """写入一条记忆。

        Args:
            name: 记忆名称（用作文件名）。
            content: 记忆内容（Markdown 正文）。
            metadata: YAML frontmatter 元数据。
            description: 描述（写入 metadata.description）。

        Returns:
            文件路径。
        """
        meta = dict(metadata or {})
        if description:
            meta["description"] = description
        meta.setdefault("name", name)

        # 生成 frontmatter
        frontmatter = _dict_to_yaml(meta)
        full_content = f"---\n{frontmatter}\n---\n\n{content.strip()}\n"

        path = self._mem_dir / f"{name}.md"
        path.write_text(full_content, encoding="utf-8")
        logger.info("写入记忆: %s (%d 字符)", name, len(content))
        return str(path)

    def read(self, name: str) -> MemoryEntry | None:
        """读取一条记忆。

        Args:
            name: 记忆名称（不含 .md 后缀）。

        Returns:
            MemoryEntry 或 None（不存在时）。
        """
        path = self._mem_dir / f"{name}.md"
        if not path.exists():
            return None

        try:
            text = path.read_text(encoding="utf-8")
            metadata, body = _parse_frontmatter(text)
            return MemoryEntry(
                name=name,
                description=metadata.get("description", ""),
                content=body,
                metadata=metadata,
                file_path=str(path),
            )
        except Exception as e:
            logger.error("读取记忆失败: %s — %s", name, e)
            return None

    def delete(self, name: str) -> bool:
        """删除一条记忆。"""
        path = self._mem_dir / f"{name}.md"
        if path.exists():
            path.unlink()
            logger.info("删除记忆: %s", name)
            return True
        return False

    def list_all(self) -> list[MemoryEntry]:
        """列出所有记忆。"""
        entries: list[MemoryEntry] = []
        for path in sorted(self._mem_dir.glob("*.md")):
            name = path.stem
            entry = self.read(name)
            if entry:
                entries.append(entry)
        return entries

    def search(self, query: str = "", tags: list[str] | None = None) -> list[MemoryEntry]:
        """搜索记忆。

        Args:
            query: 全文搜索关键词（在内容和描述中匹配）。
            tags: 按标签筛选。

        Returns:
            匹配的记忆条目列表。
        """
        results = []
        for entry in self.list_all():
            # 标签筛选
            if tags:
                entry_tags = entry.tags
                if not any(t in entry_tags for t in tags):
                    continue

            # 全文搜索
            if query:
                q = query.lower()
                if q not in entry.content.lower() and q not in entry.description.lower():
                    continue

            results.append(entry)

        return results

    def count(self) -> int:
        """记忆数量。"""
        return len(list(self._mem_dir.glob("*.md")))
