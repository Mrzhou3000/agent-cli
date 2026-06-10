"""Coordinator — 多Agent协作编排器。

设计依据（规范 4.12）：
  Coordinator 模式：1 个协调器 + N 个 Worker
  通信方式：协调器分发任务 → Worker 执行 → 结果汇总
  支持四种编排模式：顺序、并行、投票、辩论

Usage:
    coord = Coordinator(subagent_manager)
    # 顺序执行
    results = coord.sequential(["任务1", "任务2", "任务3"])
    # 并行执行
    results = coord.parallel(["搜索A", "搜索B", "搜索C"])
    # 投票
    verdict = coord.vote("这个代码有bug吗?", voters=5)
    # 辩论
    synthesis = coord.debate("我们应该用微服务还是单体?", rounds=2)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agent_cli.core.provider import IModelProvider
from agent_cli.subagent.manager import SubagentManager, SubagentResult

logger = logging.getLogger(__name__)


# ─── 数据模型 ───────────────────────────────────────────────────


@dataclass
class CoordinatorResult:
    """多Agent协作结果。

    Attributes:
        pattern: 使用的编排模式 (sequential/parallel/vote/debate)。
        results: 所有 Worker 的结果列表。
        summary: 汇总输出文本。
        task: 原始任务描述。
        duration: 执行耗时（秒）。
    """

    pattern: str
    results: list[SubagentResult] = field(default_factory=list)
    summary: str = ""
    task: str = ""
    duration: float = 0.0

    @property
    def success_count(self) -> int:
        """成功 Worker 数。"""
        return sum(1 for r in self.results if r.success)

    @property
    def failure_count(self) -> int:
        """失败 Worker 数。"""
        return sum(1 for r in self.results if not r.success)


@dataclass
class VoteResult:
    """投票结果。

    Attributes:
        question: 投票问题。
        votes: 每个投票者的结果。
        agreement: 赞成票数。
        disagreement: 反对票数。
        consensus: 是否达成共识。
    """

    question: str
    votes: list[dict[str, Any]] = field(default_factory=list)
    agreement: int = 0
    disagreement: int = 0

    @property
    def consensus(self) -> bool:
        """是否达成共识（>60% 一致）。"""
        total = self.agreement + self.disagreement
        if total == 0:
            return False
        return max(self.agreement, self.disagreement) / total >= 0.6


# ─── Coordinator ───────────────────────────────────────────────


class Coordinator:
    """多Agent协作编排器。

    基于 SubagentManager 实现四种编排模式。
    每个 Worker 拥有独立上下文，共享父 Agent 工具集。

    Usage:
        coord = Coordinator(sub_mgr)
        results = coord.sequential(["step1", "step2", "step3"])
        for r in results:
            print(r.output)
    """

    def __init__(
        self,
        subagent_manager: SubagentManager,
        max_workers: int = 5,
        provider: IModelProvider | None = None,
    ):
        self._manager = subagent_manager
        self._max_workers = max_workers
        self._provider = provider

    # ── 顺序模式 ─────────────────────────────────────────────

    def sequential(
        self,
        tasks: list[str],
        context: dict | None = None,
        pass_down: bool = True,
    ) -> CoordinatorResult:
        """顺序执行模式：任务依次执行，前一个结果可传入下一个。

        Args:
            tasks: 任务描述列表。
            context: 共享上下文。
            pass_down: 是否将前一个 Worker 的输出传递给下一个。

        Returns:
            CoordinatorResult 实例。
        """
        import time

        logger.info("Coordinator sequential: %d 个任务", len(tasks))
        start = time.time()
        results: list[SubagentResult] = []
        accumulated_context = dict(context or {})

        for i, task in enumerate(tasks, 1):
            logger.info("顺序任务 [%d/%d]: %s", i, len(tasks), task[:80])

            # 传递前一个结果
            worker_context = dict(accumulated_context)
            if pass_down and results:
                last = results[-1]
                if last.success:
                    worker_context["前一步输出"] = last.output[:2000]

            result = self._manager.spawn(
                task,
                context=worker_context,
                provider=self._provider,
            )
            results.append(result)

            # 更新累积上下文
            if result.success and pass_down:
                accumulated_context[f"步骤{i}_结果"] = result.output[:500]

        duration = time.time() - start
        summary = self._summarize_sequential(results, tasks)

        return CoordinatorResult(
            pattern="sequential",
            results=results,
            summary=summary,
            task=" → ".join(tasks),
            duration=duration,
        )

    # ── 并行模式 ─────────────────────────────────────────────

    def parallel(
        self,
        tasks: list[str],
        context: dict | None = None,
    ) -> CoordinatorResult:
        """并行执行模式：所有任务同时执行。

        Args:
            tasks: 任务描述列表。
            context: 共享上下文。

        Returns:
            CoordinatorResult 实例。
        """
        import threading
        import time

        logger.info("Coordinator parallel: %d 个任务", len(tasks))
        start = time.time()

        results: list[SubagentResult | None] = [None] * len(tasks)
        errors: list[str] = []

        def _run_task(index: int, task: str) -> None:
            """线程内执行单个任务。"""
            try:
                results[index] = self._manager.spawn(
                    task,
                    context=context,
                    provider=self._provider,
                )
            except Exception as e:
                errors.append(f"任务 '{task[:50]}' 失败: {e}")
                results[index] = SubagentResult(
                    task=task,
                    error=str(e),
                )

        threads = []
        for i, task in enumerate(tasks):
            t = threading.Thread(target=_run_task, args=(i, task), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=300)  # 5 分钟超时

        valid_results = [r for r in results if r is not None]
        duration = time.time() - start
        summary = self._summarize_parallel(valid_results, tasks, errors)

        return CoordinatorResult(
            pattern="parallel",
            results=valid_results,
            summary=summary,
            task=" || ".join(tasks),
            duration=duration,
        )

    # ── 投票模式 ─────────────────────────────────────────────

    def vote(
        self,
        question: str,
        voters: int = 3,
        context: dict | None = None,
    ) -> VoteResult:
        """投票模式：多个 Worker 独立回答同一问题，汇总投票结果。

        Args:
            question: 需要投票的问题。
            voters: 投票者数量。
            context: 共享上下文。

        Returns:
            VoteResult 实例。
        """
        logger.info("Coordinator vote: '%s' (%d 位投票者)", question[:60], voters)

        # 为每个投票者创建独立任务
        task_template = "请回答以下问题，只输出「同意」或「反对」及简要理由：\n"
        tasks = [f"{task_template}{question}" for _ in range(voters)]

        coord_result = self.parallel(tasks, context=context)
        vote_result = VoteResult(question=question)

        for r in coord_result.results:
            output = r.output.lower()
            is_agree = any(kw in output for kw in ["同意", "赞成", "是", "yes", "agree", "支持"])
            is_disagree = any(
                kw in output for kw in ["反对", "不同意", "否", "no", "disagree", "拒绝"]
            )

            vote_record = {
                "agent_output": r.output[:300],
                "agrees": is_agree or (not is_disagree and is_agree),
                "disagrees": is_disagree and not is_agree,
                "success": r.success,
            }
            vote_result.votes.append(vote_record)

            if vote_record["agrees"]:
                vote_result.agreement += 1
            elif vote_record["disagrees"]:
                vote_result.disagreement += 1

        logger.info(
            "投票结果: %d 同意 / %d 反对 (共识: %s)",
            vote_result.agreement,
            vote_result.disagreement,
            vote_result.consensus,
        )

        return vote_result

    # ── 辩论模式 ─────────────────────────────────────────────

    def debate(
        self,
        question: str,
        rounds: int = 2,
        context: dict | None = None,
    ) -> CoordinatorResult:
        """辩论模式：正反双方多轮辩论后汇总。

        Args:
            question: 辩论主题。
            rounds: 辩论轮数。
            context: 共享上下文。

        Returns:
            CoordinatorResult 实例。
        """
        import time

        logger.info("Coordinator debate: '%s' (%d 轮)", question[:60], rounds)
        start = time.time()
        results: list[SubagentResult] = []

        pro_context = dict(context or {})
        con_context = dict(context or {})
        pro_context["立场"] = "支持"
        con_context["立场"] = "反对"

        for round_num in range(1, rounds + 1):
            logger.info("辩论第 %d 轮", round_num)

            # 正方发言
            pro_task = f"【第{round_num}轮】请从支持的角度论证：{question}"
            if round_num > 1 and results:
                con_last = results[-1] if len(results) >= 2 else None
                if con_last and con_last.success:
                    pro_context["对方论点"] = con_last.output[:1000]

            pro_result = self._manager.spawn(
                pro_task,
                context=pro_context,
                provider=self._provider,
            )
            results.append(pro_result)

            # 反方发言
            con_task = f"【第{round_num}轮】请从反对的角度论证：{question}"
            con_context["对方论点"] = pro_result.output[:1000]

            con_result = self._manager.spawn(
                con_task,
                context=con_context,
                provider=self._provider,
            )
            results.append(con_result)

        # 汇总辩论
        summary = self._synthesize_debate(question, results)
        duration = time.time() - start

        return CoordinatorResult(
            pattern="debate",
            results=results,
            summary=summary,
            task=question,
            duration=duration,
        )

    # ── 私有辅助方法 ─────────────────────────────────────────

    def _summarize_sequential(self, results: list[SubagentResult], tasks: list[str]) -> str:
        """生成顺序执行摘要。"""
        parts: list[str] = [f"## 顺序执行摘要 ({len(results)} 个步骤)\n"]

        for i, (task, result) in enumerate(zip(tasks, results, strict=False), 1):
            status = "✅" if result.success else "❌"
            parts.append(f"### 步骤 {i}: {task} {status}")
            if result.success:
                parts.append(f"{result.output[:300]}")
            else:
                parts.append(f"错误: {result.error}")
            parts.append("")

        success = sum(1 for r in results if r.success)
        parts.append(f"---\n**完成: {success}/{len(results)}**")
        return "\n".join(parts)

    def _summarize_parallel(
        self,
        results: list[SubagentResult],
        tasks: list[str],
        errors: list[str],
    ) -> str:
        """生成并行执行摘要。"""
        parts: list[str] = [f"## 并行执行摘要 ({len(results)} 个任务)\n"]

        for result in results:
            status = "✅" if result.success else "❌"
            parts.append(f"### {result.task[:60]} {status}")
            if result.success:
                parts.append(f"{result.output[:200]}")
            else:
                parts.append(f"错误: {result.error}")
            parts.append("")

        if errors:
            parts.append("### 异常")
            for err in errors:
                parts.append(f"- {err}")

        success = sum(1 for r in results if r.success)
        parts.append(f"---\n**完成: {success}/{len(results)}**")
        return "\n".join(parts)

    def _synthesize_debate(self, question: str, results: list[SubagentResult]) -> str:
        """综合正反双方论点，生成辩论总结。

        Args:
            question: 辩论主题。
            results: 所有辩论发言（交替的正反方）。

        Returns:
            辩论总结文本。
        """
        parts: list[str] = [
            "## 辩论总结\n",
            f"**主题**: {question}\n",
        ]

        pro_points: list[str] = []
        con_points: list[str] = []

        for i, result in enumerate(results):
            if not result.success:
                continue
            label = "正方" if i % 2 == 0 else "反方"
            points = pro_points if i % 2 == 0 else con_points
            output = result.output[:500]
            points.append(f"### 第{i // 2 + 1}轮 {label}\n{output}\n")

        if pro_points:
            parts.append("### 正方论点\n")
            parts.extend(pro_points)

        if con_points:
            parts.append("### 反方论点\n")
            parts.extend(con_points)

        # 综合
        parts.append("### 综合\n")
        parts.append(f"双方共进行了 {len(results) // 2} 轮辩论。请根据以上论点做出判断。")

        return "\n".join(parts)
