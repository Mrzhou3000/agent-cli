"""ToolRegistry 单元测试。"""

from __future__ import annotations

import pytest

from agent_cli.tools.base import SafetyLevel
from agent_cli.tools.bash import BashTool
from agent_cli.tools.file import GlobTool, GrepTool, ReadTool, WriteTool
from agent_cli.tools.registry import ToolRegistry


class TestToolRegistry:
    """ToolRegistry 核心功能测试。"""

    def test_register_and_execute(self):
        """测试注册和执行。"""
        r = ToolRegistry()
        r.register(BashTool())
        result = r.execute("bash", command="echo hello")
        assert result["stdout"].strip() == "hello"

    def test_register_duplicate_warning(self):
        """测试重复注册不报错（覆盖并产生警告）。"""
        r = ToolRegistry()
        r.register(BashTool())
        r.register(BashTool())  # 不应抛出异常
        assert len(r) == 1

    def test_execute_unknown_tool(self):
        """测试执行未注册工具。"""
        r = ToolRegistry()
        with pytest.raises(KeyError):
            r.execute("nonexistent")

    def test_schemas_generation(self):
        """测试 Schema 生成。"""
        r = ToolRegistry()
        r.register(BashTool())
        r.register(ReadTool())
        schemas = r.schemas()
        assert len(schemas) == 2
        for s in schemas:
            assert "name" in s
            assert "description" in s
            assert "input_schema" in s

    def test_contains(self):
        """测试 __contains__。"""
        r = ToolRegistry()
        r.register(GlobTool())
        assert "glob" in r
        assert "nonexistent" not in r

    def test_tool_names_property(self):
        """测试 tool_names 属性。"""
        r = ToolRegistry()
        r.register(GrepTool())
        r.register(WriteTool())
        names = r.tool_names
        assert "grep" in names
        assert "write" in names

    def test_bash_safety(self):
        """Bash 工具安全过滤。"""
        tool = BashTool()
        result = tool.execute(command="rm -rf /")
        assert result["exit_code"] == -1
        assert "安全拒绝" in result["stderr"]

    def test_safety_level_enum(self):
        """SafetyLevel 枚举值。"""
        assert SafetyLevel.SAFE.value == "safe"
        assert SafetyLevel.SENSITIVE.value == "sensitive"
        assert SafetyLevel.DANGEROUS.value == "dangerous"
        assert SafetyLevel.ALWAYS_ASK.value == "always_ask"
