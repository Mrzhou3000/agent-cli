"""工具系统基础定义。

设计哲学（来源：learn-claude-code + 14days-build）：
  ToolSpec 是工具元信息的统一规范，所有工具都通过它注册到 Registry。
  SafetyLevel 为权限引擎提供决策依据。
  BaseTool 是工具实现者的抽象基类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SafetyLevel(str, Enum):  # noqa: UP042 — str+Enum 兼容性优于 StrEnum
    """安全等级。

    SAFE:      无风险，直接执行（如 grep、glob）
    SENSITIVE: 敏感操作，需用户确认（如 bash 命令）
    DANGEROUS: 危险操作，必须审批（如 rm -rf 等破坏性操作）
    ALWAYS_ASK: 总是询问（如网络请求）
    """

    SAFE = "safe"
    SENSITIVE = "sensitive"
    DANGEROUS = "dangerous"
    ALWAYS_ASK = "always_ask"


@dataclass
class ToolSpec:
    """工具元信息规范。

    每个工具通过 ToolSpec 描述其名称、用途、参数、入口函数及安全级别。
    注册到 ToolRegistry 后自动生成 LLM API 所需的 JSON Schema 格式。
    """

    name: str
    """工具名（唯一标识），如 'bash', 'read', 'write'。"""

    description: str
    """人类可读的工具描述。"""

    parameters: dict
    """JSON Schema 格式的参数定义。

    示例:
        {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的命令"}
            },
            "required": ["command"]
        }
    """

    handler: Callable
    """实际执行函数。接受 **kwargs 参数，返回任意结果。"""

    safety: SafetyLevel = SafetyLevel.SAFE
    """安全等级，默认为 SAFE。"""

    extra: dict[str, Any] = field(default_factory=dict)
    """额外元信息，用于扩展。"""


class BaseTool(ABC):
    """工具基类。

    所有具体工具必须继承此类并实现 spec() 和 execute() 方法。
    """

    @abstractmethod
    def spec(self) -> ToolSpec:
        """返回工具的元信息描述。"""
        ...

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        """执行工具逻辑。

        Args:
            **kwargs: 与 ToolSpec.parameters 定义一致的参数。

        Returns:
            执行结果，通常为字符串或可 JSON 序列化的结构。
        """
        ...

    def to_tool_schema(self) -> dict:
        """生成 LLM API 所需的 tool 格式。"""
        s = self.spec()
        return {
            "name": s.name,
            "description": s.description,
            "input_schema": s.parameters,
        }
