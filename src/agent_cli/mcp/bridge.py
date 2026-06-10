"""MCPToolBridge — 外部工具协议桥接。

设计依据（规范 4.11）：
  实现标准 MCP Client（stdio 传输），动态发现并注册外部工具。
  外部工具与内置工具完全对等，通过 ToolRegistry 统一调度。

MCP（Model Context Protocol）协议规范:
  - 初始化: 发送 initialize 请求
  - 工具发现: 发送 tools/list 请求
  - 工具调用: 发送 tools/call 请求
  - 通信: 标准 JSON-RPC over stdio

使用示例:
    bridge = MCPToolBridge()
    bridge.connect_all()
    bridge.register_tools(registry)  # 动态注册到 ToolRegistry
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from agent_cli.mcp.models import MCPServerConfig, MCPToolDef
from agent_cli.tools.base import BaseTool, SafetyLevel, ToolSpec

logger = logging.getLogger(__name__)

# JSON-RPC 协议常量
MCP_VERSION = "2024-11-05"


class MCPError(Exception):
    """MCP 协议错误。"""


class MCPConnection:
    """MCP 服务器连接（stdio 传输）。

    管理单个 MCP 服务器子进程的生命周期。
    通过 stdin/stdout 进行 JSON-RPC 通信。
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._process: subprocess.Popen | None = None
        self._request_id = 0

    def connect(self) -> None:
        """建立到 MCP 服务器的连接。

        启动子进程并通过 initialize 握手。
        """
        if self._process:
            logger.debug("MCP 服务器 '%s' 已连接", self.config.name)
            return

        logger.info("连接 MCP 服务器: %s (%s)", self.config.name, self.config.command)

        try:
            env = dict(self.config.env) if self.config.env else None
            self._process = subprocess.Popen(
                [self.config.command, *self.config.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
            )
            # 发送 initialize 请求
            response = self._send_request(
                "initialize",
                {
                    "protocolVersion": MCP_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "agent-cli", "version": "0.1.0"},
                },
            )
            logger.debug("MCP 初始化响应: %s", response)
        except FileNotFoundError:
            logger.warning("MCP 服务器命令未找到: %s", self.config.command)
            self._process = None
        except Exception as e:
            logger.error("MCP 连接失败 '%s': %s", self.config.name, e)
            self._process = None

    def disconnect(self) -> None:
        """断开 MCP 服务器连接。"""
        if self._process:
            from contextlib import suppress

            with suppress(Exception):
                self._send_notification("exit", {})
            self._process.terminate()
            self._process = None
            logger.info("MCP 服务器已断开: %s", self.config.name)

    def list_tools(self) -> list[dict]:
        """获取服务器提供的工具列表。

        Returns:
            工具定义列表。

        Raises:
            MCPError: 连接未建立或通信失败。
        """
        if not self._process:
            raise MCPError(f"MCP 服务器未连接: {self.config.name}")
        response = self._send_request("tools/list", {})
        return response.get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """调用 MCP 工具。

        Args:
            name: 工具名。
            arguments: 工具参数。

        Returns:
            工具执行结果。

        Raises:
            MCPError: 调用失败。
        """
        if not self._process:
            raise MCPError(f"MCP 服务器未连接: {self.config.name}")
        response = self._send_request("tools/call", {"name": name, "arguments": arguments or {}})
        return response.get("content", response)

    def _send_request(self, method: str, params: dict) -> dict:
        """发送 JSON-RPC 请求并等待响应。

        Args:
            method: 方法名。
            params: 参数。

        Returns:
            响应结果中的 result 字段。

        Raises:
            MCPError: 通信失败或远程错误。
        """
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise MCPError("MCP 进程未就绪")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        request_str = json.dumps(request, ensure_ascii=False) + "\n"
        logger.debug("MCP → %s: %s", self.config.name, method)

        try:
            self._process.stdin.write(request_str)
            self._process.stdin.flush()

            response_line = self._process.stdout.readline()
            if not response_line:
                raise MCPError("MCP 服务器无响应")

            response = json.loads(response_line)

            if "error" in response:
                err = response["error"]
                raise MCPError(f"MCP 错误 [{self.config.name}]: {err.get('message', str(err))}")

            return response.get("result", {})
        except json.JSONDecodeError as e:
            raise MCPError(f"MCP JSON 解析错误: {e}") from e
        except OSError as e:
            raise MCPError(f"MCP 通信错误: {e}") from e

    def _send_notification(self, method: str, params: dict) -> None:
        """发送 JSON-RPC 通知（无需响应）。"""
        if not self._process or not self._process.stdin:
            return
        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            self._process.stdin.write(json.dumps(notification, ensure_ascii=False) + "\n")
            self._process.stdin.flush()
        except OSError:
            pass

    @property
    def is_connected(self) -> bool:
        """连接是否有效。"""
        return self._process is not None and self._process.poll() is None


class MCPToolBridge:
    """MCP 工具桥接器。

    管理多个 MCP 服务器连接，提供工具发现和注册功能。
    将外部 MCP 工具包装为 BaseTool 实例，注册到 ToolRegistry。

    Usage:
        bridge = MCPToolBridge()
        bridge.load_config()
        bridge.connect_all()
        bridge.register_tools(registry)
    """

    def __init__(self, base_dir: str = ".agent"):
        self._config_path = Path(base_dir) / "mcp.json"
        self._servers: list[MCPServerConfig] = []
        self._connections: dict[str, MCPConnection] = {}
        self._discovered_tools: dict[str, MCPToolDef] = {}

    # ── 配置加载 ────────────────────────────────────────────────

    def load_config(self) -> list[MCPServerConfig]:
        """从 .agent/mcp.json 加载服务器配置。

        Returns:
            服务器配置列表。
        """
        if not self._config_path.exists():
            logger.info("MCP 配置文件不存在: %s", self._config_path)
            return []

        try:
            data = json.loads(self._config_path.read_text(encoding="utf-8"))
            raw_servers = data.get("mcp_servers", [])
            self._servers = [MCPServerConfig.from_dict(s) for s in raw_servers]
            logger.info("MCP 配置加载: %d 个服务器", len(self._servers))
            return self._servers
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("MCP 配置解析失败: %s", e)
            return []

    # ── 连接管理 ────────────────────────────────────────────────

    def connect_all(self) -> list[str]:
        """连接到所有配置的 MCP 服务器。

        Returns:
            成功连接的服务器名称列表。
        """
        connected: list[str] = []
        for config in self._servers:
            conn = MCPConnection(config)
            conn.connect()
            if conn.is_connected:
                self._connections[config.name] = conn
                connected.append(config.name)
                logger.info("MCP 服务器已连接: %s", config.name)
            else:
                logger.warning("MCP 服务器连接失败: %s", config.name)
        return connected

    def disconnect_all(self) -> None:
        """断开所有 MCP 服务器连接。"""
        for _name, conn in self._connections.items():
            conn.disconnect()
        self._connections.clear()
        logger.info("所有 MCP 服务器已断开")

    def get_connection(self, server_name: str) -> MCPConnection | None:
        """获取指定服务器的连接。"""
        return self._connections.get(server_name)

    # ── 工具发现 ────────────────────────────────────────────────

    def discover_tools(self) -> list[MCPToolDef]:
        """从所有已连接的服务器发现工具。

        Returns:
            发现的工具定义列表。
        """
        self._discovered_tools.clear()
        tools: list[MCPToolDef] = []

        for server_name, conn in self._connections.items():
            try:
                raw_tools = conn.list_tools()
                for raw in raw_tools:
                    tool_def = MCPToolDef(
                        name=f"{server_name}_{raw.get('name', 'unknown')}",
                        description=raw.get("description", ""),
                        input_schema=raw.get("inputSchema", raw.get("input_schema", {})),
                        server_name=server_name,
                    )
                    self._discovered_tools[tool_def.name] = tool_def
                    tools.append(tool_def)
                    logger.debug("发现 MCP 工具: %s (来自 %s)", tool_def.name, server_name)
            except MCPError as e:
                logger.warning("工具发现失败 '%s': %s", server_name, e)

        logger.info("MCP 工具发现: %d 个", len(tools))
        return tools

    # ── 动态注册 ────────────────────────────────────────────────

    def register_tools(self, registry: Any) -> int:
        """将 MCP 工具动态注册到 ToolRegistry。

        Args:
            registry: ToolRegistry 实例。

        Returns:
            注册的工具数量。
        """
        from agent_cli.tools.registry import ToolRegistry

        if not isinstance(registry, ToolRegistry):
            logger.warning("MCP: 无效的注册表类型")
            return 0

        count = 0
        for tool_def in self._discovered_tools.values():
            mcp_tool = _MCPToolWrapper(tool_def, self)
            registry.register(mcp_tool)
            count += 1
            logger.info("MCP 工具已注册: %s", tool_def.name)

        return count

    def call_mcp_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """调用 MCP 工具（供 _MCPToolWrapper 使用）。

        Args:
            tool_name: 工具全名（含 server 前缀）。
            **kwargs: 工具参数。

        Returns:
            执行结果。
        """
        tool_def = self._discovered_tools.get(tool_name)
        if not tool_def:
            raise MCPError(f"MCP 工具未发现: {tool_name}")

        conn = self._connections.get(tool_def.server_name)
        if not conn or not conn.is_connected:
            raise MCPError(f"MCP 服务器未连接: {tool_def.server_name}")

        # 去掉 server 前缀再调用
        raw_name = tool_name[len(tool_def.server_name) + 1 :]
        return conn.call_tool(raw_name, kwargs)


class _MCPToolWrapper(BaseTool):
    """MCP 工具包装器 — 将 MCP 工具适配为 BaseTool 接口。"""

    def __init__(self, tool_def: MCPToolDef, bridge: MCPToolBridge):
        self._def = tool_def
        self._bridge = bridge

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self._def.name,
            description=self._def.description or f"MCP 工具 ({self._def.server_name})",
            parameters=self._def.input_schema
            or {
                "type": "object",
                "properties": {},
            },
            safety=SafetyLevel.ALWAYS_ASK,
            extra={"server": self._def.server_name},
        )

    def execute(self, **kwargs: Any) -> Any:
        return self._bridge.call_mcp_tool(self._def.name, **kwargs)
