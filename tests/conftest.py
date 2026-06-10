"""pytest 共享 fixtures。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from agent_cli.core.provider import MockProvider
from agent_cli.tools.bash import BashTool
from agent_cli.tools.file import GlobTool, GrepTool, ReadTool, WriteTool
from agent_cli.tools.registry import ToolRegistry


@pytest.fixture
def mock_provider() -> MockProvider:
    """MockProvider fixture。"""
    return MockProvider()


@pytest.fixture
def tool_registry() -> ToolRegistry:
    """预置 7 个核心工具的 ToolRegistry fixture。"""
    r = ToolRegistry()
    r.register(BashTool())
    r.register(ReadTool())
    r.register(WriteTool())
    r.register(GlobTool())
    r.register(GrepTool())
    r.register(WriteTool())
    return r


@pytest.fixture
def temp_dir() -> Path:
    """临时目录 fixture。"""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)
