"""文件操作工具集 — Read / Write / Edit / Glob / Grep。

安全机制（来源：14days-build）：
  - cwd 边界：所有操作限制在 allowed_dir 内
  - 编码安全：自动处理 UTF-8 编码
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .base import BaseTool, SafetyLevel, ToolSpec

logger = logging.getLogger(__name__)


class _BaseFileTool(BaseTool):
    """文件工具基类，提供路径安全检查。"""

    def __init__(self, allowed_dir: str | None = None):
        self.allowed_dir = Path(allowed_dir or os.getcwd()).resolve()

    def _resolve_path(self, path: str) -> Path:
        """解析并验证路径是否在允许范围内。"""
        p = Path(path)
        if not p.is_absolute():
            p = self.allowed_dir / p
        p = p.resolve()

        # cwd 边界检查
        if not str(p).startswith(str(self.allowed_dir)):
            raise PermissionError(f"路径 '{path}' 超出了允许目录范围 ({self.allowed_dir})")
        return p


class ReadTool(_BaseFileTool):
    """读取文件内容。"""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="read",
            description="读取指定文件的内容。支持文本文件，自动 UTF-8 编码。返回文件内容及其行数。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（相对或绝对路径）",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "起始行号（从 1 开始，可选）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "读取行数上限（可选）",
                    },
                },
                "required": ["path"],
            },
            handler=self.execute,
            safety=SafetyLevel.SAFE,
        )

    def execute(  # type: ignore[override]
        self, path: str, offset: int | None = None, limit: int | None = None, **kwargs: Any
    ) -> dict:
        full_path = self._resolve_path(path)
        if not full_path.exists():
            return {"error": f"文件不存在: {path}", "content": ""}
        if not full_path.is_file():
            return {"error": f"路径不是文件: {path}", "content": ""}

        try:
            content = full_path.read_text(encoding="utf-8")
            lines = content.splitlines(keepends=True)
            total_lines = len(lines)

            # 按 offset/limit 截取
            if offset is not None:
                start = max(0, offset - 1)
                lines = lines[start:]
            if limit is not None:
                lines = lines[:limit]

            result = "".join(lines)
            logger.info("读取文件: %s (%d 行)", path, total_lines)
            return {
                "content": result,
                "total_lines": total_lines,
                "path": str(full_path),
            }
        except UnicodeDecodeError:
            return {"error": f"文件不是有效的 UTF-8 文本: {path}", "content": ""}
        except Exception as e:
            logger.error("读取文件失败: %s — %s", path, e)
            return {"error": str(e), "content": ""}


class WriteTool(_BaseFileTool):
    """写入/创建文件。"""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="write",
            description="写入或创建文件。如果文件已存在则覆盖。此操作不可逆，请谨慎使用。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（相对或绝对路径）",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文件内容",
                    },
                },
                "required": ["path", "content"],
            },
            handler=self.execute,
            safety=SafetyLevel.SENSITIVE,
        )

    def execute(  # type: ignore[override]
        self, path: str, content: str, **kwargs: Any
    ) -> dict:
        full_path = self._resolve_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            full_path.write_text(content, encoding="utf-8")
            logger.info("写入文件: %s (%d 字符)", path, len(content))
            return {"success": True, "path": str(full_path), "chars": len(content)}
        except Exception as e:
            logger.error("写入文件失败: %s — %s", path, e)
            return {"error": str(e)}


class EditTool(_BaseFileTool):
    """编辑文件 — 精确替换。"""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="edit",
            description="编辑文件：在文件中查找精确的旧字符串并替换为新字符串。"
            "操作前文件必须已被读取过。支持 replace_all 替换所有匹配项。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "要替换的旧文本（必须精确匹配）",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "替换后的新文本",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "是否替换所有匹配项（默认 false）",
                        "default": False,
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
            handler=self.execute,
            safety=SafetyLevel.SENSITIVE,
        )

    def execute(  # type: ignore[override]
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        **kwargs: Any,
    ) -> dict:
        full_path = self._resolve_path(path)
        if not full_path.exists():
            return {"error": f"文件不存在: {path}"}

        try:
            content = full_path.read_text(encoding="utf-8")

            if old_string not in content:
                return {
                    "error": f"未找到匹配的文本: '{old_string[:50]}...'",
                    "hint": "建议先用 read 查看文件实际内容",
                }

            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                new_content = content.replace(old_string, new_string, 1)

            count = content.count(old_string)
            full_path.write_text(new_content, encoding="utf-8")
            replacements = min(count, 1 if not replace_all else count)
            logger.info("编辑文件: %s (%d 处替换)", path, replacements)
            return {"success": True, "path": str(full_path), "replacements": count}
        except Exception as e:
            logger.error("编辑文件失败: %s — %s", path, e)
            return {"error": str(e)}


class GlobTool(_BaseFileTool):
    """文件通配匹配。"""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="glob",
            description="使用 glob 模式查找文件。返回匹配文件路径列表。"
            "支持 ** 递归匹配（如 '**/*.py'）。",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "glob 匹配模式，如 '**/*.py'、'src/**/*.ts'",
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索根目录（可选，默认项目根目录）",
                    },
                },
                "required": ["pattern"],
            },
            handler=self.execute,
            safety=SafetyLevel.SAFE,
        )

    def execute(  # type: ignore[override]
        self, pattern: str, path: str | None = None, **kwargs: Any
    ) -> dict:
        search_dir = self._resolve_path(path) if path else self.allowed_dir

        try:
            matches = list(search_dir.glob(pattern))
            # 按修改时间排序
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            result = [str(m.relative_to(self.allowed_dir)) for m in matches]
            logger.info("Glob 搜索: %s → %d 个结果", pattern, len(result))
            return {"files": result, "count": len(result), "pattern": pattern}
        except Exception as e:
            logger.error("Glob 搜索失败: %s — %s", pattern, e)
            return {"error": str(e), "files": [], "count": 0}


class GrepTool(_BaseFileTool):
    """文件内容搜索。"""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="grep",
            description="搜索文件内容。返回匹配行及其行号。支持正则表达式搜索。",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "搜索模式（正则表达式）。如 'TODO'、'def\\s+\\w+'",
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索根目录（可选，默认项目根目录）",
                    },
                    "glob": {
                        "type": "string",
                        "description": "文件过滤模式（可选），如 '*.py'、'*.{ts,tsx}'",
                    },
                },
                "required": ["pattern"],
            },
            handler=self.execute,
            safety=SafetyLevel.SAFE,
        )

    def execute(  # type: ignore[override]
        self, pattern: str, path: str | None = None, glob: str | None = None, **kwargs: Any
    ) -> dict:
        search_dir = self._resolve_path(path) if path else self.allowed_dir

        try:
            import re as re_mod

            compiled = re_mod.compile(pattern)
            results: list[dict] = []
            file_count = 0

            # 收集需要搜索的文件
            if glob:
                files = list(search_dir.rglob(glob))
            else:
                files = list(search_dir.rglob("*"))
                files = [f for f in files if f.is_file() and not f.name.startswith(".")]

            for file_path in files:
                if not file_path.is_file():
                    continue
                try:
                    rel_path = str(file_path.relative_to(self.allowed_dir))
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    for i, line in enumerate(content.splitlines(), 1):
                        if compiled.search(line):
                            results.append({"file": rel_path, "line": i, "content": line.strip()})
                    if any(r["file"] == rel_path for r in results):
                        file_count += 1
                except Exception:
                    continue

            logger.info("Grep 搜索: %s → %d 行 (在 %d 个文件中)", pattern, len(results), file_count)
            return {
                "matches": results,
                "count": len(results),
                "files_count": file_count,
                "pattern": pattern,
            }
        except re_mod.error as e:
            return {"error": f"正则表达式错误: {e}", "matches": [], "count": 0}
        except Exception as e:
            logger.error("Grep 搜索失败: %s — %s", pattern, e)
            return {"error": str(e), "matches": [], "count": 0}
