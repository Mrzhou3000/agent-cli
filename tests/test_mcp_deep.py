"""MCP Bridge 深度测试 — MCPConnection + _MCPToolWrapper + 集成场景。

使用 mock 子进程测试 JSON-RPC 协议逻辑，不启动真实外部进程。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_cli.mcp.bridge import (
    MCPConnection,
    MCPError,
    MCPToolBridge,
    _MCPToolWrapper,
)
from agent_cli.mcp.models import MCPServerConfig, MCPToolDef
from agent_cli.tools.base import SafetyLevel, ToolSpec

# ─── Mock 辅助 ────────────────────────────────────────────────────


def _make_mock_process(
    responses: list[dict] | None = None,
) -> MagicMock:
    """创建一个模拟的 subprocess.Popen 对象。

    Args:
        responses: 预定义的 JSON-RPC 响应列表。每次 _send_request 消耗一个。

    Returns:
        配置好的 MagicMock。
    """
    proc = MagicMock()
    proc.poll.return_value = None  # 进程正在运行

    # 模拟 stdin
    proc.stdin = MagicMock()

    # 模拟 stdout.readline — 依次返回预定义的响应行
    if responses:
        response_lines = [json.dumps(r) + "\n" for r in responses]
        proc.stdout.readline.side_effect = response_lines
    else:
        # 默认返回一个有效的 initialize 响应
        proc.stdout.readline.return_value = (
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "mock"}}})
            + "\n"
        )

    return proc


@pytest.fixture
def mock_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="test-server",
        command="python",
        args=["-m", "some_mcp_server"],
        env={"KEY": "val"},
    )


# ─── MCPConnection 测试 ──────────────────────────────────────────


class TestMCPConnectionInit:
    """MCPConnection 初始化测试。"""

    def test_init_stores_config(self, mock_config: MCPServerConfig):
        conn = MCPConnection(mock_config)
        assert conn.config is mock_config
        assert conn._process is None
        assert conn._request_id == 0

    def test_is_connected_initially_false(self, mock_config: MCPServerConfig):
        conn = MCPConnection(mock_config)
        assert conn.is_connected is False


class TestMCPConnectionConnect:
    """MCPConnection.connect() 测试。"""

    def test_connect_success(self, mock_config: MCPServerConfig):
        """成功连接应创建进程并完成初始化握手。"""
        proc_mock = _make_mock_process()
        with patch("subprocess.Popen", return_value=proc_mock) as mock_popen:
            conn = MCPConnection(mock_config)
            conn.connect()

        mock_popen.assert_called_once()
        assert conn.is_connected is True
        assert conn._process is not None

    def test_connect_idempotent(self, mock_config: MCPServerConfig):
        """重复 connect() 不应启动第二个进程。"""
        proc_mock = _make_mock_process()
        with patch("subprocess.Popen", return_value=proc_mock) as mock_popen:
            conn = MCPConnection(mock_config)
            conn.connect()
            conn.connect()  # 第二次调用

        mock_popen.assert_called_once()  # 仍然只启动一次

    def test_connect_command_not_found(self, mock_config: MCPServerConfig):
        """命令不存在时应优雅处理。"""
        with patch("subprocess.Popen", side_effect=FileNotFoundError("not found")):
            conn = MCPConnection(mock_config)
            conn.connect()  # 不应抛出异常

        assert conn._process is None
        assert conn.is_connected is False

    def test_connect_generic_error(self, mock_config: MCPServerConfig):
        """通用异常应优雅处理。"""
        with patch("subprocess.Popen", side_effect=PermissionError("denied")):
            conn = MCPConnection(mock_config)
            conn.connect()

        assert conn._process is None

    def test_connect_sends_initialize(self, mock_config: MCPServerConfig):
        """connect() 应发送 initialize 请求。"""
        # 响应 initialize
        proc_mock = _make_mock_process(
            [{"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "mock"}}}]
        )
        with patch("subprocess.Popen", return_value=proc_mock):
            conn = MCPConnection(mock_config)
            conn.connect()

        # 验证发送了 initialize 请求
        written = proc_mock.stdin.write.call_args[0][0]
        assert "initialize" in written
        assert "protocolVersion" in written


class TestMCPConnectionDisconnect:
    """MCPConnection.disconnect() 测试。"""

    def test_disconnect_connected(self, mock_config: MCPServerConfig):
        """断开已连接的进程应终止。"""
        proc_mock = _make_mock_process()
        with patch("subprocess.Popen", return_value=proc_mock):
            conn = MCPConnection(mock_config)
            conn.connect()
            conn.disconnect()

        proc_mock.terminate.assert_called_once()
        assert conn._process is None

    def test_disconnect_not_connected(self, mock_config: MCPServerConfig):
        """未连接时断开不应报错。"""
        conn = MCPConnection(mock_config)
        conn.disconnect()  # 不应抛出异常


class TestMCPConnectionSendRequest:
    """MCPConnection._send_request() 测试。"""

    def test_send_request_increments_id(self, mock_config: MCPServerConfig):
        """每次请求递增 request_id。"""
        proc_mock = _make_mock_process(
            [
                {"jsonrpc": "2.0", "id": 1, "result": {}},
                {"jsonrpc": "2.0", "id": 2, "result": {}},
            ]
        )
        with patch("subprocess.Popen", return_value=proc_mock):
            conn = MCPConnection(mock_config)
            conn.connect()
            assert conn._request_id == 1  # 第一次是 initialize
            conn._send_request("tools/list", {})
            assert conn._request_id == 2

    def test_send_request_not_connected(self, mock_config: MCPServerConfig):
        """未连接时发送请求应抛出 MCPError。"""
        conn = MCPConnection(mock_config)
        with pytest.raises(MCPError, match="未就绪"):
            conn._send_request("tools/list", {})

    def test_send_request_no_stdin(self, mock_config: MCPServerConfig):
        """stdin 不可用时抛出错误。"""
        proc_mock = _make_mock_process()
        proc_mock.stdin = None
        with patch("subprocess.Popen", return_value=proc_mock):
            conn = MCPConnection(mock_config)
            conn.connect()
            with pytest.raises(MCPError, match="未就绪"):
                conn._send_request("tools/list", {})

    def test_send_request_no_stdout(self, mock_config: MCPServerConfig):
        """stdout 不可用时抛出错误。"""
        proc_mock = _make_mock_process()
        proc_mock.stdout = None
        with patch("subprocess.Popen", return_value=proc_mock):
            conn = MCPConnection(mock_config)
            conn.connect()
            with pytest.raises(MCPError, match="未就绪"):
                conn._send_request("tools/list", {})

    def test_send_request_empty_response(self, mock_config: MCPServerConfig):
        """空响应行抛出错误。"""
        # 在 connect 消耗 initialize 响应后，下一个 readline 返回空字符串
        responses = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
            "",  # 空响应
        ]
        proc_mock = MagicMock()
        proc_mock.poll.return_value = None
        proc_mock.stdin = MagicMock()

        readline_iter = iter(responses)
        proc_mock.stdout.readline.side_effect = lambda: next(readline_iter)

        with patch("subprocess.Popen", return_value=proc_mock):
            conn = MCPConnection(mock_config)
            conn.connect()
            with pytest.raises(MCPError, match="无响应"):
                conn._send_request("tools/list", {})

    def test_send_request_json_decode_error(self, mock_config: MCPServerConfig):
        """无效 JSON 响应抛出错误。"""
        responses = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
            "not json\n",
        ]
        proc_mock = MagicMock()
        proc_mock.poll.return_value = None
        proc_mock.stdin = MagicMock()
        readline_iter = iter(responses)
        proc_mock.stdout.readline.side_effect = lambda: next(readline_iter)

        with patch("subprocess.Popen", return_value=proc_mock):
            conn = MCPConnection(mock_config)
            conn.connect()
            with pytest.raises(MCPError, match="JSON 解析错误"):
                conn._send_request("tools/list", {})

    def test_send_request_os_error(self, mock_config: MCPServerConfig):
        """OSError 应包装为 MCPError。"""
        write_count = [0]

        def _write(*args: object) -> int:
            write_count[0] += 1
            if write_count[0] >= 2:  # 第二次写入（tools/list）时失败
                raise OSError("broken pipe")
            return len(str(args[0]) if args else "")

        responses = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
        ]
        proc_mock = MagicMock()
        proc_mock.poll.return_value = None
        proc_mock.stdin = MagicMock()
        proc_mock.stdin.write.side_effect = _write
        readline_iter = iter(responses)
        proc_mock.stdout.readline.side_effect = lambda: next(readline_iter)

        with patch("subprocess.Popen", return_value=proc_mock):
            conn = MCPConnection(mock_config)
            conn.connect()
            with pytest.raises(MCPError, match="通信错误"):
                conn._send_request("tools/list", {})

    def test_send_request_remote_error(self, mock_config: MCPServerConfig):
        """远程返回 error 应抛出 MCPError。"""
        proc_mock = _make_mock_process(
            [
                {"jsonrpc": "2.0", "id": 1, "result": {}},  # initialize
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "error": {"code": -32601, "message": "Method not found"},
                },
            ]
        )
        with patch("subprocess.Popen", return_value=proc_mock):
            conn = MCPConnection(mock_config)
            conn.connect()
            with pytest.raises(MCPError, match="Method not found"):
                conn._send_request("tools/list", {})


class TestMCPConnectionListTools:
    """MCPConnection.list_tools() 测试。"""

    def test_list_tools_not_connected(self, mock_config: MCPServerConfig):
        """未连接时抛出错误。"""
        conn = MCPConnection(mock_config)
        with pytest.raises(MCPError, match="未连接"):
            conn.list_tools()

    def test_list_tools_returns_tools(self, mock_config: MCPServerConfig):
        """成功列出工具。"""
        proc_mock = _make_mock_process(
            [
                {"jsonrpc": "2.0", "id": 1, "result": {}},  # initialize
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "tools": [
                            {"name": "read_file", "description": "Read a file"},
                            {"name": "write_file", "description": "Write a file"},
                        ]
                    },
                },
            ]
        )
        with patch("subprocess.Popen", return_value=proc_mock):
            conn = MCPConnection(mock_config)
            conn.connect()
            tools = conn.list_tools()
            assert len(tools) == 2
            assert tools[0]["name"] == "read_file"
            assert tools[1]["name"] == "write_file"


class TestMCPConnectionCallTool:
    """MCPConnection.call_tool() 测试。"""

    def test_call_tool_not_connected(self, mock_config: MCPServerConfig):
        """未连接时抛出错误。"""
        conn = MCPConnection(mock_config)
        with pytest.raises(MCPError, match="未连接"):
            conn.call_tool("read_file", {"path": "/test"})

    def test_call_tool_success(self, mock_config: MCPServerConfig):
        """成功调用工具。"""
        proc_mock = _make_mock_process(
            [
                {"jsonrpc": "2.0", "id": 1, "result": {}},  # initialize
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {"content": [{"type": "text", "text": "file content"}]},
                },
            ]
        )
        with patch("subprocess.Popen", return_value=proc_mock):
            conn = MCPConnection(mock_config)
            conn.connect()
            result = conn.call_tool("read_file", {"path": "/test"})
            assert result[0]["text"] == "file content"


class TestMCPConnectionSendNotification:
    """MCPConnection._send_notification() 测试。"""

    def test_send_notification_no_process(self, mock_config: MCPServerConfig):
        """无进程时发送通知不应报错。"""
        conn = MCPConnection(mock_config)
        conn._send_notification("exit", {})  # 不应抛出异常

    def test_send_notification_writes(self, mock_config: MCPServerConfig):
        """通知应写入 stdin。"""
        proc_mock = _make_mock_process()
        with patch("subprocess.Popen", return_value=proc_mock):
            conn = MCPConnection(mock_config)
            conn.connect()
            conn._send_notification("notify", {"msg": "hello"})

        written = proc_mock.stdin.write.call_args[0][0]
        assert "notify" in written
        assert "hello" in written

    def test_send_notification_oserror_suppressed(self, mock_config: MCPServerConfig):
        """OSError 在通知中应被抑制。"""
        proc_mock = _make_mock_process()
        proc_mock.stdin.write.side_effect = OSError("broken")
        with patch("subprocess.Popen", return_value=proc_mock):
            conn = MCPConnection(mock_config)
            conn.connect()
            conn._send_notification("exit", {})  # 不应抛出异常


# ─── MCPToolBridge 测试 ──────────────────────────────────────────


class TestMCPToolBridgeConnectAll:
    """MCPToolBridge.connect_all() 测试。"""

    def test_connect_all_with_servers(self, tmp_path: Path):
        """带有效配置的服务器应返回已连接名称。"""
        config_dir = tmp_path / ".agent"
        config_dir.mkdir(parents=True)
        (config_dir / "mcp.json").write_text(
            json.dumps(
                {
                    "mcp_servers": [
                        {"name": "s1", "command": "python", "args": ["-m", "fake"]},
                        {"name": "s2", "command": "python", "args": ["-m", "fake2"]},
                    ]
                }
            ),
            encoding="utf-8",
        )

        bridge = MCPToolBridge(base_dir=str(tmp_path / ".agent"))
        bridge.load_config()

        proc_mock = _make_mock_process()
        with patch("subprocess.Popen", return_value=proc_mock):
            connected = bridge.connect_all()

        assert len(connected) == 2
        assert "s1" in connected
        assert "s2" in connected

    def test_connect_all_partial_failure(self, tmp_path: Path):
        """部分连接失败时只返回成功的。"""
        config_dir = tmp_path / ".agent"
        config_dir.mkdir(parents=True)
        (config_dir / "mcp.json").write_text(
            json.dumps(
                {
                    "mcp_servers": [
                        {"name": "good", "command": "python", "args": ["-m", "ok"]},
                        {"name": "bad", "command": "nonexistent_cmd", "args": []},
                    ]
                }
            ),
            encoding="utf-8",
        )

        bridge = MCPToolBridge(base_dir=str(tmp_path / ".agent"))
        bridge.load_config()

        # 第一个成功，第二个 FileNotFoundError
        proc_mock = _make_mock_process()
        with patch(
            "subprocess.Popen",
            side_effect=[proc_mock, FileNotFoundError("not found")],
        ):
            connected = bridge.connect_all()

        assert connected == ["good"]


class TestMCPToolBridgeGetConnection:
    """MCPToolBridge.get_connection() 测试。"""

    def test_get_connection_exists(self, tmp_path: Path):
        """获取已连接的服务器。"""
        config_dir = tmp_path / ".agent"
        config_dir.mkdir(parents=True)
        (config_dir / "mcp.json").write_text(
            json.dumps(
                {"mcp_servers": [{"name": "s1", "command": "python", "args": ["-m", "test"]}]}
            ),
            encoding="utf-8",
        )

        bridge = MCPToolBridge(base_dir=str(tmp_path / ".agent"))
        bridge.load_config()

        proc_mock = _make_mock_process()
        with patch("subprocess.Popen", return_value=proc_mock):
            bridge.connect_all()

        conn = bridge.get_connection("s1")
        assert conn is not None
        assert conn.config.name == "s1"

    def test_get_connection_not_exists(self):
        """获取不存在的连接返回 None。"""
        bridge = MCPToolBridge()
        assert bridge.get_connection("nonexistent") is None


class TestMCPToolBridgeDiscoverTools:
    """MCPToolBridge.discover_tools() 测试。"""

    def test_discover_tools_success(self, tmp_path: Path):
        """从已连接服务器发现工具。"""
        config_dir = tmp_path / ".agent"
        config_dir.mkdir(parents=True)
        (config_dir / "mcp.json").write_text(
            json.dumps(
                {"mcp_servers": [{"name": "fs", "command": "python", "args": ["-m", "fs"]}]}
            ),
            encoding="utf-8",
        )

        bridge = MCPToolBridge(base_dir=str(tmp_path / ".agent"))
        bridge.load_config()

        # 模拟 tools/list 返回
        proc_mock = _make_mock_process(
            [
                {"jsonrpc": "2.0", "id": 1, "result": {}},  # initialize
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "tools": [
                            {
                                "name": "read",
                                "description": "Read file",
                                "inputSchema": {"type": "object"},
                            },
                        ]
                    },
                },
            ]
        )
        with patch("subprocess.Popen", return_value=proc_mock):
            bridge.connect_all()
            tools = bridge.discover_tools()

        assert len(tools) == 1
        assert tools[0].name == "fs_read"
        assert tools[0].server_name == "fs"

    def test_discover_tools_no_connections(self):
        """无连接时发现工具返回空。"""
        bridge = MCPToolBridge()
        tools = bridge.discover_tools()
        assert tools == []


class TestMCPToolBridgeCallMCPTool:
    """MCPToolBridge.call_mcp_tool() 测试。"""

    def test_call_mcp_tool_success(self, tmp_path: Path):
        """通过桥接调用 MCP 工具。"""
        config_dir = tmp_path / ".agent"
        config_dir.mkdir(parents=True)
        (config_dir / "mcp.json").write_text(
            json.dumps(
                {"mcp_servers": [{"name": "fs", "command": "python", "args": ["-m", "fs"]}]}
            ),
            encoding="utf-8",
        )

        bridge = MCPToolBridge(base_dir=str(tmp_path / ".agent"))
        bridge.load_config()

        proc_mock = _make_mock_process(
            [
                {"jsonrpc": "2.0", "id": 1, "result": {}},  # initialize
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {"tools": [{"name": "read", "description": "Read"}]},
                },  # tools/list
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "result": {"content": [{"type": "text", "text": "hello"}]},
                },  # tools/call
            ]
        )
        with patch("subprocess.Popen", return_value=proc_mock):
            bridge.connect_all()
            bridge.discover_tools()
            result = bridge.call_mcp_tool("fs_read", path="/test.txt")

        assert result[0]["text"] == "hello"

    def test_call_mcp_tool_unknown(self, tmp_path: Path):
        """调用未发现的工具抛出错误。"""
        config_dir = tmp_path / ".agent"
        config_dir.mkdir(parents=True)
        (config_dir / "mcp.json").write_text(
            json.dumps(
                {"mcp_servers": [{"name": "fs", "command": "python", "args": ["-m", "fs"]}]}
            ),
            encoding="utf-8",
        )

        bridge = MCPToolBridge(base_dir=str(tmp_path / ".agent"))
        bridge.load_config()

        with patch("subprocess.Popen", return_value=_make_mock_process()):
            bridge.connect_all()
            # 没有调用 discover_tools → 没有工具被注册
            with pytest.raises(MCPError, match="未发现"):
                bridge.call_mcp_tool("fs_read", path="/test.txt")


class TestMCPToolBridgeRegisterTools:
    """MCPToolBridge.register_tools() 测试。"""

    def test_register_tools(self, tmp_path: Path):
        """将发现的 MCP 工具注册到 ToolRegistry。"""
        from agent_cli.tools.registry import ToolRegistry

        config_dir = tmp_path / ".agent"
        config_dir.mkdir(parents=True)
        (config_dir / "mcp.json").write_text(
            json.dumps(
                {"mcp_servers": [{"name": "fs", "command": "python", "args": ["-m", "fs"]}]}
            ),
            encoding="utf-8",
        )

        bridge = MCPToolBridge(base_dir=str(tmp_path / ".agent"))
        bridge.load_config()

        proc_mock = _make_mock_process(
            [
                {"jsonrpc": "2.0", "id": 1, "result": {}},  # initialize
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {"tools": [{"name": "read", "description": "Read file"}]},
                },
            ]
        )
        with patch("subprocess.Popen", return_value=proc_mock):
            bridge.connect_all()
            bridge.discover_tools()

            registry = ToolRegistry()
            count = bridge.register_tools(registry)
            assert count == 1

            assert "fs_read" in registry.tool_names

    def test_register_tools_wrong_type(self):
        """传入非 ToolRegistry 返回 0。"""
        bridge = MCPToolBridge()
        count = bridge.register_tools("not_a_registry")
        assert count == 0


class TestMCPToolBridgeDisconnectAll:
    """MCPToolBridge.disconnect_all() 测试。"""

    def test_disconnect_all_with_connections(self, tmp_path: Path):
        """断开所有连接。"""
        config_dir = tmp_path / ".agent"
        config_dir.mkdir(parents=True)
        (config_dir / "mcp.json").write_text(
            json.dumps(
                {
                    "mcp_servers": [
                        {"name": "s1", "command": "python", "args": ["-m", "s1"]},
                        {"name": "s2", "command": "python", "args": ["-m", "s2"]},
                    ]
                }
            ),
            encoding="utf-8",
        )

        bridge = MCPToolBridge(base_dir=str(tmp_path / ".agent"))
        bridge.load_config()

        proc_mock = _make_mock_process()
        with patch("subprocess.Popen", return_value=proc_mock):
            bridge.connect_all()
            assert len(bridge._connections) == 2

        bridge.disconnect_all()
        assert len(bridge._connections) == 0


# ─── _MCPToolWrapper 测试 ────────────────────────────────────────


class TestMCPToolWrapper:
    """_MCPToolWrapper — MCP 工具的 BaseTool 适配器测试。"""

    @pytest.fixture
    def tool_def(self) -> MCPToolDef:
        return MCPToolDef(
            name="fs_read",
            description="Read a file via MCP",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
            server_name="fs",
        )

    def test_spec_returns_tool_spec(self, tool_def: MCPToolDef):
        """spec() 应返回正确的 ToolSpec。"""
        bridge = MCPToolBridge()
        wrapper = _MCPToolWrapper(tool_def, bridge)
        spec = wrapper.spec()

        assert isinstance(spec, ToolSpec)
        assert spec.name == "fs_read"
        assert spec.description == "Read a file via MCP"
        assert spec.parameters["type"] == "object"
        assert spec.safety == SafetyLevel.ALWAYS_ASK
        assert spec.extra["server"] == "fs"

    def test_spec_empty_description(self):
        """描述为空时使用 fallback 文本。"""
        tool_def = MCPToolDef(name="test", description="", server_name="srv")
        bridge = MCPToolBridge()
        wrapper = _MCPToolWrapper(tool_def, bridge)
        spec = wrapper.spec()
        assert "MCP 工具" in spec.description
        assert "srv" in spec.description

    def test_spec_empty_schema(self):
        """输入 schema 为空时 fallback 到默认空 schema。"""
        tool_def = MCPToolDef(name="test", description="desc", server_name="srv")
        bridge = MCPToolBridge()
        wrapper = _MCPToolWrapper(tool_def, bridge)
        spec = wrapper.spec()
        assert spec.parameters["type"] == "object"
        assert spec.parameters["properties"] == {}

    def test_execute_calls_bridge(self, tool_def: MCPToolDef):
        """execute() 应委托给 bridge.call_mcp_tool。"""
        bridge = MCPToolBridge()
        wrapper = _MCPToolWrapper(tool_def, bridge)

        with patch.object(bridge, "call_mcp_tool", return_value="ok") as mock_call:
            result = wrapper.execute(path="/test.txt")

        mock_call.assert_called_once_with("fs_read", path="/test.txt")
        assert result == "ok"
