"""ToolRegistry 工具注册中心。

设计哲学（来源：14days-build-claude-code-cli）：
  统一注册中心管理所有工具的注册、查找、执行。
  自动生成 LLM 所需的 JSON Schema 格式。
  扩展新能力 = 注册新工具，无需修改循环代码。
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册中心。

    管理所有工具的注册、查找、执行。
    支持自动生成 LLM 所需的 tool 列表格式。

    Usage:
        registry = ToolRegistry()
        registry.register(BashTool())
        schemas = registry.schemas()  # → [{name, description, input_schema}, ...]
        result = registry.execute("bash", command="echo hello")
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    @property
    def tool_names(self) -> list[str]:
        """返回所有已注册工具的名称列表。"""
        return list(self._tools.keys())

    def register(self, tool: BaseTool) -> None:
        """注册工具。同名工具会覆盖并产生警告。

        Args:
            tool: BaseTool 子类实例。
        """
        spec = tool.spec()
        if spec.name in self._tools:
            logger.warning("工具 '%s' 已存在，将被覆盖", spec.name)
        self._tools[spec.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """按名称查找工具。"""
        return self._tools.get(name)

    def schemas(self) -> list[dict]:
        """生成 LLM API 所需的 tools 参数格式。

        返回列表可直接传入 Anthropic/OpenAI 的 tools 参数。
        """
        return [tool.to_tool_schema() for tool in self._tools.values()]

    def execute(self, name: str, **kwargs: Any) -> Any:
        """执行指定工具。

        Args:
            name: 工具名。
            **kwargs: 传递给工具的参数。

        Returns:
            工具执行结果。

        Raises:
            KeyError: 工具不存在。
        """
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"工具 '{name}' 未注册。可用工具: {list(self._tools.keys())}")
        return tool.execute(**kwargs)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)
