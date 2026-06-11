"""DeepSeek 真实模型集成测试（VCR 录制/回放）。

测试内容：
  1. 基础文本补全（非流式）
  2. System message 传递
  3. 流式响应
  4. 无效 API key 错误处理
  5. 无效 base URL 错误处理

首次运行需要设置 DEEPSEEK_API_KEY 环境变量以录制 cassette，
之后回放无需 API key。
"""

from __future__ import annotations

from agent_cli.core.provider import CompatibleProvider, DeepSeekProvider

from .conftest import vcr_config


class TestDeepSeekCompletion:
    """DeepSeek 非流式补全测试。"""

    @vcr_config.use_cassette("deepseek-text.yaml")
    def test_text_completion(self, deepseek_provider: DeepSeekProvider):
        """基础文本补全应返回非空响应。"""
        messages = [{"role": "user", "content": "请用一句话介绍 Python 编程语言的特点"}]
        resp = deepseek_provider.invoke(messages)
        assert resp.stop_reason == "end_turn"
        assert len(resp.text) > 0
        assert "Python" in resp.text or "python" in resp.text

    @vcr_config.use_cassette("deepseek-system.yaml")
    def test_system_message(self, deepseek_provider: DeepSeekProvider):
        """System message 应被模型遵循。"""
        messages = [
            {"role": "system", "content": "你是一个只回答中文的助手，所有回复必须使用中文。"},
            {"role": "user", "content": "Say hello in any language"},
        ]
        resp = deepseek_provider.invoke(messages)
        assert resp.stop_reason == "end_turn"
        assert len(resp.text) > 0
        # 应该用中文回复
        assert any("一" <= ch <= "鿿" for ch in resp.text)

    @vcr_config.use_cassette("deepseek-stream.yaml")
    def test_streaming(self, deepseek_provider: DeepSeekProvider):
        """流式调用应逐块产出文本，最终拼接为完整回复。"""
        messages = [{"role": "user", "content": "数三个数字：1 2 3"}]
        chunks = list(deepseek_provider.invoke_stream(messages))
        assert len(chunks) > 0
        full = "".join(chunks)
        assert len(full) > 0
        # 流式结果应包含数字相关内容
        assert any(d in full for d in ("1", "2", "3"))


class TestDeepSeekErrors:
    """错误处理测试 — 这些不需要 VCR（因为请求不会成功）。"""

    def test_invalid_api_key(self):
        """无效 API key 返回错误信息而非崩溃。"""
        provider = DeepSeekProvider(
            api_key="sk-invalid-key-xxx",
            model="deepseek-chat",
            max_tokens=256,
        )
        messages = [{"role": "user", "content": "hi"}]
        resp = provider.invoke(messages)
        assert resp.stop_reason == "end_turn"
        assert "失败" in resp.text or "error" in resp.text.lower() or "401" in resp.text

    def test_invalid_base_url(self):
        """无效 base URL 返回错误信息而非崩溃。"""
        provider = CompatibleProvider(
            base_url="https://api.invalid-url-xxx.com/v1",
            api_key="sk-test",
            model="deepseek-chat",
            max_tokens=256,
        )
        messages = [{"role": "user", "content": "hi"}]
        resp = provider.invoke(messages)
        assert resp.stop_reason == "end_turn"
        assert "失败" in resp.text or "error" in resp.text.lower()
