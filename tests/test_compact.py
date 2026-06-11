"""CompactPipeline 测试。"""

from __future__ import annotations

import pytest
from agent_cli.compact.pipeline import CompactPipeline, _estimate_tokens


class TestTokenEstimator:
    """Token 估算工具测试。"""

    def test_string_tokens(self):
        """测试字符串 Token 估算。"""
        tokens = _estimate_tokens("hello world")
        assert tokens > 0

    def test_empty_string(self):
        assert _estimate_tokens("") == 0

    def test_list_tokens(self):
        tokens = _estimate_tokens([{"type": "text", "text": "hello"}])
        assert tokens > 0

    def test_dict_tokens(self):
        tokens = _estimate_tokens({"role": "user", "content": "hello"})
        assert tokens > 0

    def test_tool_block_overhead(self):
        """tool block 有额外开销。"""
        tool_block = {
            "type": "tool_use",
            "id": "tu_123",
            "name": "bash",
            "input": {"command": "echo hi"},
        }
        plain_block = {"id": "tu_123", "name": "bash", "input": {"command": "echo hi"}}
        assert _estimate_tokens(tool_block) > _estimate_tokens(plain_block)


class TestCompactPipeline:
    """CompactPipeline 核心功能测试。"""

    @pytest.fixture
    def pipeline(self) -> CompactPipeline:
        return CompactPipeline(max_tokens=1000)

    def make_messages(self, count: int) -> list[dict]:
        """生成测试用消息。"""
        msgs = []
        for i in range(count):
            msgs.append({"role": "user", "content": f"测试消息 {i} " * 20})
            msgs.append({"role": "assistant", "content": f"回复消息 {i} " * 30})
        return msgs

    def test_should_compact_below_threshold(self, pipeline: CompactPipeline):
        """低于阈值的消息不触发压缩。"""
        msgs = [{"role": "user", "content": "短消息"}]
        assert not pipeline.should_compact(msgs)

    def test_should_compact_above_threshold(self, pipeline: CompactPipeline):
        """超过 70% 阈值时触发压缩。"""
        pipeline._max_tokens = 100
        msgs = [{"role": "user", "content": "x" * 300}]
        assert pipeline.should_compact(msgs)

    def test_compress_below_threshold(self, pipeline: CompactPipeline):
        """低于阈值的 compress 是空操作。"""
        msgs = [{"role": "user", "content": "短消息"}]
        result = pipeline.compress(msgs)
        assert len(result) == len(msgs)

    def test_l1_discard_truncates_long_content(self, pipeline: CompactPipeline):
        """L1 截断过长的 tool_result。"""
        long_result = [{"type": "tool_result", "tool_use_id": "tu_1", "content": "x" * 5000}]
        msgs = [{"role": "user", "content": long_result}]
        pipeline._max_tokens = 50
        result = pipeline.compress(msgs)
        # 应该被截断或处理
        content = result[0]["content"]
        if isinstance(content, list):
            block_content = content[0].get("content", "")
            assert len(block_content) <= 2100  # 截断后

    def test_l3_summarize_reduces_message_count(self, pipeline: CompactPipeline):
        """L3 摘要减少消息数量。"""
        msgs = self.make_messages(8)  # 16 条消息
        pipeline._max_tokens = 50
        result = pipeline.compress(msgs)
        assert len(result) < len(msgs)

    def test_compression_stats(self, pipeline: CompactPipeline):
        """压缩后统计信息可查。"""
        msgs = [{"role": "user", "content": "x" * 50}]
        pipeline.compress(msgs)
        stats = pipeline.get_stats()
        assert "compression_count" in stats
        assert "max_tokens" in stats

    def test_empty_messages(self, pipeline: CompactPipeline):
        """空消息列表不报错。"""
        assert pipeline.compress([]) == []
        assert not pipeline.should_compact([])

    def test_layer2_merge_adjacent_tool_results(self, pipeline: CompactPipeline):
        """L2 合并相邻的 tool_result。"""
        msgs = [
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "tu_1", "content": "a"}],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "tu_2", "content": "b"}],
            },
        ]
        pipeline._max_tokens = 10
        result = pipeline.compress(msgs)
        # 合并后应该只有 1 条 user 消息（+ 可能的压缩标记）
        user_msgs = [m for m in result if m["role"] == "user"]
        assert len(user_msgs) <= 1

    def test_compression_marker(self, pipeline: CompactPipeline):
        """压缩后添加标记。"""
        msgs = [{"role": "user", "content": "x" * 300}]
        pipeline._max_tokens = 100
        result = pipeline.compress(msgs)
        markers = [
            m
            for m in result
            if m["role"] == "system" and "[compressed" in str(m.get("content", ""))
        ]
        assert len(markers) >= 1
