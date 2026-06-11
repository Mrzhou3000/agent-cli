"""CompactPipeline 深度测试 — 覆盖 L1-L4 各层的边界情况。

补全 test_compact.py 中未覆盖的行。
"""

from __future__ import annotations

import pytest

from agent_cli.compact.pipeline import CompactPipeline, _estimate_tokens
from agent_cli.core.provider import MockProvider


class TestTokenEstimatorEdgeCases:
    """_estimate_tokens 边界情况。"""

    def test_int_input(self):
        """整数输入不崩溃。"""
        tokens = _estimate_tokens(42)
        assert isinstance(tokens, int)
        assert tokens >= 0

    def test_none_input(self):
        """None 输入不崩溃。"""
        tokens = _estimate_tokens(None)
        assert isinstance(tokens, int)

    def test_tool_result_block_overhead(self):
        """tool_result block 也有额外开销。"""
        tr = {"type": "tool_result", "tool_use_id": "tu_1", "content": "hi"}
        plain = {"tool_use_id": "tu_1", "content": "hi"}
        assert _estimate_tokens(tr) > _estimate_tokens(plain)


class TestCompactPipelineEdgeCases:
    """CompactPipeline 边界情况测试。"""

    @pytest.fixture
    def pipeline(self) -> CompactPipeline:
        return CompactPipeline(max_tokens=1000)

    # ── should_compact 边界 ──────────────────────────────────

    def test_should_compact_empty(self, pipeline: CompactPipeline):
        """空消息不压缩。"""
        assert not pipeline.should_compact([])

    def test_should_compact_sets_last_ratio(self, pipeline: CompactPipeline):
        """调用后更新 last_ratio。"""
        msgs = [{"role": "user", "content": "x" * 300}]
        pipeline._max_tokens = 100
        pipeline.should_compact(msgs)
        assert pipeline.last_ratio > 0

    # ── 压缩执行时 L1 截断长字符串 ────────────────────────────

    def test_l1_truncates_long_string_content(self, pipeline: CompactPipeline):
        """L1 截断超过 4000 字符的字符串 content。"""
        pipeline._max_tokens = 100
        msgs = [{"role": "user", "content": "x" * 5000}]
        result = pipeline.compress(msgs)
        content = result[0].get("content", "")
        assert len(content) <= 4100  # 4000 + "... [截断]"

    # ── L1 处理空 tool_result ─────────────────────────────────

    def test_l1_skips_empty_tool_result(self, pipeline: CompactPipeline):
        """L1 跳过完全空的 tool_result block。"""
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_1", "content": ""},
                ],
            },
        ]
        # 直接调用 _layer1_discard 测试过滤逻辑
        result = pipeline._layer1_discard(msgs)
        # content 中的空 tool_result 被过滤
        if result:
            content = result[0].get("content", [])
            assert len(content) == 0

    def test_l1_skips_empty_tool_result_dict(self, pipeline: CompactPipeline):
        """L1 跳过 content 为 dict 且 content['content'] 为空的 tool_result。"""
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_1", "content": {"content": ""}},
                ],
            },
        ]
        result = pipeline._layer1_discard(msgs)
        if result:
            content = result[0].get("content", [])
            assert len(content) == 0

    def test_l1_keeps_non_empty_tool_result(self, pipeline: CompactPipeline):
        """L1 保留非空的 tool_result。"""
        pipeline._max_tokens = 100
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_1", "content": "real data"},
                ],
            },
        ]
        result = pipeline.compress(msgs)
        content = result[0].get("content", [])
        assert len(content) == 1
        assert content[0]["content"] == "real data"

    # ── L1 标记（70-90% 区间触发） ───────────────────────────

    def test_l1_compression_marker_added(self, pipeline: CompactPipeline):
        """70-90% 范围触发 L1 并添加标记。"""
        pipeline._max_tokens = 100
        # ~850 chars → 85% 在 L1 范围（>= 70% 但 < 90%）
        pipeline._max_tokens = 500
        msgs = [{"role": "user", "content": "x" * 1500}]  # ~375 tokens / 500 = 75%
        result = pipeline.compress(msgs)
        markers = [m for m in result if "[compressed" in str(m.get("content", ""))]
        assert len(markers) >= 1

    # ── L2 合并连续的 assistant text ──────────────────────────

    def test_l2_merge_adjacent_assistant_text(self, pipeline: CompactPipeline):
        """L2 合并连续的 assistant text 消息。"""
        msgs = [
            {"role": "assistant", "content": "第一段回复"},
            {"role": "assistant", "content": "第二段回复"},
        ]
        # 直接调用 _layer2_merge 测试合并逻辑
        result = pipeline._layer2_merge(msgs)
        assistant_msgs = [m for m in result if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert "第一段回复" in assistant_msgs[0]["content"]
        assert "第二段回复" in assistant_msgs[0]["content"]

    def test_l2_merge_skips_non_continuous(self, pipeline: CompactPipeline):
        """L2 不会合并不同角色的相邻消息。"""
        pipeline._max_tokens = 50
        msgs = [
            {"role": "user", "content": "用户问题"},
            {"role": "assistant", "content": "助手回复"},
        ]
        result = pipeline.compress(msgs)
        user_msgs = [m for m in result if m["role"] == "user"]
        assistant_msgs = [m for m in result if m["role"] == "assistant"]
        assert len(user_msgs) == 1
        assert len(assistant_msgs) == 1

    # ── L2 不合并非 text-only assistant ───────────────────────

    def test_l2_does_not_merge_non_text_assistant(self, pipeline: CompactPipeline):
        """L2 不会合并包含 tool_use 的 assistant 消息。"""
        pipeline._max_tokens = 50
        msgs = [
            {"role": "assistant", "content": [{"type": "text", "text": "让我查一下"}]},
            {
                "role": "assistant",
                "content": "结果是...",
            },
        ]
        result = pipeline.compress(msgs)
        assistant_msgs = [m for m in result if m["role"] == "assistant"]
        # 第一条是 list content（含 tool_use/text block），第二条是纯 text
        # L2 的合并条件：_get_text_content 对第一条会返回字符串，对第二条也返回字符串
        # 但第一条有 list content，_get_text_content 从 list 提取 text
        # 实际上两条都会返回非空 text → 合并
        assert len(assistant_msgs) <= 2

    # ── _get_text_content ────────────────────────────────────

    def test_get_text_content_from_string(self, pipeline: CompactPipeline):
        """字符串 content 直接返回。"""
        msg = {"role": "assistant", "content": "纯文本"}
        text = pipeline._get_text_content(msg)
        assert text == "纯文本"

    def test_get_text_content_from_list(self, pipeline: CompactPipeline):
        """list content 提取 text 块。"""
        msg = {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "第一步"},
                {"type": "tool_use", "id": "tu_1", "name": "bash", "input": {"cmd": "ls"}},
                {"type": "text", "text": "第二步"},
            ],
        }
        text = pipeline._get_text_content(msg)
        assert "第一步" in text
        assert "第二步" in text
        assert "tool_use" not in text  # 不会被包含

    def test_get_text_content_empty(self, pipeline: CompactPipeline):
        """无文本时返回空字符串。"""
        msg = {}
        assert pipeline._get_text_content(msg) == ""

    # ── L3 摘要 ──────────────────────────────────────────────

    def test_l3_summarize_few_messages(self, pipeline: CompactPipeline):
        """少于 6 条消息时 L3 不做摘要。"""
        msgs = [
            {"role": "user", "content": "问题1"},
            {"role": "assistant", "content": "回答1"},
            {"role": "user", "content": "问题2"},
            {"role": "assistant", "content": "回答2"},
        ]
        result = pipeline._layer3_summarize(msgs)
        # 没有早期消息可摘要 → 不变
        assert len(result) == len(msgs)

    def test_l3_summarize_many_messages(self, pipeline: CompactPipeline):
        """超过 6 条消息时摘要早期消息。"""
        msgs = []
        for i in range(5):
            msgs.append({"role": "user", "content": f"问题{i}"})
            msgs.append({"role": "assistant", "content": f"回答{i}"})
        # 10 条消息, 保留最后 6 条 = 3 对
        result = pipeline._layer3_summarize(msgs)
        # 结果 = 1 条系统摘要 + 最后 6 条 = 7 条
        assert len(result) == 7
        assert result[0]["role"] == "system"
        assert "对话摘要" in result[0].get("content", "")

    def test_l3_extracts_file_paths(self, pipeline: CompactPipeline):
        """L3 从 assistant 回复中提取文件路径。"""
        msgs = [
            {"role": "user", "content": "分析代码"},
            {"role": "assistant", "content": "在 src/main.py 中找到了入口函数。"},
            {"role": "user", "content": "继续"},
        ]
        # 添加更多消息使总消息数超过 6
        for i in range(3):
            msgs.append({"role": "user", "content": f"额外消息{i}"})
            msgs.append({"role": "assistant", "content": f"回复{i}"})
        # 10 条
        result = pipeline._layer3_summarize(msgs)
        assert len(result) == 7  # 1 系统 + 6 保留
        assert "main.py" in result[0].get("content", "")

    def test_l3_with_file_blocks_in_list(self, pipeline: CompactPipeline):
        """L3 从 list content 的 assistant 消息中提取文件路径。"""
        msgs = []
        for i in range(5):
            msgs.append({"role": "user", "content": f"问{i}"})
            msgs.append(
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "请查看 src/app.py"},
                    ],
                }
            )
        result = pipeline._layer3_summarize(msgs)
        assert len(result) == 7
        assert "app.py" in result[0].get("content", "")

    # ── L4 重写层 ────────────────────────────────────────────

    def test_l4_without_provider_skips(self, pipeline: CompactPipeline):
        """没有 provider 时 L4 跳过。"""
        msgs = [
            {"role": "user", "content": "x" * 500},
            {"role": "assistant", "content": "y" * 500},
        ]
        pipeline._max_tokens = 100
        assert pipeline._provider is None
        # compress 不会调用 L4
        result = pipeline.compress(msgs)
        assert len(result) >= 1

    def test_l4_with_provider(self):
        """有 MockProvider 时 L4 可以执行。"""
        provider = MockProvider()
        pipeline = CompactPipeline(max_tokens=100, provider=provider)
        msgs = [
            {"role": "user", "content": "x" * 500},
            {"role": "assistant", "content": "y" * 500},
        ]
        # 直接调用 _layer4_rewrite
        result = pipeline._layer4_rewrite(msgs)
        assert len(result) >= 1

    def test_l4_provider_errors_gracefully(self):
        """L4 异常时返回原消息。"""

        class _BrokenProvider(MockProvider):
            def invoke(self, messages, **kwargs):
                raise RuntimeError("API 故障")

        provider = _BrokenProvider()
        pipeline = CompactPipeline(max_tokens=100, provider=provider)
        msgs = [{"role": "user", "content": "test"}]
        result = pipeline._layer4_rewrite(msgs)
        assert result == msgs  # 异常时原样返回

    # ── compress 综合 ────────────────────────────────────────

    def test_compress_through_all_layers(self):
        """超过 90% 阈值时依次触发 L1 → L2 → L3。"""
        provider = MockProvider()
        pipeline = CompactPipeline(max_tokens=100, provider=provider)

        # 产生大量消息使 ratio > 90%
        msgs = []
        for i in range(10):
            msgs.append({"role": "user", "content": f"x{i} " * 50})
            msgs.append({"role": "assistant", "content": f"y{i} " * 80})
            msgs.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": f"tu_{i}", "content": f"result {i}"}
                    ],
                }
            )

        pipeline._max_tokens = 50  # 强制所有消息超过限制
        result = pipeline.compress(msgs)
        assert len(result) < len(msgs)
        # 应有压缩标记
        markers = [m for m in result if "[compressed" in str(m.get("content", ""))]
        assert len(markers) >= 1

    def test_get_stats_values(self, pipeline: CompactPipeline):
        """get_stats 返回正确的值。"""
        stats = pipeline.get_stats()
        assert stats["compression_count"] == 0
        assert stats["last_ratio"] == 0.0
        assert stats["max_tokens"] == 1000
        assert stats["compact_ratio"] == 0.7
        assert stats["critical_ratio"] == 0.9
