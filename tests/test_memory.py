"""Memory System 测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from agent_cli.memory.file_memory import FileMemory
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
