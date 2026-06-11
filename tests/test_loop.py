"""Agent Loop 单元测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from agent_cli.core.loop import AgentLoop
from agent_cli.core.provider import MockProvider, Response, ToolCall
from agent_cli.hooks.manager import POST_LOOP, PRE_LOOP, HookManager
from agent_cli.memory.manager import MemoryManager
from agent_cli.session.store import SessionStore
from agent_cli.tools.bash import BashTool
from agent_cli.tools.registry import ToolRegistry


@pytest.fixture
def registry() -> ToolRegistry:
    r = ToolRegistry()
    r.register(BashTool())
    return r


class TestAgentLoop:
    """Agent Loop 核心功能测试。"""

    def test_text_response(self, mock_provider: MockProvider, registry: ToolRegistry):
        """测试纯文本回复场景。"""
        loop = AgentLoop(provider=mock_provider, tools=registry)
        response = loop.run("你好")
        assert response.stop_reason == "end_turn"
        assert len(response.text) > 0
        assert loop._iteration == 1

    def test_tool_call_then_text(self, mock_provider: MockProvider, registry: ToolRegistry):
        """测试工具调用后文本回复场景。"""
        loop = AgentLoop(provider=mock_provider, tools=registry, max_iterations=5)
        response = loop.run("请搜索项目中的TODO")
        assert response.stop_reason == "end_turn"
        assert loop._iteration >= 1

    def test_max_iterations(self, registry: ToolRegistry):
        """测试最大迭代次数限制。"""

        # 使用自定义 provider 总是返回 tool_use
        class AlwaysToolProvider(MockProvider):
            def __init__(self):
                super().__init__()
                self._count = 0

            def invoke(self, messages, tools=None):
                self._count += 1
                from agent_cli.core.provider import Response, ToolCall

                return Response(
                    stop_reason="tool_use",
                    content=[
                        {
                            "type": "tool_use",
                            "id": "tu_0",
                            "name": "bash",
                            "input": {"command": "echo hi"},
                        }
                    ],
                    tool_calls=[ToolCall(id="tu_0", name="bash", input={"command": "echo hi"})],
                )

        loop = AgentLoop(provider=AlwaysToolProvider(), tools=registry, max_iterations=3)
        response = loop.run("loop forever")
        assert loop._iteration == 3  # 达到上限
        assert response.stop_reason == "max_tokens"

    def test_hooks_integration(self, mock_provider: MockProvider, registry: ToolRegistry):
        """测试 Hook 系统集成。"""
        hook_calls = []
        hooks = HookManager()
        hooks.on(PRE_LOOP, lambda msgs: hook_calls.append("pre_loop"))
        hooks.on(POST_LOOP, lambda resp: hook_calls.append("post_loop"))

        loop = AgentLoop(provider=mock_provider, tools=registry, hooks=hooks)
        loop.run("测试 Hook 集成")

        assert "pre_loop" in hook_calls
        assert "post_loop" in hook_calls

    def test_messages_passthrough(self, mock_provider: MockProvider, registry: ToolRegistry):
        """测试外部传入消息列表。"""
        loop = AgentLoop(provider=mock_provider, tools=registry)
        response = loop.run(prompt="", messages=[{"role": "user", "content": "直接传入"}])
        assert response.stop_reason == "end_turn"

    def test_unknown_tool_keyerror(self, registry: ToolRegistry):
        """调用不存在的工具时返回错误信息而非崩溃。"""

        class UnknownToolProvider(MockProvider):
            def invoke(self, messages, tools=None):
                return Response(
                    stop_reason="tool_use",
                    content=[
                        {"type": "tool_use", "id": "tu_bad", "name": "ghost_tool", "input": {}}
                    ],
                    tool_calls=[ToolCall(id="tu_bad", name="ghost_tool", input={})],
                )

        loop = AgentLoop(provider=UnknownToolProvider(), tools=registry, max_iterations=3)
        response = loop.run("use ghost tool")
        # 循环应正常结束，不崩溃
        assert response.stop_reason in ("end_turn", "max_tokens")

    def test_memory_context_injection(self, mock_provider: MockProvider, registry: ToolRegistry):
        """MemoryManager 注入记忆上下文到系统消息。"""
        with tempfile.TemporaryDirectory() as td:
            mem = MemoryManager(base_dir=str(Path(td) / ".agent"))
            mem.write_note("test-mem", "Remember user likes Python", tags=["python"])
            loop = AgentLoop(provider=mock_provider, tools=registry, memory=mem)
            response = loop.run("Python related question")
            assert response.stop_reason == "end_turn"

    def test_session_persistence(self, mock_provider: MockProvider, registry: ToolRegistry):
        """SessionStore 持久化消息。"""
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(base_dir=str(Path(td) / ".agent"))
            loop = AgentLoop(provider=mock_provider, tools=registry, session_store=store)
            sid = store.create()
            response = loop.run("test", session_id=sid)
            assert response.stop_reason == "end_turn"
            # verify messages were persisted
            loaded = store.load(sid)
            assert len(loaded) >= 1
