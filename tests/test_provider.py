"""Provider 单元测试：AnthropicProvider + CompatibleProvider + 数据模型。

目标模块: src/agent_cli/core/provider.py
当前覆盖率: 46% → 目标 90%

策略：
  - AnthropicProvider: mock anthropic.Anthropic SDK
  - CompatibleProvider: mock httpx.Client
  - 数据模型: 直接构造验证
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from agent_cli.core.provider import (
    AnthropicProvider,
    CompatibleProvider,
    Message,
    MockProvider,
    Response,
    ToolCall,
    Usage,
    _parse_response,
)

# ═══════════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataModels:
    """Message / ToolCall / Usage / Response dataclass 测试。"""

    def test_message_user(self):
        """Message 应正确存储 user 角色消息。"""
        msg = Message(role="user", content="你好")
        assert msg.role == "user"
        assert msg.content == "你好"

    def test_message_system(self):
        """Message 应正确存储 system 角色消息。"""
        msg = Message(role="system", content="你是助手")
        assert msg.role == "system"

    def test_message_assistant(self):
        """Message 应正确存储 assistant 角色消息。"""
        msg = Message(role="assistant", content="我是AI")
        assert msg.role == "assistant"

    def test_message_list_content(self):
        """Message 的 content 可以是 list。"""
        blocks = [{"type": "text", "text": "hello"}]
        msg = Message(role="user", content=blocks)
        assert isinstance(msg.content, list)

    def test_tool_call_defaults(self):
        """ToolCall 应正确存储工具调用信息。"""
        tc = ToolCall(id="tu_001", name="bash", input={"command": "ls"})
        assert tc.id == "tu_001"
        assert tc.name == "bash"
        assert tc.input == {"command": "ls"}

    def test_usage_defaults(self):
        """Usage 的默认值应为 0。"""
        usage = Usage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0

    def test_usage_custom(self):
        """Usage 可设置自定义 token 数。"""
        usage = Usage(input_tokens=100, output_tokens=50)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50

    def test_response_defaults(self):
        """Response 应有合理的默认值。"""
        resp = Response(stop_reason="end_turn", content=[])
        assert resp.text == ""
        assert resp.tool_calls == []
        assert resp.usage.input_tokens == 0

    def test_response_with_tool_calls(self):
        """Response 可携带工具调用。"""
        tc = ToolCall(id="tu_1", name="bash", input={"cmd": "ls"})
        resp = Response(
            stop_reason="tool_use",
            content=[{"type": "tool_use", "id": "tu_1", "name": "bash", "input": {"cmd": "ls"}}],
            text="执行中",
            tool_calls=[tc],
            usage=Usage(input_tokens=10, output_tokens=5),
        )
        assert resp.stop_reason == "tool_use"
        assert resp.text == "执行中"
        assert len(resp.tool_calls) == 1
        assert resp.usage.input_tokens == 10


# ═══════════════════════════════════════════════════════════════════════════════
# _parse_response
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseResponse:
    """_parse_response 工具函数测试。"""

    def test_text_only(self):
        """纯文本响应应正确提取。"""
        raw = {
            "content": [{"type": "text", "text": "你好世界"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        resp = _parse_response(raw)
        assert resp.text == "你好世界"
        assert resp.stop_reason == "end_turn"
        assert resp.usage.input_tokens == 10
        assert resp.usage.output_tokens == 5
        assert resp.tool_calls == []

    def test_tool_use_only(self):
        """纯工具调用响应应正确解析。"""
        raw = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu_abc123",
                    "name": "bash",
                    "input": {"command": "ls"},
                }
            ],
            "stop_reason": "tool_use",
            "usage": {},
        }
        resp = _parse_response(raw)
        assert resp.text == ""
        assert resp.stop_reason == "tool_use"
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "bash"
        assert resp.tool_calls[0].input == {"command": "ls"}

    def test_mixed_content(self):
        """文本 + 工具调用混合响应。"""
        raw = {
            "content": [
                {"type": "text", "text": "我来执行"},
                {
                    "type": "tool_use",
                    "id": "tu_def",
                    "name": "read",
                    "input": {"path": "/tmp/test.txt"},
                },
            ],
            "stop_reason": "tool_use",
            "usage": {},
        }
        resp = _parse_response(raw)
        assert resp.text == "我来执行"
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "read"

    def test_multiple_text_blocks(self):
        """多个文本块应拼接。"""
        raw = {
            "content": [
                {"type": "text", "text": "第一段"},
                {"type": "text", "text": "第二段"},
            ],
            "stop_reason": "end_turn",
            "usage": {},
        }
        resp = _parse_response(raw)
        assert resp.text == "第一段第二段"

    def test_multiple_tool_calls(self):
        """多个工具调用应全部解析。"""
        raw = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu_1",
                    "name": "bash",
                    "input": {"command": "ls"},
                },
                {
                    "type": "tool_use",
                    "id": "tu_2",
                    "name": "web_fetch",
                    "input": {"url": "https://example.com"},
                },
            ],
            "stop_reason": "tool_use",
            "usage": {},
        }
        resp = _parse_response(raw)
        assert len(resp.tool_calls) == 2
        assert resp.tool_calls[0].id == "tu_1"
        assert resp.tool_calls[1].id == "tu_2"

    def test_stop_sequence(self):
        """stop_reason 应为 stop_sequence。"""
        raw = {
            "content": [{"type": "text", "text": "done"}],
            "stop_reason": "stop_sequence",
            "usage": {},
        }
        resp = _parse_response(raw)
        assert resp.stop_reason == "stop_sequence"

    def test_max_tokens_stop(self):
        """stop_reason 应为 max_tokens。"""
        raw = {
            "content": [{"type": "text", "text": "截断"}],
            "stop_reason": "max_tokens",
            "usage": {"input_tokens": 100, "output_tokens": 0},
        }
        resp = _parse_response(raw)
        assert resp.stop_reason == "max_tokens"


# ═══════════════════════════════════════════════════════════════════════════════
# AnthropicProvider
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnthropicProviderInit:
    """AnthropicProvider.__init__ 测试。"""

    def test_default_model(self):
        """默认模型应为 claude-sonnet-4-20250514。"""
        p = AnthropicProvider()
        assert p.model == "claude-sonnet-4-20250514"

    def test_custom_api_key(self):
        """构造函数可传入 api_key。"""
        p = AnthropicProvider(api_key="sk-test")
        assert p.api_key == "sk-test"

    def test_custom_model(self):
        """构造函数可指定模型。"""
        p = AnthropicProvider(model="claude-3-5-haiku-latest")
        assert p.model == "claude-3-5-haiku-latest"

    def test_custom_max_tokens(self):
        """构造函数可指定 max_tokens。"""
        p = AnthropicProvider(max_tokens=2048)
        assert p.max_tokens == 2048

    def test_client_lazy_init(self):
        """_client 初始为 None，延迟初始化。"""
        p = AnthropicProvider(api_key="sk-test")
        assert p._client is None


class TestAnthropicProviderGetClient:
    """AnthropicProvider._get_client 测试。"""

    def test_returns_cached_client(self):
        """重复调用应返回缓存的同一客户端实例。"""
        with patch("anthropic.Anthropic") as mock_anthropic:
            p = AnthropicProvider(api_key="sk-test")
            client1 = p._get_client()
            client2 = p._get_client()
            assert client1 is client2
            # Anthropic() 只调用一次
            mock_anthropic.assert_called_once_with(api_key="sk-test")

    def test_fallback_to_env_var(self):
        """未传 api_key 时尝试读取 ANTHROPIC_API_KEY 环境变量。"""
        with (
            patch("anthropic.Anthropic") as mock_anthropic,
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env"}, clear=True),
        ):
            p = AnthropicProvider()
            p._get_client()
            mock_anthropic.assert_called_once_with(api_key="sk-env")

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_raises_value_error(self):
        """无 API key（构造参数和 env 都没有）应抛出 ValueError。"""
        with patch("anthropic.Anthropic"):
            p = AnthropicProvider()
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                p._get_client()

    @patch.dict(os.environ, {}, clear=True)
    def test_get_client_success(self):
        """有 api_key 时 _get_client 应成功返回客户端实例。"""
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_anthropic.return_value = MagicMock()
            p = AnthropicProvider(api_key="sk-test")
            client = p._get_client()
            assert client is not None
            mock_anthropic.assert_called_once_with(api_key="sk-test")


class TestAnthropicProviderInvoke:
    """AnthropicProvider.invoke 测试。"""

    @patch("anthropic.Anthropic")
    def test_invoke_text_response(self, mock_anthropic):
        """invoke 返回文本时应正确解析。"""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        # 模拟 Anthropic API 响应
        raw_response = {
            "content": [{"type": "text", "text": "你好世界"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 15, "output_tokens": 5},
        }
        mock_client.messages.create.return_value.model_dump.return_value = raw_response

        p = AnthropicProvider(api_key="sk-test")
        resp = p.invoke(messages=[{"role": "user", "content": "hi"}])

        assert resp.text == "你好世界"
        assert resp.stop_reason == "end_turn"
        assert resp.usage.input_tokens == 15
        assert len(resp.tool_calls) == 0

    @patch("anthropic.Anthropic")
    def test_invoke_with_tools(self, mock_anthropic):
        """invoke 传入 tools 参数时应透传给 API。"""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        raw_response = {
            "content": [{"type": "text", "text": "done"}],
            "stop_reason": "end_turn",
            "usage": {},
        }
        mock_client.messages.create.return_value.model_dump.return_value = raw_response

        p = AnthropicProvider(api_key="sk-test")
        tools = [{"name": "bash", "description": "Run a command"}]
        p.invoke(messages=[{"role": "user", "content": "run ls"}], tools=tools)

        mock_client.messages.create.assert_called_once()
        _, kwargs = mock_client.messages.create.call_args
        assert kwargs["tools"] == tools
        assert kwargs["model"] == "claude-sonnet-4-20250514"

    @patch("anthropic.Anthropic")
    def test_invoke_tool_use_response(self, mock_anthropic):
        """invoke 返回工具调用时应正确解析。"""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        raw_response = {
            "content": [
                {"type": "text", "text": "执行命令"},
                {
                    "type": "tool_use",
                    "id": "tu_001",
                    "name": "bash",
                    "input": {"command": "ls"},
                },
            ],
            "stop_reason": "tool_use",
            "usage": {},
        }
        mock_client.messages.create.return_value.model_dump.return_value = raw_response

        p = AnthropicProvider(api_key="sk-test")
        resp = p.invoke(messages=[{"role": "user", "content": "run ls"}])

        assert resp.text == "执行命令"
        assert resp.stop_reason == "tool_use"
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "bash"

    @patch("anthropic.Anthropic")
    def test_invoke_custom_model(self, mock_anthropic):
        """自定义模型名称应传递给 API。"""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value.model_dump.return_value = {
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
            "usage": {},
        }

        p = AnthropicProvider(api_key="sk-test", model="claude-3-haiku-20240307")
        p.invoke(messages=[{"role": "user", "content": "hi"}])

        _, kwargs = mock_client.messages.create.call_args
        assert kwargs["model"] == "claude-3-haiku-20240307"


# ═══════════════════════════════════════════════════════════════════════════════
# CompatibleProvider
# ═══════════════════════════════════════════════════════════════════════════════

class TestCompatibleProviderInit:
    """CompatibleProvider.__init__ 测试。"""

    def test_default_values(self):
        """默认 base_url 为 DeepSeek，模型为 deepseek-chat。"""
        p = CompatibleProvider()
        assert p.base_url == "https://api.deepseek.com/v1"
        assert p.model == "deepseek-chat"

    def test_custom_values(self):
        """所有参数都可自定义。"""
        p = CompatibleProvider(
            base_url="https://api.openai.com/v1",
            api_key="sk-xxx",
            model="gpt-4",
            max_tokens=2048,
        )
        assert p.base_url == "https://api.openai.com/v1"
        assert p.api_key == "sk-xxx"
        assert p.model == "gpt-4"
        assert p.max_tokens == 2048

    def test_client_lazy_init(self):
        """_client 初始为 None。"""
        p = CompatibleProvider()
        assert p._client is None


class TestCompatibleProviderGetClient:
    """CompatibleProvider._get_client 测试。"""

    def test_returns_cached_client(self):
        """重复调用应返回缓存实例。"""
        with patch("httpx.Client") as mock_httpx_cls:
            p = CompatibleProvider(api_key="sk-test")
            client1 = p._get_client()
            client2 = p._get_client()
            assert client1 is client2
            mock_httpx_cls.assert_called_once()

    def test_passes_base_url_and_headers(self):
        """httpx.Client 应使用正确的 base_url 和 Authorization header。"""
        with patch("httpx.Client") as mock_httpx_cls:
            p = CompatibleProvider(api_key="sk-test", base_url="https://custom.api.com/v1")
            p._get_client()
            mock_httpx_cls.assert_called_once()
            _, kwargs = mock_httpx_cls.call_args
            assert kwargs["base_url"] == "https://custom.api.com/v1"
            assert "Authorization" in kwargs["headers"]
            assert kwargs["headers"]["Authorization"] == "Bearer sk-test"

    def test_env_var_fallback(self):
        """未传 api_key 时尝试读取 COMPATIBLE_API_KEY。"""
        with (
            patch("httpx.Client") as mock_httpx_cls,
            patch.dict(os.environ, {"COMPATIBLE_API_KEY": "sk-env"}, clear=True),
        ):
            p = CompatibleProvider()
            p._get_client()
            _, kwargs = mock_httpx_cls.call_args
            assert kwargs["headers"]["Authorization"] == "Bearer sk-env"

    def test_missing_key_uses_empty_bearer(self):
        """无 API key 时使用空 Bearer token（服务端会拒绝），不抛异常。"""
        with patch("httpx.Client") as mock_httpx_cls, patch.dict(os.environ, {}, clear=True):
            p = CompatibleProvider()
            p._get_client()
            _, kwargs = mock_httpx_cls.call_args
            assert kwargs["headers"]["Authorization"] == "Bearer "


class TestCompatibleProviderInvoke:
    """CompatibleProvider.invoke 测试。"""

    def _make_provider(self, **kwargs) -> CompatibleProvider:
        """创建预设好的 CompatibleProvider（使用 mock client）。"""
        return CompatibleProvider(api_key="sk-test", **kwargs)

    def _mock_post(self, mock_client: MagicMock, json_data: dict, status_code: int = 200):
        """设置 mock_client.post 的返回值。"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = json_data
        mock_resp.status_code = status_code
        mock_resp.raise_for_status.return_value = None
        mock_client.post.return_value = mock_resp
        return mock_resp

    def test_invoke_text_response(self):
        """普通文本响应应正确解析。"""
        with patch("httpx.Client") as mock_httpx_cls:
            mock_client = MagicMock()
            mock_httpx_cls.return_value = mock_client

            self._mock_post(mock_client, {
                "choices": [
                    {
                        "message": {"content": "你好世界"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            })

            p = self._make_provider()
            resp = p.invoke(messages=[{"role": "user", "content": "hi"}])

            assert resp.text == "你好世界"
            assert resp.stop_reason == "end_turn"
            assert resp.usage.input_tokens == 10
            assert resp.usage.output_tokens == 5
            assert len(resp.tool_calls) == 0

    def test_invoke_tool_calls(self):
        """工具调用响应应正确映射为内部格式。"""
        with patch("httpx.Client") as mock_httpx_cls:
            mock_client = MagicMock()
            mock_httpx_cls.return_value = mock_client

            self._mock_post(mock_client, {
                "choices": [
                    {
                        "message": {
                            "content": "执行命令",
                            "tool_calls": [
                                {
                                    "id": "call_001",
                                    "type": "function",
                                    "function": {
                                        "name": "bash",
                                        "arguments": '{"command": "ls"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {},
            })

            p = self._make_provider()
            resp = p.invoke(messages=[{"role": "user", "content": "run ls"}])

            assert resp.text == "执行命令"
            assert resp.stop_reason == "tool_use"
            assert len(resp.tool_calls) == 1
            assert resp.tool_calls[0].name == "bash"
            assert resp.tool_calls[0].input == {"command": "ls"}

    def test_invoke_multiple_tool_calls(self):
        """多个工具调用应全部解析。"""
        with patch("httpx.Client") as mock_httpx_cls:
            mock_client = MagicMock()
            mock_httpx_cls.return_value = mock_client

            self._mock_post(mock_client, {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "bash",
                                        "arguments": '{"command": "ls"}',
                                    },
                                },
                                {
                                    "id": "call_2",
                                    "type": "function",
                                    "function": {
                                        "name": "web_fetch",
                                        "arguments": '{"url": "https://example.com"}',
                                    },
                                },
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {},
            })

            p = self._make_provider()
            resp = p.invoke(messages=[{"role": "user", "content": "do both"}])

            assert len(resp.tool_calls) == 2
            assert resp.tool_calls[0].name == "bash"
            assert resp.tool_calls[1].name == "web_fetch"

    def test_invoke_passes_body(self):
        """POST 请求体应包含 model / messages / max_tokens。"""
        with patch("httpx.Client") as mock_httpx_cls:
            mock_client = MagicMock()
            mock_httpx_cls.return_value = mock_client

            self._mock_post(mock_client, {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {},
            })

            p = self._make_provider(model="deepseek-coder", max_tokens=2048)
            p.invoke(messages=[{"role": "user", "content": "hi"}])

            mock_client.post.assert_called_once()
            _, kwargs = mock_client.post.call_args
            assert kwargs["json"]["model"] == "deepseek-coder"
            assert kwargs["json"]["max_tokens"] == 2048
            assert len(kwargs["json"]["messages"]) == 1

    def test_invoke_http_error(self):
        """HTTP 错误应返回包含 error 信息的 Response。"""
        with patch("httpx.Client") as mock_httpx_cls:
            mock_client = MagicMock()
            mock_httpx_cls.return_value = mock_client

            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = Exception("HTTP 500")
            mock_client.post.return_value = mock_resp

            p = self._make_provider()
            resp = p.invoke(messages=[{"role": "user", "content": "hi"}])

            assert "API 调用失败" in resp.text
            assert resp.stop_reason == "end_turn"

    def test_invoke_general_exception(self):
        """通用异常应返回包含错误信息的 Response。"""
        with patch("httpx.Client") as mock_httpx_cls:
            mock_client = MagicMock()
            mock_httpx_cls.return_value = mock_client
            mock_client.post.side_effect = ConnectionError("连接被拒绝")

            p = self._make_provider()
            resp = p.invoke(messages=[{"role": "user", "content": "hi"}])

            assert "API 调用失败" in resp.text
            assert "连接被拒绝" in resp.text

    def test_no_content_in_response(self):
        """content 为 None 的响应应处理为空字符串。"""
        with patch("httpx.Client") as mock_httpx_cls:
            mock_client = MagicMock()
            mock_httpx_cls.return_value = mock_client

            self._mock_post(mock_client, {
                "choices": [
                    {
                        "message": {"content": None},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {},
            })

            p = self._make_provider()
            resp = p.invoke(messages=[{"role": "user", "content": "hi"}])

            assert resp.text == ""


# ═══════════════════════════════════════════════════════════════════════════════
# MockProvider（增强）
# ═══════════════════════════════════════════════════════════════════════════════

class TestMockProvider:
    """MockProvider 补充测试（核心路径已在 loop 测试中覆盖）。"""

    def test_default_response(self):
        """默认 greeting 应包含 Agent-CLI。"""
        p = MockProvider()
        resp = p.invoke(messages=[{"role": "user", "content": "hello"}])
        assert "Agent-CLI" in resp.text

    def test_call_count(self):
        """call_count 应递增。"""
        p = MockProvider()
        assert p.call_count == 0
        p.invoke(messages=[{"role": "user", "content": "hi"}])
        assert p.call_count == 1
        p.invoke(messages=[{"role": "user", "content": "hi"}])
        assert p.call_count == 2

    def test_help_response(self):
        """包含"帮助"的消息应返回帮助文本。"""
        p = MockProvider()
        resp = p.invoke(messages=[{"role": "user", "content": "请帮助我"}])
        assert "bash" in resp.text or "文件" in resp.text

    def test_tool_trigger_bash(self):
        """含"执行"的消息应触发工具调用。"""
        p = MockProvider()
        resp = p.invoke(messages=[{"role": "user", "content": "执行 ls 命令"}])
        assert resp.stop_reason == "tool_use"
        assert len(resp.tool_calls) > 0
        assert resp.tool_calls[0].name == "bash"

    def test_tool_trigger_search(self):
        """含"搜索"的消息应触发 grep 工具调用。"""
        p = MockProvider()
        resp = p.invoke(messages=[{"role": "user", "content": "搜索 TODO 标记"}])
        assert resp.stop_reason == "tool_use"
        assert resp.tool_calls[0].name == "grep"

    def test_tool_trigger_fetch(self):
        """_guess_tool 含"fetch"时应返回 web_fetch。"""
        p = MockProvider()
        name, _ = p._guess_tool("fetch example.com")
        assert name == "web_fetch"

    def test_tool_trigger_create(self):
        """含"创建"的消息应触发 write。"""
        p = MockProvider()
        resp = p.invoke(messages=[{"role": "user", "content": "创建文件 test.txt"}])
        assert resp.stop_reason == "tool_use"
        assert resp.tool_calls[0].name == "write"

    def test_extract_text_from_string(self):
        """_extract_text 应正确处理字符串。"""
        p = MockProvider()
        assert p._extract_text("hello") == "hello"

    def test_extract_text_from_blocks(self):
        """_extract_text 应正确处理 content blocks。"""
        p = MockProvider()
        blocks = [{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}]
        assert p._extract_text(blocks) == "hello world"

    def test_extract_text_from_non_text_blocks(self):
        """_extract_text 应跳过非 text 类型的 block。"""
        p = MockProvider()
        blocks = [
            {"type": "text", "text": "hello"},
            {"type": "tool_use", "id": "tu_1", "name": "bash", "input": {}},
        ]
        assert p._extract_text(blocks) == "hello"
