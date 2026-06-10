"""ModelProvider 抽象层。

设计哲学（来源：14days-build-claude-code-cli）：
  Provider 抽象使得 Agent Loop 与具体模型解耦。
  MockProvider 用于测试，AnthropicProvider 用于生产，
  CompatibleProvider 用于兼容其他 API。

三层架构:
  IModelProvider  ←  抽象接口
    ├─ MockProvider      ← 测试用，预设响应
    ├─ AnthropicProvider ← Anthropic Claude API
    └─ CompatibleProvider ← 兼容 API（如 DeepSeek）
"""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

# ─── 数据模型 ───────────────────────────────────────────────────


@dataclass
class Message:
    """统一的内部消息格式。"""

    role: Literal["user", "assistant", "system"]
    content: str | list[dict[str, Any]]


@dataclass
class ToolCall:
    """模型请求的工具调用。"""

    id: str
    name: str
    input: dict[str, Any]


@dataclass
class Usage:
    """Token 用量统计。"""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Response:
    """模型调用响应。"""

    stop_reason: str  # "end_turn" | "tool_use" | "max_tokens" | "stop_sequence"
    content: list[dict[str, Any]]
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


# ─── 抽象接口 ───────────────────────────────────────────────────


class IModelProvider(ABC):
    """模型提供者接口。

    所有具体 Provider 必须实现此接口。
    """

    @abstractmethod
    def invoke(self, messages: list[dict], tools: list[dict] | None = None) -> Response:
        """调用模型，返回响应。

        Args:
            messages: Anthropic Messages API 格式的消息列表。
            tools: Anthropic 格式的工具定义列表（可选）。

        Returns:
            包含模型响应内容的 Response 对象。
        """
        ...


# ─── 内部助手 ───────────────────────────────────────────────────


def _parse_response(raw: dict) -> Response:
    """将 Anthropic API 原始响应解析为 Response 对象。"""
    content = raw.get("content", [])
    stop_reason = raw.get("stop_reason", "end_turn")

    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    for block in content:
        if block["type"] == "text":
            text_parts.append(block["text"])
        elif block["type"] == "tool_use":
            tool_calls.append(
                ToolCall(
                    id=block["id"],
                    name=block["name"],
                    input=block["input"],
                )
            )

    usage_data = raw.get("usage", {})
    usage = Usage(
        input_tokens=usage_data.get("input_tokens", 0),
        output_tokens=usage_data.get("output_tokens", 0),
    )

    return Response(
        stop_reason=stop_reason,
        content=content,
        text="".join(text_parts),
        tool_calls=tool_calls,
        usage=usage,
    )


# ─── MockProvider ───────────────────────────────────────────────


class MockProvider(IModelProvider):
    """Mock 实现：返回预设响应，用于测试。

    会根据消息列表的上下文智能选择返回文本回复还是工具调用。
    当最后一条消息包含特定关键字时触发工具调用模拟。
    """

    def __init__(
        self,
        default_response: str = "你好！我是 Agent-CLI，有什么可以帮助你的？",
        tool_trigger_keywords: tuple[str, ...] = ("搜索", "执行", "创建", "读取", "写入"),
    ):
        self.default_response = default_response
        self.tool_trigger_keywords = tool_trigger_keywords
        self.call_count = 0

    def invoke(self, messages: list[dict], tools: list[dict] | None = None) -> Response:
        """根据输入返回预设的响应。"""
        self.call_count += 1
        last_msg = messages[-1]["content"] if messages else ""

        # 提取文本内容
        text = self._extract_text(last_msg)

        # 检查是否应触发工具调用
        if self._should_use_tool(text) and len(messages) < 4:
            return self._make_tool_response(text)
        elif "你好" in text or "hello" in text.lower():
            return self._make_text_response(
                "你好！我是 Agent-CLI，你的个人助手。有什么我可以帮你的吗？"
            )
        elif "帮助" in text or "help" in text:
            return self._make_text_response(
                "我可以执行以下操作：\n"
                "- 运行 bash 命令\n"
                "- 读写文件\n"
                "- 搜索文件内容\n"
                "- 获取网页内容\n"
                "- 以及更多！"
            )
        else:
            return self._make_text_response(self.default_response)

    def _extract_text(self, content: str | list) -> str:
        """从消息内容中提取纯文本。"""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return " ".join(parts)
        return str(content)

    def _should_use_tool(self, text: str) -> bool:
        """判断是否应模拟工具调用。"""
        return any(kw in text for kw in self.tool_trigger_keywords)

    def _make_text_response(self, text: str) -> Response:
        """构建文本回复。"""
        return Response(
            stop_reason="end_turn",
            content=[{"type": "text", "text": text}],
            text=text,
        )

    def _make_tool_response(self, text: str) -> Response:
        """构建包含工具调用的响应。"""
        tool_name, tool_input = self._guess_tool(text)
        tool_id = f"tu_{uuid.uuid4().hex[:8]}"

        return Response(
            stop_reason="tool_use",
            content=[
                {"type": "text", "text": f"好的，我来执行：{text}"},
                {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": tool_name,
                    "input": tool_input,
                },
            ],
            text=f"好的，我来执行：{text}",
            tool_calls=[ToolCall(id=tool_id, name=tool_name, input=tool_input)],
        )

    def _guess_tool(self, text: str) -> tuple[str, dict]:
        """根据文本猜测应调用的工具。"""
        if "bash" in text or "执行" in text or "命令" in text or "运行" in text:
            return "bash", {"command": text}
        if "创建" in text or "写入" in text:
            return "write", {"path": "/tmp/test.txt", "content": text}
        if "读取" in text or "打开" in text:
            return "read", {"path": "/tmp/test.txt"}
        if "搜索" in text or "查找" in text:
            return "grep", {"pattern": "TODO", "path": "."}
        if "网页" in text or "获取" in text or "fetch" in text.lower():
            return "web_fetch", {"url": "https://example.com"}
        return "bash", {"command": f"echo '{text}'"}


# ─── AnthropicProvider ──────────────────────────────────────────


class AnthropicProvider(IModelProvider):
    """Anthropic Claude API 实现。

    需要设置环境变量 ANTHROPIC_API_KEY。
    支持的模型包括 claude-sonnet-4-20250514, claude-3-5-haiku-latest 等。
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
    ):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self._client: Any = None  # Lazy init

    def _get_client(self):
        """延迟初始化 Anthropic 客户端。"""
        if self._client is not None:
            return self._client
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError("anthropic 包未安装。请运行: uv add anthropic") from None

        key = self.api_key
        if not key:
            import os

            key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("未设置 ANTHROPIC_API_KEY。请通过环境变量或构造参数传入。")

        self._client = Anthropic(api_key=key)
        return self._client

    def invoke(self, messages: list[dict], tools: list[dict] | None = None) -> Response:
        """调用 Anthropic Claude API。"""
        client = self._get_client()

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        raw = client.messages.create(**kwargs)

        return _parse_response(raw.model_dump(mode="json"))


# ─── CompatibleProvider ─────────────────────────────────────────


class CompatibleProvider(IModelProvider):
    """兼容 API 实现（如 DeepSeek、OpenAI 兼容模式）。

    通过指定 base_url 可适配任意兼容 OpenAI API 格式的服务。
    """

    def __init__(
        self,
        base_url: str = "https://api.deepseek.com/v1",
        api_key: str | None = None,
        model: str = "deepseek-chat",
        max_tokens: int = 4096,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self._client: Any = None

    def _get_client(self):
        """延迟初始化 httpx 客户端。"""
        if self._client is not None:
            return self._client

        key = self.api_key
        if not key:
            import os

            key = os.environ.get("COMPATIBLE_API_KEY")

        import httpx

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key or ''}",
        }

        self._client = httpx.Client(base_url=self.base_url, headers=headers)
        return self._client

    def invoke(self, messages: list[dict], tools: list[dict] | None = None) -> Response:
        """调用兼容 API。"""
        client = self._get_client()

        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }

        # 简化 tools → functions 映射
        if tools:
            body["tools"] = tools

        try:
            resp = client.post("/chat/completions", json=body)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]

            # 转换为内部 Response 格式
            content_blocks: list[dict] = []
            tool_calls: list[ToolCall] = []
            text = msg.get("content") or ""

            if text:
                content_blocks.append({"type": "text", "text": text})

            for tc in msg.get("tool_calls") or []:
                tid = tc["id"]
                tname = tc["function"]["name"]
                tinput = json.loads(tc["function"]["arguments"])
                content_blocks.append(
                    {"type": "tool_use", "id": tid, "name": tname, "input": tinput}
                )
                tool_calls.append(ToolCall(id=tid, name=tname, input=tinput))

            finish = choice.get("finish_reason", "stop")
            stop_reason = "tool_use" if finish == "tool_calls" else "end_turn"

            usage_data = data.get("usage", {})
            usage = Usage(
                input_tokens=usage_data.get("prompt_tokens", 0),
                output_tokens=usage_data.get("completion_tokens", 0),
            )

            return Response(
                stop_reason=stop_reason,
                content=content_blocks,
                text=text or "",
                tool_calls=tool_calls,
                usage=usage,
            )

        except Exception as e:
            return Response(
                stop_reason="end_turn",
                content=[{"type": "text", "text": f"API 调用失败: {e}"}],
                text=f"API 调用失败: {e}",
            )
