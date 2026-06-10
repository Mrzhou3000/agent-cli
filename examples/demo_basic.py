"""
Agent-CLI 基础使用演示脚本。

运行方式:
    uv run python examples/demo_basic.py
"""

from agent_cli.core.loop import AgentLoop
from agent_cli.core.provider import MockProvider
from agent_cli.tools.registry import ToolRegistry
from agent_cli.tools.bash import BashTool
from agent_cli.tools.file import GlobTool, GrepTool, ReadTool, WriteTool
from agent_cli.tools.web import WebFetchTool
from agent_cli.tools.agent_tool import AgentTool


def main():
    """演示 Agent-CLI 的基本使用流程。"""
    print("=" * 60)
    print("Agent-CLI 演示脚本")
    print("=" * 60)

    # 1. 初始化组件
    registry = ToolRegistry()
    registry.register(BashTool())
    registry.register(ReadTool())
    registry.register(WriteTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    registry.register(WebFetchTool())
    registry.register(AgentTool())

    provider = MockProvider(default_response="你好！我是 Agent-CLI 演示助手。")

    loop = AgentLoop(
        provider=provider,
        tools=registry,
        max_iterations=3,
    )

    # 2. 运行简单的对话
    print("\n📝 运行示例 1: 简单问候")
    result = loop.run("你好")
    print(f"  Agent: {result.text}")

    # 3. 再次运行（模拟多轮）
    print("\n📝 运行示例 2: 请求帮助")
    result = loop.run("你能做什么？")
    print(f"  Agent: {result.text}")

    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)
    print(f"\nProvider 调用次数: {provider.call_count}")


if __name__ == "__main__":
    main()
