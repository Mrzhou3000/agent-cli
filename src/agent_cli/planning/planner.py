"""TaskPlanner — 任务规划与审批闭环。

设计依据（规范 4.6）：
  流程: 规划 → 展示 → 确认 → 执行 → 汇总
  审批闭环确保用户在任务执行前有机会审核和调整。
  任务图持久化为 JSON 文件，支持中断恢复。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_cli.planning.models import TaskPlan, TodoItem

logger = logging.getLogger(__name__)


class TaskPlanner:
    """任务规划器。

    管理任务计划的创建、审批、执行跟踪和持久化。
    支持依赖拓扑排序和审批闭环。

    Usage:
        planner = TaskPlanner()
        plan = planner.create_plan([
            {"id": "t1", "title": "搜索代码", "description": "搜索所有 TODO"},
            {"id": "t2", "title": "分析结果", "deps": ["t1"]},
        ])
        planner.show_plan(plan)
        planner.approve_plan(plan.plan_id)
        ready = planner.get_next_tasks(plan.plan_id)
    """

    def __init__(self, base_dir: str = ".agent"):
        self._plans_dir = Path(base_dir) / "plans"
        self._plans_dir.mkdir(parents=True, exist_ok=True)
        self._current_plan: TaskPlan | None = None

    # ── 创建 ────────────────────────────────────────────────────

    def create_plan(self, tasks: list[dict]) -> TaskPlan:
        """从任务描述列表创建计划。

        Args:
            tasks: 任务描述列表，每项包含 id、title、description、deps。

        Returns:
            创建的 TaskPlan 实例。
        """
        import random

        plan_id = f"plan_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{random.getrandbits(16):04x}"
        todos = [TodoItem(**t) for t in tasks]
        plan = TaskPlan(plan_id=plan_id, todos=todos)
        self._save(plan)
        self._current_plan = plan
        logger.info("创建计划: %s (%d 个任务)", plan_id, len(todos))
        return plan

    # ── 展示 ────────────────────────────────────────────────────

    def show_plan(self, plan: TaskPlan | None = None) -> str:
        """生成计划的文本展示。

        Args:
            plan: 计划实例。为 None 时使用当前计划。

        Returns:
            格式化的计划文本。
        """
        p = plan or self._current_plan
        if not p:
            return "暂无计划。"

        lines = [f"## 计划 {p.plan_id}", f"创建: {p.created_at}", ""]

        layers = p.topological_sort()
        for layer_idx, layer in enumerate(layers, 1):
            lines.append(f"### 第 {layer_idx} 层 (并行)")
            for todo_id in layer:
                todo = next(t for t in p.todos if t.id == todo_id)
                dep_info = f" [依赖: {', '.join(todo.deps)}]" if todo.deps else ""
                lines.append(f"  [{todo.status}] {todo.id}: {todo.title}{dep_info}")
                if todo.description:
                    lines.append(f"    {todo.description}")
            lines.append("")

        lines.append(p.summary)
        return "\n".join(lines)

    # ── 审批 ────────────────────────────────────────────────────

    def approve_plan(self, plan_id: str | None = None) -> bool:
        """审批通过计划，将所有 pending 任务标记为 approved。

        Args:
            plan_id: 计划 ID。为 None 时使用当前计划。

        Returns:
            操作成功返回 True。
        """
        plan = self._load(plan_id) if plan_id else self._current_plan
        if not plan:
            logger.warning("计划不存在: %s", plan_id)
            return False

        for todo in plan.todos:
            if todo.status == "pending":
                todo.status = "approved"

        self._save(plan)
        self._current_plan = plan
        logger.info("计划已审批: %s", plan.plan_id)
        return True

    # ── 执行 ────────────────────────────────────────────────────

    def get_next_tasks(self, plan_id: str | None = None) -> list[TodoItem]:
        """获取当前可执行的任务（已审批且依赖完成）。

        Args:
            plan_id: 计划 ID。为 None 时使用当前计划。

        Returns:
            可执行的任务列表。
        """
        plan = self._load(plan_id) if plan_id else self._current_plan
        if not plan:
            return []

        completed = {t.id for t in plan.todos if t.status == "completed"}
        return [t for t in plan.todos if t.status == "approved" and t.can_start(completed)]

    def start_task(self, todo_id: str, plan_id: str | None = None) -> bool:
        """将任务标记为执行中。

        Args:
            todo_id: 任务 ID。
            plan_id: 计划 ID。为 None 时使用当前计划。

        Returns:
            操作成功返回 True。
        """
        return self._update_status(todo_id, "in_progress", plan_id)

    def complete_task(self, todo_id: str, plan_id: str | None = None) -> bool:
        """将任务标记为已完成。

        Args:
            todo_id: 任务 ID。
            plan_id: 计划 ID。为 None 时使用当前计划。

        Returns:
            操作成功返回 True。
        """
        return self._update_status(todo_id, "completed", plan_id)

    def fail_task(self, todo_id: str, plan_id: str | None = None) -> bool:
        """将任务标记为失败。

        Args:
            todo_id: 任务 ID。
            plan_id: 计划 ID。为 None 时使用当前计划。

        Returns:
            操作成功返回 True。
        """
        return self._update_status(todo_id, "failed", plan_id)

    # ── 汇总 ────────────────────────────────────────────────────

    def summarize(self, plan_id: str | None = None) -> str:
        """生成计划的执行总结。

        Args:
            plan_id: 计划 ID。为 None 时使用当前计划。

        Returns:
            格式化的总结文本。
        """
        plan = self._load(plan_id) if plan_id else self._current_plan
        if not plan:
            return "暂无计划。"

        completed = [t for t in plan.todos if t.status == "completed"]
        failed = [t for t in plan.todos if t.status == "failed"]
        remaining = [t for t in plan.todos if t.status in ("pending", "approved", "in_progress")]

        lines = [
            f"## 执行总结 — {plan.plan_id}",
            plan.summary,
            "",
        ]

        if completed:
            lines.append(f"### 已完成 ({len(completed)})")
            for t in completed:
                lines.append(f"  [ok] {t.id}: {t.title}")

        if failed:
            lines.append(f"### 失败 ({len(failed)})")
            for t in failed:
                lines.append(f"  [x] {t.id}: {t.title}")

        if remaining:
            lines.append(f"### 剩余 ({len(remaining)})")
            for t in remaining:
                lines.append(f"  [-] {t.id}: {t.title} ({t.status})")

        return "\n".join(lines)

    # ── 持久化 ──────────────────────────────────────────────────

    def _save(self, plan: TaskPlan) -> None:
        """保存计划到文件。"""
        path = self._plans_dir / f"{plan.plan_id}.json"
        path.write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self, plan_id: str) -> TaskPlan | None:
        """从文件加载计划。"""
        path = self._plans_dir / f"{plan_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return TaskPlan.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            logger.error("加载计划失败 %s: %s", plan_id, e)
            return None

    def list_plans(self) -> list[dict[str, Any]]:
        """列出所有计划。"""
        plans = []
        for path in sorted(self._plans_dir.glob("plan_*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                plans.append(
                    {
                        "plan_id": data.get("plan_id", path.stem),
                        "created_at": data.get("created_at", ""),
                        "task_count": len(data.get("todos", [])),
                        "statuses": {t.get("status") for t in data.get("todos", [])},
                    }
                )
            except json.JSONDecodeError:
                continue
        return plans

    def _update_status(self, todo_id: str, status: str, plan_id: str | None = None) -> bool:
        """更新任务状态。

        Args:
            todo_id: 任务 ID。
            status: 新状态。
            plan_id: 计划 ID。

        Returns:
            操作成功返回 True。
        """
        plan = self._load(plan_id) if plan_id else self._current_plan
        if not plan:
            return False

        for todo in plan.todos:
            if todo.id == todo_id:
                todo.status = status
                self._save(plan)
                self._current_plan = plan
                logger.info("任务 %s → %s: %s", todo_id, status, todo.title)
                return True

        logger.warning("任务不存在: %s", todo_id)
        return False

    @property
    def current_plan(self) -> TaskPlan | None:
        """当前计划。"""
        return self._current_plan

    @current_plan.setter
    def current_plan(self, plan: TaskPlan | None) -> None:
        self._current_plan = plan
