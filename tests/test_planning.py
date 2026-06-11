"""Tests for Phase 3 — Task Planning."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_cli.planning.models import TaskPlan, TodoItem
from agent_cli.planning.planner import TaskPlanner


class TestTodoItem:
    """TodoItem 数据模型测试。"""

    def test_can_start_no_deps(self):
        """无依赖的任务应始终可开始。"""
        t = TodoItem(id="t1", title="Test")
        assert t.can_start(set()) is True
        assert t.can_start({"any_id"}) is True

    def test_can_start_with_deps(self):
        """依赖完成时可开始。"""
        t = TodoItem(id="t2", title="Test", deps=["t1"])
        assert t.can_start(set()) is False
        assert t.can_start({"t1"}) is True

    def test_can_start_multiple_deps(self):
        """所有依赖都完成才可开始。"""
        t = TodoItem(id="t3", title="Test", deps=["t1", "t2"])
        assert t.can_start({"t1"}) is False
        assert t.can_start({"t1", "t2"}) is True


class TestTaskPlan:
    """TaskPlan 数据模型测试。"""

    def test_topological_sort_simple(self):
        """简单线性依赖应正确排序。"""
        plan = TaskPlan(
            plan_id="test1",
            todos=[
                TodoItem(id="t1", title="Task 1"),
                TodoItem(id="t2", title="Task 2", deps=["t1"]),
                TodoItem(id="t3", title="Task 3", deps=["t2"]),
            ],
        )
        layers = plan.topological_sort()
        assert len(layers) == 3
        assert layers[0] == ["t1"]
        assert layers[1] == ["t2"]
        assert layers[2] == ["t3"]

    def test_topological_sort_parallel(self):
        """无依赖的任务应在同一层并行。"""
        plan = TaskPlan(
            plan_id="test2",
            todos=[
                TodoItem(id="t1", title="Task 1"),
                TodoItem(id="t2", title="Task 2"),
                TodoItem(id="t3", title="Task 3"),
            ],
        )
        layers = plan.topological_sort()
        assert len(layers) == 1
        assert set(layers[0]) == {"t1", "t2", "t3"}

    def test_topological_sort_mixed(self):
        """混合依赖应正确分层。"""
        plan = TaskPlan(
            plan_id="test3",
            todos=[
                TodoItem(id="t1", title="Task 1"),
                TodoItem(id="t2", title="Task 2"),
                TodoItem(id="t3", title="Task 3", deps=["t1"]),
                TodoItem(id="t4", title="Task 4", deps=["t2"]),
                TodoItem(id="t5", title="Task 5", deps=["t3", "t4"]),
            ],
        )
        layers = plan.topological_sort()
        assert len(layers) == 3
        assert set(layers[0]) == {"t1", "t2"}
        assert set(layers[1]) == {"t3", "t4"}
        assert layers[2] == ["t5"]

    def test_summary_counts(self):
        """summary 应正确统计各状态数量。"""
        plan = TaskPlan(
            plan_id="test4",
            todos=[
                TodoItem(id="t1", title="A", status="completed"),
                TodoItem(id="t2", title="B", status="failed"),
                TodoItem(id="t3", title="C", status="in_progress"),
                TodoItem(id="t4", title="D", status="pending"),
            ],
        )
        summary = plan.summary
        assert "test4" in summary
        assert "4 个任务" in summary
        assert "1 完成" in summary
        assert "1 失败" in summary
        assert "1 进行中" in summary

    def test_to_dict_roundtrip(self):
        """序列化和反序列化应一致。"""
        original = TaskPlan(
            plan_id="test5",
            created_at="2026-06-10 12:00 UTC",
            todos=[
                TodoItem(id="t1", title="Task 1", description="Desc 1", status="pending"),
                TodoItem(id="t2", title="Task 2", deps=["t1"], status="approved"),
            ],
        )
        data = original.to_dict()
        restored = TaskPlan.from_dict(data)
        assert restored.plan_id == original.plan_id
        assert len(restored.todos) == len(original.todos)
        assert restored.todos[0].id == "t1"
        assert restored.todos[1].deps == ["t1"]


class TestTaskPlanner:
    """TaskPlanner 功能测试。"""

    @pytest.fixture
    def planner(self, tmp_path: Path) -> TaskPlanner:
        """临时目录的 TaskPlanner fixture。"""
        return TaskPlanner(base_dir=str(tmp_path / ".agent"))

    def test_create_plan(self, planner: TaskPlanner):
        """创建计划应生成 plan_id 并持久化。"""
        plan = planner.create_plan(
            [
                {"id": "t1", "title": "First task"},
                {"id": "t2", "title": "Second task", "deps": ["t1"]},
            ]
        )
        assert plan.plan_id.startswith("plan_")
        assert len(plan.todos) == 2
        assert plan.todos[0].title == "First task"
        assert plan.todos[1].deps == ["t1"]

    def test_show_plan(self, planner: TaskPlanner):
        """展示计划应返回格式化的文本。"""
        planner.create_plan(
            [
                {"id": "t1", "title": "Task 1"},
            ]
        )
        text = planner.show_plan()
        assert "Task 1" in text
        assert "plan_" in text

    def test_approve_plan(self, planner: TaskPlanner):
        """审批通过应将所有 pending 任务标记为 approved。"""
        planner.create_plan(
            [
                {"id": "t1", "title": "A"},
                {"id": "t2", "title": "B"},
            ]
        )
        assert planner.approve_plan() is True
        assert planner.current_plan is not None
        for todo in planner.current_plan.todos:
            assert todo.status == "approved"

    def test_get_next_tasks(self, planner: TaskPlanner):
        """只有已审批且依赖完成的任务才可执行。"""
        planner.create_plan(
            [
                {"id": "t1", "title": "A"},
                {"id": "t2", "title": "B", "deps": ["t1"]},
            ]
        )
        # 未审批，无可执行任务
        assert planner.get_next_tasks() == []

        # 审批后 t1 可执行
        planner.approve_plan()
        next_tasks = planner.get_next_tasks()
        assert len(next_tasks) == 1
        assert next_tasks[0].id == "t1"

    def test_task_lifecycle(self, planner: TaskPlanner):
        """任务完整生命周期: pending → approved → in_progress → completed。"""
        planner.create_plan([{"id": "t1", "title": "Lifecycle test"}])
        planner.approve_plan()

        assert planner.start_task("t1") is True
        assert planner.current_plan is not None
        assert planner.current_plan.todos[0].status == "in_progress"

        assert planner.complete_task("t1") is True
        assert planner.current_plan.todos[0].status == "completed"

    def test_fail_task(self, planner: TaskPlanner):
        """任务失败状态更新。"""
        planner.create_plan([{"id": "t1", "title": "Fail test"}])
        planner.approve_plan()
        planner.start_task("t1")
        assert planner.fail_task("t1") is True
        assert planner.current_plan is not None
        assert planner.current_plan.todos[0].status == "failed"

    def test_summarize(self, planner: TaskPlanner):
        """执行总结应汇总各状态数据。"""
        planner.create_plan(
            [
                {"id": "t1", "title": "Done"},
                {"id": "t2", "title": "Failed"},
            ]
        )
        planner.approve_plan()
        planner.start_task("t1")
        planner.complete_task("t1")
        planner.start_task("t2")
        planner.fail_task("t2")

        summary = planner.summarize()
        assert "Done" in summary
        assert "Failed" in summary
        assert "已完成" in summary or "失败" in summary

    def test_list_plans(self, planner: TaskPlanner):
        """list_plans 应返回所有计划。"""
        import time

        planner.create_plan([{"id": "t1", "title": "A"}])
        time.sleep(0.01)  # 确保不同时间戳
        planner.create_plan([{"id": "t2", "title": "B"}])
        plans = planner.list_plans()
        assert len(plans) == 2

    def test_persistence(self, tmp_path: Path):
        """计划应持久化到文件并能重新加载。"""
        base = tmp_path / ".agent"
        planner1 = TaskPlanner(base_dir=str(base))
        planner1.create_plan([{"id": "t1", "title": "Persist test"}])
        planner1.approve_plan()
        planner1.start_task("t1")
        plan_id = planner1.current_plan.plan_id

        # 新实例加载
        planner2 = TaskPlanner(base_dir=str(base))
        loaded = planner2._load(plan_id)
        assert loaded is not None
        assert loaded.todos[0].status == "in_progress"
