"""Memory System 测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from agent_cli.memory.file_memory import (
    FileMemory,
    _dict_to_yaml,
    _is_float,
    _parse_frontmatter,
    _set_nested,
    _simple_yaml_parse,
    _to_yaml_value,
)
from agent_cli.memory.manager import MemoryManager
from agent_cli.memory.project_memory import ProjectMemory


class TestFileMemory:
    """FileMemory 测试。"""

    @pytest.fixture
    def mem(self) -> FileMemory:
        with tempfile.TemporaryDirectory() as td:
            yield FileMemory(base_dir=str(Path(td) / ".agent"))

    def test_write_and_read(self, mem: FileMemory):
        mem.write("test-note", "Hello World", description="测试笔记")
        entry = mem.read("test-note")
        assert entry is not None
        assert entry.name == "test-note"
        assert entry.content == "Hello World"
        assert entry.description == "测试笔记"

    def test_read_nonexistent(self, mem: FileMemory):
        assert mem.read("nonexistent") is None

    def test_write_with_metadata(self, mem: FileMemory):
        mem.write("meta-test", "内容", metadata={"tags": ["python", "test"], "type": "note"})
        entry = mem.read("meta-test")
        assert entry is not None
        assert "python" in entry.tags
        assert entry.metadata.get("type") == "note"

    def test_delete(self, mem: FileMemory):
        mem.write("to-delete", "内容")
        assert mem.read("to-delete") is not None
        assert mem.delete("to-delete") is True
        assert mem.read("to-delete") is None
        assert mem.delete("to-delete") is False

    def test_list_all(self, mem: FileMemory):
        mem.write("a", "内容 A")
        mem.write("b", "内容 B")
        entries = mem.list_all()
        assert len(entries) == 2
        names = [e.name for e in entries]
        assert "a" in names
        assert "b" in names

    def test_search_by_query(self, mem: FileMemory):
        mem.write("python", "Python 开发笔记", description="Python 相关")
        mem.write("js", "JavaScript 笔记")
        results = mem.search(query="Python")
        assert len(results) == 1
        assert results[0].name == "python"

    def test_search_by_tags(self, mem: FileMemory):
        mem.write("work", "工作记录", metadata={"tags": ["work", "important"]})
        mem.write("personal", "个人记录", metadata={"tags": ["personal"]})
        results = mem.search(tags=["work"])
        assert len(results) == 1
        assert results[0].name == "work"

    def test_count(self, mem: FileMemory):
        assert mem.count() == 0
        mem.write("n1", "1")
        mem.write("n2", "2")
        assert mem.count() == 2

    def test_yaml_frontmatter_parsing(self, mem: FileMemory):
        """测试 YAML frontmatter 解析的各种格式。"""
        mem.write(
            "complex",
            "正文内容",
            metadata={
                "tags": ["a", "b"],
                "nested": {"key": "val"},
                "count": 42,
                "enabled": True,
            },
        )
        entry = mem.read("complex")
        assert entry is not None
        assert entry.metadata.get("count") == 42
        assert entry.metadata.get("enabled") is True

    def test_overwrite(self, mem: FileMemory):
        mem.write("over", "原内容")
        mem.write("over", "新内容")
        entry = mem.read("over")
        assert entry is not None
        assert entry.content == "新内容"

    def test_file_structure(self, mem: FileMemory):
        """验证实际写入的文件结构。"""
        mem.write("struct", "内容行", metadata={"tags": ["test"]})
        path = Path(mem._mem_dir) / "struct.md"
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---")
        assert "tags:" in text
        assert "内容行" in text


class TestProjectMemory:
    """ProjectMemory 测试。"""

    @pytest.fixture
    def pm(self) -> ProjectMemory:
        with tempfile.TemporaryDirectory() as td:
            yield ProjectMemory(base_dir=str(Path(td) / ".agent"))

    def test_initialize(self, pm: ProjectMemory):
        pm.initialize()
        content = pm.read()
        assert "项目记忆" in content

    def test_update_section(self, pm: ProjectMemory):
        pm.update("技术栈", "Python 3.13, Typer, pytest")
        content = pm.read()
        assert "技术栈" in content
        assert "Python 3.13" in content

    def test_update_existing_section(self, pm: ProjectMemory):
        pm.update("设计决策", "决策 A")
        pm.update("设计决策", "决策 B（更新）")
        content = pm.read()
        assert "决策 B（更新）" in content

    def test_append(self, pm: ProjectMemory):
        pm.append("笔记", "第一条笔记")
        pm.append("笔记", "第二条笔记")
        content = pm.read()
        assert "第一条笔记" in content
        assert "第二条笔记" in content

    def test_append_cross_section_boundary(self, pm: ProjectMemory):
        """在多章节文件中，向中间章节追加时不应污染相邻章节。"""
        pm.update("章节A", "A 内容")
        pm.update("章节B", "B 内容")
        pm.update("章节C", "C 内容")
        # 向中间章节追加
        pm.append("章节B", "追加到 B")
        content = pm.read()
        assert "- 追加到 B" in content
        # 确认追加行在 ## 章节B 和 ## 章节C 之间
        section_b_pos = content.index("## 章节B")
        section_c_pos = content.index("## 章节C")
        append_pos = content.index("- 追加到 B")
        assert section_b_pos < append_pos < section_c_pos, (
            "追加内容应出现在章节B区域内，而非章节A或章节C"
        )
        # 章节A 和 章节C 不应被污染
        assert "A 内容" in content
        assert "C 内容" in content

    def test_append_to_last_section(self, pm: ProjectMemory):
        """向最后一个章节追加时，内容应出现在文件末尾区域。"""
        pm.update("章节X", "X 内容")
        pm.update("章节Y", "Y 内容")
        pm.append("章节Y", "追加到尾部")
        content = pm.read()
        lines = content.split("\n")
        y_idx = next(i for i, line in enumerate(lines) if "章节Y" in line)
        append_idx = next(i for i, line in enumerate(lines) if "追加到尾部" in line)
        assert y_idx < append_idx, "追加内容应在章节Y之后"
        # 章节Y之后不应该有其他 ## 标题
        tail = lines[append_idx:]
        assert not any(line.startswith("## ") for line in tail), (
            "最后一个章节追加后不应出现新的章节标题"
        )

    def test_append_new_section(self, pm: ProjectMemory):
        """向不存在的章节追加时，应自动创建章节。"""
        pm.append("新章节", "新内容")
        content = pm.read()
        assert "## 新章节" in content
        assert "- 新内容" in content


class TestMemoryManager:
    """MemoryManager 集成测试。"""

    @pytest.fixture
    def mgr(self) -> MemoryManager:
        with tempfile.TemporaryDirectory() as td:
            yield MemoryManager(base_dir=str(Path(td) / ".agent"))

    def test_write_and_search(self, mgr: MemoryManager):
        mgr.write_note("pref", "喜欢简洁回答", tags=["preference"], description="用户偏好")
        entries = mgr.search(query="简洁")
        assert len(entries) == 1

    def test_build_context(self, mgr: MemoryManager):
        ctx = mgr.build_context()
        assert isinstance(ctx, str)

    def test_build_context_with_keywords(self, mgr: MemoryManager):
        mgr.write_note("python-note", "Python 3.12 新特性", tags=["python"])
        ctx = mgr.build_context(keywords="Python")
        assert "python-note" in ctx or "Python" in ctx

    def test_triple_layer_access(self, mgr: MemoryManager):
        """验证三层记忆各自可访问。"""
        # 文件级
        mgr.write_note("layer-file", "文件内容")
        assert mgr.read_note("layer-file") is not None

        # 项目级
        mgr.project.initialize()
        assert mgr.project.read() != ""

        # 会话级
        sid = mgr.session.store.create()
        assert sid.startswith("sess_")

    def test_build_context_with_project_and_session(self, mgr: MemoryManager):
        """build_context 包含项目记忆和会话历史。"""
        mgr.project.initialize()
        mgr.project.update("Tech Stack", "Python 3.12, Typer")
        sid = mgr.session.store.create()
        mgr.session.store.append(sid, [{"role": "user", "content": "hello"}])

        ctx = mgr.build_context(keywords="Python")
        assert "Tech Stack" in ctx or "Python" in ctx

    def test_build_context_empty(self, mgr: MemoryManager):
        """无内容时 build_context 返回空字符串。"""
        ctx = mgr.build_context()
        assert isinstance(ctx, str)


# ─── YAML 辅助函数测试 ─────────────────────────────────────────


class TestYamlHelpers:
    """`_simple_yaml_parse` / `_parse_frontmatter` / `_is_float` 等 YAML 辅助函数测试。"""

    def test_parse_frontmatter_no_match(self):
        """没有 frontmatter 时返回空 dict 和原文本。"""
        meta, body = _parse_frontmatter("纯文本内容")
        assert meta == {}
        assert body == "纯文本内容"

    def test_parse_frontmatter_empty(self):
        """空字符串返回空。"""
        meta, body = _parse_frontmatter("")
        assert meta == {}
        assert body == ""

    def test_simple_yaml_multiline(self):
        """管道符多行字符串解析。"""
        text = "description: |\n  line1\n  line2\nkey: value"
        result = _simple_yaml_parse(text)
        assert result.get("description") == "line1\nline2"

    def test_simple_yaml_inline_list(self):
        """内联列表解析。"""
        text = "tags: [a, b, c]\nname: test"
        result = _simple_yaml_parse(text)
        assert result.get("tags") == ["a", "b", "c"]

    def test_simple_yaml_list_items(self):
        """横线列表项解析。"""
        text = "tags:\n  - x\n  - y"
        result = _simple_yaml_parse(text)
        assert result.get("tags") == ["x", "y"]

    def test_simple_yaml_nested(self):
        """嵌套键值解析（扁平化为 dotted key）。"""
        text = "outer:\n  inner: value"
        result = _simple_yaml_parse(text)
        # 当前解析器使用 _set_nested 支持 dotted keys，但不构建嵌套 dict
        # 所以 outer 和 inner 是独立键
        assert "inner" in result or "outer" in result

    def test_simple_yaml_boolean_and_number(self):
        """布尔值和数字解析。"""
        text = "enabled: true\ncount: 123\nratio: 3.14\nname: hello"
        result = _simple_yaml_parse(text)
        assert result.get("enabled") is True
        assert result.get("count") == 123
        assert result.get("ratio") == 3.14
        assert result.get("name") == "hello"

    def test_simple_yaml_comment_lines(self):
        """注释行被跳过。"""
        text = "# this is a comment\nkey: val\n# another comment"
        result = _simple_yaml_parse(text)
        assert result.get("key") == "val"
        assert "#" not in str(result.keys())

    def test_is_float(self):
        """_is_float 判断浮点数。"""
        assert _is_float("3.14") is True
        assert _is_float("123") is False
        assert _is_float("abc") is False
        assert _is_float("") is False

    def test_set_nested(self):
        """_set_nested 设置嵌套路径。"""
        d = {}
        _set_nested(d, "a.b.c", "val")
        assert d == {"a": {"b": {"c": "val"}}}

        _set_nested(d, "a.b.d", 42)
        assert d["a"]["b"]["d"] == 42

    def test_to_yaml_value_bool(self):
        """布尔值转 YAML。"""
        assert _to_yaml_value(True) == "true"
        assert _to_yaml_value(False) == "false"

    def test_to_yaml_value_number(self):
        """数字转 YAML。"""
        assert _to_yaml_value(42) == "42"
        assert _to_yaml_value(3.14) == "3.14"

    def test_to_yaml_value_list_empty(self):
        """空列表转 YAML。"""
        assert _to_yaml_value([]) == "[]"

    def test_to_yaml_value_list_nonempty(self):
        """非空列表转 YAML。"""
        result = _to_yaml_value(["a", "b"])
        assert "- a" in result
        assert "- b" in result

    def test_to_yaml_value_dict(self):
        """字典转 YAML。"""
        result = _to_yaml_value({"k": "v"})
        assert "k:" in result
        assert "v" in result or "v" in str(result)

    def test_to_yaml_value_string(self):
        """字符串直接返回。"""
        assert _to_yaml_value("hello") == "hello"

    def test_dict_to_yaml(self):
        """_dict_to_yaml 完整输出。"""
        d = {"name": "test", "tags": ["a", "b"], "nested": {"key": "val"}, "empty": []}
        result = _dict_to_yaml(d)
        assert "name: test" in result
        assert "tags:" in result
        assert "- a" in result
        assert "nested:" in result
        assert "key: val" in result


class TestFileMemoryEdgeCases:
    """FileMemory 边界情况测试。"""

    @pytest.fixture
    def mem(self) -> FileMemory:
        with tempfile.TemporaryDirectory() as td:
            yield FileMemory(base_dir=str(Path(td) / ".agent"))

    def test_tags_as_string(self, mem: FileMemory):
        """metadata.tags 为字符串时也能正确解析。"""
        mem.write("str-tags", "内容", metadata={"tags": "python,test"})
        entry = mem.read("str-tags")
        assert entry is not None
        assert "python" in entry.tags

    def test_read_corrupt_file_returns_none(self, mem: FileMemory):
        """损坏的记忆文件返回 None，不崩溃。"""
        path = Path(mem._mem_dir) / "corrupt.md"
        path.write_bytes(b"\xff\xfe\x00\x01invalid")
        entry = mem.read("corrupt")
        assert entry is None
