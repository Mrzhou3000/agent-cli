"""Executor 单元测试。

目标模块: src/agent_cli/core/executor.py
当前覆盖率: 0% → 目标 100%

Executor 在 Agent Loop 和 ToolRegistry 之间提供：
1. 权限检查
2. 执行调度
3. 异常处理
"""

from __future__ import annotations

import pytest

from agent_cli.core.executor import Executor
from agent_cli.permissions.engine import PermissionEngine
from agent_cli.tools.base import BaseTool, SafetyLevel, ToolSpec
from agent_cli.tools.registry import ToolRegistry


class TestExecutor:
    """Executor 单元测试。"""

    @pytest.fixture
    def registry(self):
        """预置含一个工具的 ToolRegistry。"""
        r = ToolRegistry()

        class EchoTool(BaseTool):
            def spec(self) -> ToolSpec:
                return ToolSpec(
                    name="echo",
                    description="回显",
                    parameters={"type": "object", "properties": {"msg": {"type": "string"}}, "required": ["msg"]},
                    handler=self.execute,
                    safety=SafetyLevel.SAFE,
                )

            def execute(self, msg: str = "", **kwargs) -> dict:
                return {"stdout": msg}

        r.register(EchoTool())
        return r

    @pytest.fixture
    def permission_engine(self):
        """PermissionEngine fixture。"""
        return PermissionEngine()

    @pytest.fixture
    def executor(self, registry, permission_engine):
        """Executor fixture。"""
        return Executor(registry=registry, permissions=permission_engine)

    def test_execute_success(self, executor):
        """正常执行应返回 success=True 和工具结果。"""
        result = executor.execute("echo", msg="hello")
        assert result["success"] is True
        assert result["stdout"] == "hello"

    def test_execute_tool_not_found(self, executor):
        """不存在的工具应返回 success=False。"""
        result = executor.execute("nonexistent")
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_execute_permission_denied(self, executor, permission_engine):
        """权限拒绝时应返回 success=False。"""
        # 将 echo 设为 deny
        permission_engine.set_rule("echo", "deny")
        result = executor.execute("echo", msg="hello")
        assert result["success"] is False
        assert "权限拒绝" in result["error"]

    def test_execute_tool_exception(self, executor, registry):
        """工具执行抛出异常时应返回 success=False。"""
        # 注入一个会抛异常的工具
        class BrokenTool(BaseTool):
            def spec(self) -> ToolSpec:
                return ToolSpec(
                    name="broken",
                    description="坏掉的工具",
                    parameters={},
                    handler=self.execute,
                    safety=SafetyLevel.SAFE,
                )

            def execute(self, **kwargs) -> dict:
                raise RuntimeError("内部错误")

        registry.register(BrokenTool())
        result = executor.execute("broken")
        assert result["success"] is False
        assert "内部错误" in result["error"]

    def test_execute_result_not_dict(self, executor, registry):
        """工具返回非 dict 时应自动包装为 dict。"""
        class StrTool(BaseTool):
            def spec(self) -> ToolSpec:
                return ToolSpec(
                    name="str_tool",
                    description="返回字符串",
                    parameters={},
                    handler=self.execute,
                    safety=SafetyLevel.SAFE,
                )

            def execute(self, **kwargs):
                return "直接返回字符串"

        registry.register(StrTool())
        result = executor.execute("str_tool")
        assert result["success"] is True
        assert result["result"] == "直接返回字符串"

    def test_registry_get_returns_none(self, executor, registry):
        """registry.get 返回 None 时应正确报错。"""
        # 手动覆盖 get 方法
        original_get = registry.get
        registry.get = lambda name: None
        result = executor.execute("echo")
        assert result["success"] is False
        assert "不存在" in result["error"]
        registry.get = original_get  # 恢复
