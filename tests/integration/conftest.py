"""集成测试共享 fixtures — VCR 配置 + Provider 初始化。

设计原则：
  - 首次运行需要 COMPATIBLE_API_KEY 环境变量，录制真实 API 响应到 cassette
  - 后续运行回放 cassette，无需 API key（VCR 拦截 HTTP 请求）
  - Authorization 头在 cassette 中自动过滤，避免泄露
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import vcr

from agent_cli.core.provider import DeepSeekProvider

# ─── VCR 配置 ──────────────────────────────────────────────────────

CASSETTE_DIR = Path(__file__).parent / "cassettes"

vcr_config = vcr.VCR(
    cassette_library_dir=str(CASSETTE_DIR),
    record_mode="once",
    filter_headers=[("authorization", "[FILTERED]")],
    filter_query_parameters=["api_key", "api-key", "key"],
)


def _get_deepseek_key() -> str | None:
    return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("COMPATIBLE_API_KEY")


@pytest.fixture
def deepseek_key() -> str | None:
    """DeepSeek API key fixture。

    有 cassette 时不要求 key（VCR 会回放），
    无 cassette 时 pytest.skip。
    """
    key = _get_deepseek_key()
    has_cassettes = any(CASSETTE_DIR.glob("*.yaml"))
    if not key and not has_cassettes:
        pytest.skip("无 API key 且无 cassette，跳过集成测试。设置 DEEPSEEK_API_KEY 后重试。")
    return key  # None 是允许的 — VCR 回放时不需要真实 key


@pytest.fixture
def deepseek_provider(deepseek_key: str | None) -> DeepSeekProvider:
    """已配置的 DeepSeekProvider fixture。

    key 为 None 时仍然创建 provider（VCR 回放模式下不会实际发起 HTTP 请求）。
    """
    return DeepSeekProvider(
        api_key=deepseek_key or "",
        model="deepseek-chat",
        max_tokens=1024,
    )
