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
import logging
import random
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

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


# ─── 重试与退避 ───────────────────────────────────────────────────

# 默认重试参数
RETRY_MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # 秒
RETRY_MAX_DELAY = 30.0  # 秒

# 不可重试的 HTTP 状态码
_NON_RETRYABLE_STATUSES = {400, 401, 403, 404, 405, 422}


def _is_retryable_http(status: int) -> bool:
    """判断 HTTP 状态码是否可重试。"""
    return status not in _NON_RETRYABLE_STATUSES


def invoke_with_retry(
    fn: Any,
    max_retries: int = RETRY_MAX_RETRIES,
    base_delay: float = RETRY_BASE_DELAY,
    max_delay: float = RETRY_MAX_DELAY,
) -> Any:
    """带指数退避和随机抖动的 API 调用重试包装器。

    对可重试错误（网络问题、5xx、429）进行指数退避重试，
    对不可重试错误（401、403、404 等）立即抛出。

    Args:
        fn: 无参可调用对象，执行实际 API 请求。
        max_retries: 最大重试次数（默认 3）。
        base_delay: 初始延迟秒数（默认 1.0）。
        max_delay: 最大延迟秒数（默认 30.0）。

    Returns:
        fn() 的返回值。

    Raises:
        最后一次异常（重试耗尽或不可重试错误）。
    """
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if not _is_retryable_http(status) or attempt == max_retries:
                logger.warning(
                    "HTTP %d 不可重试或重试耗尽 (attempt %d/%d)",
                    status,
                    attempt + 1,
                    max_retries + 1,
                )
                raise
            delay = min(base_delay * (2**attempt) + random.uniform(0, 0.5), max_delay)
            logger.info(
                "HTTP %d 重试 (attempt %d/%d, delay %.1fs)",
                status,
                attempt + 1,
                max_retries + 1,
                delay,
            )
            time.sleep(delay)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
            if attempt == max_retries:
                logger.warning(
                    "网络错误重试耗尽 (attempt %d/%d): %s",
                    attempt + 1,
                    max_retries + 1,
                    e,
                )
                raise
            delay = min(base_delay * (2**attempt) + random.uniform(0, 0.5), max_delay)
            logger.info(
                "网络错误重试 (attempt %d/%d, delay %.1fs): %s",
                attempt + 1,
                max_retries + 1,
                delay,
                e,
            )
            time.sleep(delay)

    # 不应到达此处 — 上面的循环覆盖了所有路径
    raise RuntimeError("重试循环异常终止")


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

    def invoke_stream(self, messages: list[dict], tools: list[dict] | None = None) -> Iterator[str]:
        """流式调用模型，逐个产出文本块。

        默认实现直接返回 invoke() 的完整文本（非流式）。
        子类可重写此方法以提供真正的流式输出。

        Args:
            messages: 消息列表。
            tools: 工具定义列表（可选）。

        Yields:
            文本块，每次产出累积的新内容。
        """
        response = self.invoke(messages, tools=tools)
        if response.text:
            yield response.text


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

    def invoke_stream(self, messages: list[dict], tools: list[dict] | None = None) -> Iterator[str]:
        """流式调用 MockProvider — 逐字符模拟流式输出。"""
        response = self.invoke(messages, tools=tools)
        if response.text:
            yield from response.text

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

    def _get_client(self) -> Any:
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
        """调用 Anthropic Claude API（带指数退避重试）。"""
        client = self._get_client()

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        def _do_request() -> Any:
            """执行实际 API 调用（可被重试）。"""
            return client.messages.create(**kwargs)

        raw = invoke_with_retry(_do_request)

        return _parse_response(raw.model_dump(mode="json"))

    def invoke_stream(self, messages: list[dict], tools: list[dict] | None = None) -> Iterator[str]:
        """流式调用 Anthropic Claude API。"""
        client = self._get_client()

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        try:
            with client.messages.stream(**kwargs) as stream:
                yield from stream.text_stream
        except Exception as e:
            yield f"\n[流式调用失败: {e}]"


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

    def _get_client(self) -> Any:
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
        """调用兼容 API（带指数退避重试）。"""
        client = self._get_client()

        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }

        # 简化 tools → functions 映射
        if tools:
            body["tools"] = tools

        def _do_request() -> httpx.Response:
            """执行实际 HTTP 请求（可被重试）。"""
            r = client.post("/chat/completions", json=body)
            r.raise_for_status()
            return r

        try:
            resp = invoke_with_retry(_do_request)
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

        except (httpx.HTTPStatusError, httpx.RequestError, json.JSONDecodeError, KeyError) as e:
            return Response(
                stop_reason="end_turn",
                content=[{"type": "text", "text": f"API 调用失败: {e}"}],
                text=f"API 调用失败: {e}",
            )

    def invoke_stream(self, messages: list[dict], tools: list[dict] | None = None) -> Iterator[str]:
        """流式调用兼容 API（SSE）。

        使用 httpx 的流式传输逐块产出文本，
        支持 OpenAI 兼容的 SSE 格式（如 DeepSeek、OpenAI）。
        """
        client = self._get_client()

        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
            "stream": True,
        }
        if tools:
            body["tools"] = tools

        try:
            with client.stream("POST", "/chat/completions", json=body) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        payload = line[6:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue

        except Exception as e:
            yield f"\n[流式调用失败: {e}]"
