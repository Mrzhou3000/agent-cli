"""MCP Bridge 数据模型。

设计依据（规范 4.11）：
  - MCPToolBridge 桥接类
  - 标准 MCP Client（stdio 传输）
  - 动态注册到 ToolRegistry
  - 配置: .agent/mcp.json
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPServerConfig:
    """MCP 服务器配置。

    Attributes:
        name: 服务器名称。
        transport: 传输协议（stdio / sse）。
        command: 启动命令（stdio 模式）。
        args: 命令参数。
        env: 环境变量。
    """

    name: str
    transport: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> MCPServerConfig:
        """从字典创建配置。"""
        return cls(
            name=data.get("name", ""),
            transport=data.get("transport", "stdio"),
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env", {}),
        )


@dataclass
class MCPToolDef:
    """MCP 工具定义。

    Attributes:
        name: 工具名。
        description: 工具描述。
        input_schema: 输入参数 JSON Schema。
        server_name: 所属服务器名。
    """

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""
