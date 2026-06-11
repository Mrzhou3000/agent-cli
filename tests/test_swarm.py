"""Swarm Coordinator 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent_cli.subagent.manager import SubagentResult
from agent_cli.swarm.coordinator import Coordinator, CoordinatorResult, VoteResult


class TestCoordinatorResult:
    """CoordinatorResult 数据类测试。"""

    def test_success_failure_count_all_success(self):
        result = CoordinatorResult(
            pattern="sequential",
            results=[
                SubagentResult(task="t1", output="ok"),
                SubagentResult(task="t2", output="ok"),
            ],
        )
        assert result.success_count == 2
        assert result.failure_count == 0

    def test_success_failure_count_mixed(self):
        result = CoordinatorResult(
            pattern="parallel",
            results=[
                SubagentResult(task="t1", output="ok"),
                SubagentResult(task="t2", error="失败"),
                SubagentResult(task="t3", output="ok"),
            ],
        )
        assert result.success_count == 2
        assert result.failure_count == 1


class TestVoteResult:
    """VoteResult 数据类测试。"""

    def test_consensus_yes(self):
        result = VoteResult(question="test?", agreement=4, disagreement=1)
        assert result.consensus is True

    def test_consensus_no(self):
        result = VoteResult(question="test?", agreement=3, disagreement=3)
        assert result.consensus is False

    def test_consensus_empty(self):
        result = VoteResult(question="test?")
        assert result.consensus is False

    def test_consensus_no_records(self):
        result = VoteResult(question="test?", agreement=0, disagreement=0)
        assert result.consensus is False


class TestCoordinator:
    """Coordinator 核心功能测试。"""

    @pytest.fixture
    def mock_manager(self):
        """创建模拟的 SubagentManager。"""
        mgr = MagicMock()

        def spawn_side_effect(task, context=None, provider=None):
            return SubagentResult(task=task, output=f"完成: {task[:20]}")

        mgr.spawn.side_effect = spawn_side_effect
        return mgr

    @pytest.fixture
    def coordinator(self, mock_manager):
        return Coordinator(subagent_manager=mock_manager)

    def test_init(self, mock_manager):
        coord = Coordinator(subagent_manager=mock_manager)
        assert coord._max_workers == 5

    def test_init_custom(self, mock_manager):
        coord = Coordinator(subagent_manager=mock_manager, max_workers=10)
        assert coord._max_workers == 10

    def test_sequential_basic(self, coordinator, mock_manager):
        result = coordinator.sequential(["task1", "task2"])
        assert result.pattern == "sequential"
        assert len(result.results) == 2
        assert result.success_count == 2
        assert mock_manager.spawn.call_count == 2

    def test_sequential_single_task(self, coordinator, mock_manager):
        result = coordinator.sequential(["only task"])
        assert len(result.results) == 1
        assert result.results[0].success

    def test_sequential_preserves_context(self, coordinator, mock_manager):
        result = coordinator.sequential(
            ["step1", "step2"],
            context={"project": "test"},
        )
        assert len(result.results) == 2
        # 验证第一次调用有 project 上下文
        first_call_args = mock_manager.spawn.call_args_list[0]
        assert first_call_args[1].get("context", {}).get("project") == "test"

    def test_parallel_basic(self, coordinator, mock_manager):
        result = coordinator.parallel(["search A", "search B", "search C"])
        assert result.pattern == "parallel"
        assert len(result.results) == 3
        assert result.success_count == 3

    def test_parallel_single(self, coordinator, mock_manager):
        result = coordinator.parallel(["only task"])
        assert len(result.results) == 1

    def test_parallel_empty(self, coordinator):
        result = coordinator.parallel([])
        assert len(result.results) == 0
        assert result.success_count == 0

    def test_vote_consensus(self, coordinator, mock_manager):
        """测试投票达成共识。"""
        # 所有投票者返回同意
        mock_manager.spawn.return_value = SubagentResult(
            task="vote",
            output="同意，这个方案可行。",
        )
        result = coordinator.vote("这个方案好吗?", voters=3)
        assert result.agreement >= 1

    def test_vote_no_consensus(self, coordinator, mock_manager):
        """测试投票未达成共识。"""
        # 交替返回同意/反对
        outputs = ["同意", "反对", "不确定"]
        mock_manager.spawn.side_effect = [SubagentResult(task="v1", output=o) for o in outputs]
        result = coordinator.vote("这个方案好吗?", voters=3)
        assert len(result.votes) == 3

    def test_vote_custom_voters(self, coordinator, mock_manager):
        mock_manager.spawn.return_value = SubagentResult(task="vote", output="同意")
        result = coordinator.vote("test?", voters=5)
        assert len(result.votes) == 5

    def test_debate_basic(self, coordinator, mock_manager):
        mock_manager.spawn.return_value = SubagentResult(
            task="debate",
            output="这是论点",
        )
        result = coordinator.debate("微服务还是单体?")
        assert result.pattern == "debate"
        # 每轮2个发言（正反方）
        assert len(result.results) == 4  # 2 rounds × 2
        assert "辩论总结" in result.summary

    def test_debate_custom_rounds(self, coordinator, mock_manager):
        mock_manager.spawn.return_value = SubagentResult(
            task="debate",
            output="论点",
        )
        result = coordinator.debate("test?", rounds=3)
        assert len(result.results) == 6  # 3 rounds × 2

    def test_sequential_failure_handling(self, coordinator, mock_manager):
        """测试顺序执行中某个任务失败。"""
        mock_manager.spawn.side_effect = [
            SubagentResult(task="t1", output="ok"),
            SubagentResult(task="t2", error="失败了"),
            SubagentResult(task="t3", output="ok"),
        ]
        result = coordinator.sequential(["t1", "t2", "t3"])
        assert result.success_count == 2
        assert result.failure_count == 1
        # t3 应该仍然执行了（错误不影响后续）
        assert mock_manager.spawn.call_count == 3

    def test_summary_sequential(self, coordinator):
        results = [
            SubagentResult(task="t1", output="完成1"),
            SubagentResult(task="t2", output="完成2"),
        ]
        summary = coordinator._summarize_sequential(results, ["t1", "t2"])
        assert "顺序执行摘要" in summary
        assert "完成1" in summary
        assert "完成2" in summary

    def test_summary_parallel(self, coordinator):
        results = [
            SubagentResult(task="t1", output="结果1"),
            SubagentResult(task="t2", error="失败"),
        ]
        summary = coordinator._summarize_parallel(results, ["t1", "t2"], [])
        assert "并行执行摘要" in summary
        assert "结果1" in summary

    def test_synthesize_debate(self, coordinator):
        results = [
            SubagentResult(task="pro1", output="支持论点"),
            SubagentResult(task="con1", output="反对论点"),
        ]
        summary = coordinator._synthesize_debate("测试主题", results)
        assert "正方" in summary
        assert "反方" in summary
