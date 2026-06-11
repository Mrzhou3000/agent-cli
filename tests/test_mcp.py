"""Tests for Phase 3 — MCP Bridge.

注意: MCP 测试不启动真实子进程，只测试配置加载和数据模型。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agent_cli.mcp.bridge import MCPError, MCPToolBridge
from agent_cli.mcp.models import MCPServerConfig, MCPToolDef


class TestMCPServerConfig:
    """MCPServerConfig 数据模型测试。"""

    def test_from_dict_full(self):
        """完整配置应正确加载。"""
        data = {
            "name": "filesystem",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
            "env": {"KEY": "value"},
        }
        config = MCPServerConfig.from_dict(data)
        assert config.name == "filesystem"
        assert config.transport == "stdio"
        assert config.command == "npx"
        assert len(config.args) == 3

    def test_from_dict_minimal(self):
        """最小配置应使用默认值。"""
        data = {"name": "test"}
        config = MCPServerConfig.from_dict(data)
        assert config.name == "test"
        assert config.transport == "stdio"
        assert config.args == []
        assert config.env == {}


class TestMCPToolDef:
    """MCPToolDef 数据模型测试。"""

    def test_basic_creation(self):
        """基本创建。"""
        tool = MCPToolDef(
            name="read_file",
            description="Read a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            server_name="filesystem",
        )
        assert tool.name == "read_file"
        assert tool.server_name == "filesystem"
        assert tool.input_schema["properties"]["path"]["type"] == "string"


class TestMCPToolBridge:
    """MCPToolBridge 配置加载测试。"""

    @pytest.fixture
    def bridge(self, tmp_path: Path) -> MCPToolBridge:
        """临时目录的 MCPToolBridge fixture。"""
        return MCPToolBridge(base_dir=str(tmp_path / ".agent"))

    def test_load_config_no_file(self, bridge: MCPToolBridge):
        """无配置文件应返回空列表。"""
        configs = bridge.load_config()
        assert configs == []

    def test_load_config_valid(self, tmp_path: Path, bridge: MCPToolBridge):
        """有效配置文件应正确解析。"""
        config_dir = tmp_path / ".agent"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "mcp.json"
        config_path.write_text(
            json.dumps(
                {
                    "mcp_servers": [
                        {
                            "name": "filesystem",
                            "transport": "stdio",
                            "command": "npx",
                            "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
                        },
                        {
                            "name": "github",
                            "transport": "stdio",
                            "command": "npx",
                            "args": ["-y", "@modelcontextprotocol/server-github"],
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        configs = bridge.load_config()
        assert len(configs) == 2
        assert configs[0].name == "filesystem"
        assert configs[1].name == "github"

    def test_load_config_invalid_json(self, tmp_path: Path, bridge: MCPToolBridge):
        """无效 JSON 应返回空列表。"""
        config_dir = tmp_path / ".agent"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "mcp.json").write_text("invalid json", encoding="utf-8")

        configs = bridge.load_config()
        assert configs == []

    def test_disconnect_all_empty(self, bridge: MCPToolBridge):
        """无连接时断开应不报错。"""
        # 不应抛出异常
        bridge.disconnect_all()

    def test_connect_no_servers(self, bridge: MCPToolBridge):
        """无服务器配置时连接应返回空。"""
        connected = bridge.connect_all()
        assert connected == []

    def test_discover_tools_no_connection(self, bridge: MCPToolBridge):
        """无连接时发现工具应返回空。"""
        tools = bridge.discover_tools()
        assert tools == []

    def test_mcp_error_message(self):
        """MCPError 应有正确的错误消息。"""
        err = MCPError("Connection failed")
        assert str(err) == "Connection failed"
