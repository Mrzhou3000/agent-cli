"""Task Planning 数据模型。

设计依据（规范 4.6）：
  - TodoItem: id + title + status + deps
  - 状态机：pending → approved → in_progress → completed/failed
  - 支持拓扑排序依赖解析
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class TodoItem:
    """单个任务项。

    Attributes:
        id: 唯一标识符。
        title: 任务标题。
        description: 任务详细描述。
        status: 状态（pending/approved/in_progress/completed/failed）。
        deps: 依赖的任务 ID 列表。
    """

    id: str
    title: str
    description: str = ""
    status: str = "pending"
    deps: list[str] = field(default_factory=list)

    def can_start(self, completed_ids: set[str]) -> bool:
        """检查是否所有依赖已完成。

        Args:
            completed_ids: 已完成的任务 ID 集合。

        Returns:
            依赖全部完成返回 True。
        """
        return all(dep in completed_ids for dep in self.deps)


@dataclass
class TaskPlan:
    """完整的任务计划。

    Attributes:
        plan_id: 计划标识符。
        created_at: 创建时间。
        todos: 任务列表。
    """

    plan_id: str
    created_at: str = ""
    todos: list[TodoItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    def topological_sort(self) -> list[list[str]]:
        """拓扑排序，返回并行执行层。

        Returns:
            按层分组的任务 ID 列表。同一层可并行执行。
        """
        completed: set[str] = set()
        remaining = {t.id for t in self.todos}
        layers: list[list[str]] = []

        while remaining:
            current_layer = []
            for todo_id in remaining:
                todo = self._get(todo_id)
                if todo and todo.can_start(completed):
                    current_layer.append(todo_id)

            if not current_layer:
                # 有环依赖或无法进展
                current_layer = list(remaining)
                break

            for tid in current_layer:
                remaining.discard(tid)
                completed.add(tid)

            layers.append(current_layer)

        return layers

    def _get(self, todo_id: str) -> TodoItem | None:
        """按 ID 查找任务。"""
        for t in self.todos:
            if t.id == todo_id:
                return t
        return None

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "todos": [
                {
                    "id": t.id,
                    "title": t.title,
                    "description": t.description,
                    "status": t.status,
                    "deps": t.deps,
                }
                for t in self.todos
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> TaskPlan:
        """从字典反序列化。"""
        return cls(
            plan_id=data["plan_id"],
            created_at=data.get("created_at", ""),
            todos=[TodoItem(**t) for t in data.get("todos", [])],
        )

    @property
    def summary(self) -> str:
        """生成计划摘要。"""
        total = len(self.todos)
        counts = {"completed": 0, "failed": 0, "in_progress": 0, "pending": 0, "approved": 0}
        for t in self.todos:
            if t.status in counts:
                counts[t.status] += 1
        return (
            f"计划 {self.plan_id}: {total} 个任务"
            f" ({counts['completed']} 完成"
            f"/ {counts['in_progress']} 进行中"
            f"/ {counts['failed']} 失败"
            f"/ {counts['pending']} 待审批)"
        )
