"""文件工具集单元测试 — Read / Write / Edit / Glob / Grep。

目标模块: src/agent_cli/tools/file.py
当前覆盖率: 24% → 目标 88%

测试策略：使用 temp_dir fixture 做真实的文件系统 IO 操作。
所有工具都继承 _BaseFileTool，共享 _resolve_path 安全检查。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_cli.tools.file import (
    EditTool,
    GlobTool,
    GrepTool,
    ReadTool,
    WriteTool,
)

# ═══════════════════════════════════════════════════════════════════════════════
# _BaseFileTool 基础路径安全
# ═══════════════════════════════════════════════════════════════════════════════


class TestBaseFileTool:
    """_BaseFileTool 路径解析和安全检查（通过 ReadTool 测试，因基类为抽象类）。"""

    @pytest.fixture
    def tool(self, temp_dir: Path) -> ReadTool:
        return ReadTool(allowed_dir=str(temp_dir))

    def test_resolve_relative_path(self, tool: ReadTool, temp_dir: Path):
        """相对路径应基于 allowed_dir 解析。"""
        resolved = tool._resolve_path("sub/file.txt")
        assert str(resolved) == str(temp_dir / "sub" / "file.txt")

    def test_resolve_absolute_path_within_allowed(self, tool: ReadTool, temp_dir: Path):
        """绝对路径在 allowed_dir 内应通过。"""
        target = temp_dir / "test.txt"
        target.touch()
        resolved = tool._resolve_path(str(target))
        assert str(resolved) == str(target)

    def test_resolve_path_outside_allowed(self, tool: ReadTool, temp_dir: Path):
        """路径超出 allowed_dir 应抛出 PermissionError。"""
        outside = temp_dir.parent / "outside.txt"
        with pytest.raises(PermissionError):
            tool._resolve_path(str(outside))

    def test_resolve_path_traversal(self, tool: ReadTool, temp_dir: Path):
        """路径穿越（../）超出 allowed_dir 应抛出 PermissionError。"""
        with pytest.raises(PermissionError):
            tool._resolve_path("../outside")

    def test_default_allowed_dir(self):
        """默认 allowed_dir 为当前工作目录。"""
        tool = ReadTool()
        assert tool.allowed_dir == Path(os.getcwd()).resolve()


# ═══════════════════════════════════════════════════════════════════════════════
# ReadTool 读取文件
# ═══════════════════════════════════════════════════════════════════════════════


class TestReadTool:
    """ReadTool 文件读取测试。"""

    @pytest.fixture
    def tool(self, temp_dir: Path) -> ReadTool:
        return ReadTool(allowed_dir=str(temp_dir))

    @pytest.fixture
    def sample_file(self, temp_dir: Path) -> Path:
        """创建包含 5 行文本的示例文件。"""
        f = temp_dir / "sample.txt"
        f.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")
        return f

    def test_read_full_file(self, tool: ReadTool, sample_file: Path):
        """读取完整文件应返回全部内容和行数。"""
        result = tool.execute(path=str(sample_file))
        assert result["total_lines"] == 5
        assert "line1" in result["content"]
        assert result["content"].count("\n") == 5

    def test_read_with_offset(self, tool: ReadTool, sample_file: Path):
        """offset=3 应从第 3 行开始。"""
        result = tool.execute(path=str(sample_file), offset=3)
        assert result["content"].startswith("line3")
        assert "line1" not in result["content"]

    def test_read_with_limit(self, tool: ReadTool, sample_file: Path):
        """limit=2 应只返回前 2 行。"""
        result = tool.execute(path=str(sample_file), limit=2)
        lines = result["content"].strip().split("\n")
        assert len(lines) == 2
        assert lines[0] == "line1"

    def test_read_with_offset_and_limit(self, tool: ReadTool, sample_file: Path):
        """offset=2, limit=2 应返回第 2-3 行。"""
        result = tool.execute(path=str(sample_file), offset=2, limit=2)
        lines = result["content"].strip().split("\n")
        assert len(lines) == 2
        assert lines[0] == "line2"
        assert lines[1] == "line3"

    def test_read_file_not_exists(self, tool: ReadTool):
        """文件不存在应返回 error。"""
        result = tool.execute(path="nonexistent.txt")
        assert "error" in result
        assert "不存在" in result["error"]

    def test_read_path_is_directory(self, tool: ReadTool, temp_dir: Path):
        """路径是目录时应返回 error。"""
        result = tool.execute(path=str(temp_dir))
        assert "error" in result
        assert "不是文件" in result["error"]

    def test_read_empty_file(self, tool: ReadTool, temp_dir: Path):
        """空文件应返回空内容和行数 0。"""
        f = temp_dir / "empty.txt"
        f.touch()
        result = tool.execute(path=str(f))
        assert result["total_lines"] == 0
        assert result["content"] == ""

    def test_read_returns_full_path(self, tool: ReadTool, sample_file: Path):
        """返回结果应包含文件的绝对路径。"""
        result = tool.execute(path=str(sample_file))
        assert result["path"] == str(sample_file.resolve())


# ═══════════════════════════════════════════════════════════════════════════════
# WriteTool 写入文件
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteTool:
    """WriteTool 文件写入测试。"""

    @pytest.fixture
    def tool(self, temp_dir: Path) -> WriteTool:
        return WriteTool(allowed_dir=str(temp_dir))

    def test_write_new_file(self, tool: WriteTool, temp_dir: Path):
        """写入新文件应成功，文件实际存在。"""
        path = str(temp_dir / "new.txt")
        result = tool.execute(path=path, content="hello world")
        assert result["success"] is True
        assert (temp_dir / "new.txt").read_text() == "hello world"

    def test_write_overwrite(self, tool: WriteTool, temp_dir: Path):
        """覆盖已有文件应成功。"""
        f = temp_dir / "existing.txt"
        f.write_text("old content")
        result = tool.execute(path=str(f), content="new content")
        assert result["success"] is True
        assert f.read_text() == "new content"

    def test_write_empty_content(self, tool: WriteTool, temp_dir: Path):
        """写入空内容应创建空文件。"""
        path = str(temp_dir / "empty.txt")
        result = tool.execute(path=path, content="")
        assert result["success"] is True
        assert result["chars"] == 0

    def test_write_creates_subdirs(self, tool: WriteTool, temp_dir: Path):
        """写入时中间目录不存在应自动创建。"""
        path = str(temp_dir / "a" / "b" / "deep.txt")
        result = tool.execute(path=path, content="deep")
        assert result["success"] is True
        assert (temp_dir / "a" / "b" / "deep.txt").exists()

    def test_write_chars_count(self, tool: WriteTool, temp_dir: Path):
        """返回的 chars 应等于写入字符数。"""
        path = str(temp_dir / "count.txt")
        result = tool.execute(path=path, content="12345")
        assert result["chars"] == 5


# ═══════════════════════════════════════════════════════════════════════════════
# EditTool 编辑文件
# ═══════════════════════════════════════════════════════════════════════════════


class TestEditTool:
    """EditTool 文件编辑测试。"""

    @pytest.fixture
    def tool(self, temp_dir: Path) -> EditTool:
        return EditTool(allowed_dir=str(temp_dir))

    @pytest.fixture
    def sample_file(self, temp_dir: Path) -> Path:
        f = temp_dir / "edit.txt"
        f.write_text("aaa bbb aaa bbb aaa\n", encoding="utf-8")
        return f

    def test_edit_single(self, tool: EditTool, sample_file: Path):
        """replace_all=False 只替换第一次出现。"""
        result = tool.execute(path=str(sample_file), old_string="aaa", new_string="xxx")
        assert result["success"] is True
        content = sample_file.read_text()
        assert content == "xxx bbb aaa bbb aaa\n"

    def test_edit_replace_all(self, tool: EditTool, sample_file: Path):
        """replace_all=True 替换所有匹配。"""
        result = tool.execute(
            path=str(sample_file),
            old_string="aaa",
            new_string="xxx",
            replace_all=True,
        )
        assert result["success"] is True
        content = sample_file.read_text()
        assert content == "xxx bbb xxx bbb xxx\n"

    def test_edit_file_not_found(self, tool: EditTool, temp_dir: Path):
        """文件不存在应返回 error。"""
        result = tool.execute(
            path=str(temp_dir / "nope.txt"),
            old_string="old",
            new_string="new",
        )
        assert "error" in result
        assert "不存在" in result["error"]

    def test_edit_string_not_found(self, tool: EditTool, sample_file: Path):
        """old_string 不存在应返回 error 和 hint。"""
        result = tool.execute(
            path=str(sample_file),
            old_string="zzz",
            new_string="xxx",
        )
        assert "error" in result
        assert "未找到匹配" in result["error"]
        assert "hint" in result

    def test_edit_multiple_occurrences_count(self, tool: EditTool, sample_file: Path):
        """返回的 replacements 应为总匹配数（非替换数）。"""
        result = tool.execute(
            path=str(sample_file),
            old_string="bbb",
            new_string="yyy",
            replace_all=True,
        )
        # "bbb" 在编辑文件中出现 2 次
        assert result["replacements"] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# GlobTool 文件通配匹配
# ═══════════════════════════════════════════════════════════════════════════════


class TestGlobTool:
    """GlobTool 文件查找测试。"""

    @pytest.fixture
    def tool(self, temp_dir: Path) -> GlobTool:
        return GlobTool(allowed_dir=str(temp_dir))

    @pytest.fixture
    def dir_with_files(self, temp_dir: Path):
        """创建含多个文件的目录结构。"""
        (temp_dir / "a.py").touch()
        (temp_dir / "b.py").touch()
        (temp_dir / "c.txt").touch()
        sub = temp_dir / "sub"
        sub.mkdir()
        (sub / "d.py").touch()
        return temp_dir

    def test_glob_all_py(self, tool: GlobTool, dir_with_files: Path):
        """glob **/*.py 应找到所有 .py 文件。"""
        result = tool.execute(pattern="**/*.py")
        assert result["count"] >= 3
        assert any(f.endswith("a.py") for f in result["files"])
        assert any("sub" in f and f.endswith("d.py") for f in result["files"])

    def test_glob_no_match(self, tool: GlobTool, dir_with_files: Path):
        """无匹配时应返回空列表和 count=0。"""
        result = tool.execute(pattern="**/*.rs")
        assert result["count"] == 0
        assert result["files"] == []

    def test_glob_custom_path(self, tool: GlobTool, dir_with_files: Path):
        """指定 path 参数应限制搜索范围。"""
        sub = dir_with_files / "sub"
        result = tool.execute(pattern="*.py", path=str(sub))
        assert result["count"] >= 1
        assert all("sub" in f or not f.startswith("..") for f in result["files"])


# ═══════════════════════════════════════════════════════════════════════════════
# GrepTool 文件内容搜索
# ═══════════════════════════════════════════════════════════════════════════════


class TestGrepTool:
    """GrepTool 文件内容搜索测试。"""

    @pytest.fixture
    def tool(self, temp_dir: Path) -> GrepTool:
        return GrepTool(allowed_dir=str(temp_dir))

    @pytest.fixture
    def dir_with_content(self, temp_dir: Path):
        """创建含特定内容的文件。"""
        py_file = temp_dir / "hello.py"
        py_file.write_text("print('hello world')\n# TODO: refactor\n", encoding="utf-8")
        txt_file = temp_dir / "note.txt"
        txt_file.write_text("hello there\ngeneral kenobi\n", encoding="utf-8")
        return temp_dir

    def test_grep_find_matches(self, tool: GrepTool, dir_with_content: Path):
        """搜索 'hello' 应返回所有含 hello 的行。"""
        result = tool.execute(pattern="hello")
        assert result["count"] >= 2  # hello.py 和 note.txt 都有
        assert result["files_count"] >= 2

    def test_grep_with_glob(self, tool: GrepTool, dir_with_content: Path):
        """指定 glob=*.py 应只搜索 .py 文件。"""
        result = tool.execute(pattern="hello", glob="*.py")
        assert result["count"] >= 1
        assert result["files_count"] >= 1
        # 验证结果都在 .py 文件中
        for m in result["matches"]:
            assert m["file"].endswith(".py")

    def test_grep_no_match(self, tool: GrepTool, dir_with_content: Path):
        """无匹配时应返回 count=0。"""
        result = tool.execute(pattern="NONEXISTENT__PATTERN")
        assert result["count"] == 0
        assert result["matches"] == []

    def test_grep_invalid_regex(self, tool: GrepTool, dir_with_content: Path):
        """非法正则应返回 error。"""
        result = tool.execute(pattern="[invalid")
        assert "error" in result
        assert "正则表达式错误" in result["error"]
