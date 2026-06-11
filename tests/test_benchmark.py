"""性能基准测试 — 衡量核心操作的性能指标。

测试内容：
  1. Provider 调用延迟（MockProvider — 纯内存操作基准）
  2. CompactPipeline 压缩速度
  3. ToolRegistry 注册与查找
  4. 记忆系统写入/读取
  5. Agent Loop 轻量迭代

这些测试使用 time.perf_counter() 进行精确计时，
输出基准数据（均值、最小值、最大值）便于追踪性能变化。
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from agent_cli.compact.pipeline import CompactPipeline
from agent_cli.core.provider import MockProvider
from agent_cli.memory.file_memory import FileMemory
from agent_cli.tools.bash import BashTool
from agent_cli.tools.registry import ToolRegistry

# ─── 基准测试阈值常量（秒） ────────────────────────────────────────
# 这些是经验值，在 CI/本地机器上应当远低于阈值。
# 如果持续超阈值，说明有性能退化。

BENCHMARK_THRESHOLDS = {
    "provider_invoke": 0.5,  # MockProvider.invoke() < 500ms
    "compact_pipeline": 1.0,  # CompactPipeline 压缩 < 1s
    "tool_registry": 0.1,  # 100 次注册/查找 < 100ms
    "memory_io": 0.5,  # 记忆写入/读取 < 500ms
    "loop_iteration": 1.0,  # Agent Loop 单次迭代 < 1s
}


def _time_it(fn, *args, warmup: int = 1, repeat: int = 5, label: str = "", **kwargs) -> dict:
    """运行函数多次并返回统计信息。

    Args:
        fn: 要测量的函数。
        *args: 传给 fn 的位置参数。
        warmup: 预热次数（不计入统计）。
        repeat: 正式测量次数。
        label: 标识标签。
        **kwargs: 传给 fn 的关键字参数。

    Returns:
        {"mean": 均值, "min": 最小值, "max": 最大值, "total": 总耗时, "n": 次数}.
    """
    # 预热
    for _ in range(warmup):
        fn(*args, **kwargs)

    timings: list[float] = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn(*args, **kwargs)
        end = time.perf_counter()
        timings.append(end - start)

    stats = {
        "mean": sum(timings) / len(timings),
        "min": min(timings),
        "max": max(timings),
        "total": sum(timings),
        "n": len(timings),
    }
    print(
        f"  [{label}] 均值={stats['mean'] * 1000:.1f}ms "
        f"min={stats['min'] * 1000:.1f}ms max={stats['max'] * 1000:.1f}ms "
        f"({stats['n']}次)"
    )
    return stats


# ─── Provider 基准测试 ─────────────────────────────────────────────


class TestProviderBenchmark:
    """Provider 调用性能基准。"""

    @pytest.fixture
    def provider(self) -> MockProvider:
        return MockProvider()

    def test_provider_invoke_latency(self, provider: MockProvider):
        """MockProvider.invoke() 纯内存操作延迟。"""
        messages = [{"role": "user", "content": "你好，请介绍 Python 的特点"}]
        stats = _time_it(provider.invoke, messages, warmup=3, repeat=10, label="provider.invoke")
        assert stats["mean"] < BENCHMARK_THRESHOLDS["provider_invoke"], (
            f"Provider 调用延迟过高: {stats['mean'] * 1000:.1f}ms > "
            f"{BENCHMARK_THRESHOLDS['provider_invoke'] * 1000:.0f}ms"
        )

    def test_provider_with_tools(self, provider: MockProvider):
        """带工具定义的 Provider 调用。"""
        messages = [{"role": "user", "content": "请搜索文件中的 TODO"}]
        tools = [
            {
                "name": "bash",
                "description": "Run a shell command",
                "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}},
            }
        ]
        stats = _time_it(
            provider.invoke,
            messages,
            tools,
            warmup=3,
            repeat=10,
            label="provider.invoke(tools)",
        )
        assert stats["mean"] < BENCHMARK_THRESHOLDS["provider_invoke"]


# ─── CompactPipeline 基准测试 ──────────────────────────────────────


class TestCompactBenchmark:
    """上下文压缩性能基准。"""

    @pytest.fixture
    def compact(self) -> CompactPipeline:
        return CompactPipeline(max_tokens=100000, provider=MockProvider())

    def test_compact_short_history(self, compact: CompactPipeline):
        """短历史（5条消息）压缩速度。"""
        messages = [
            {"role": "user", "content": f"第{i}条消息" if i % 2 == 0 else f"回复{i}"}
            for i in range(5)
        ]
        stats = _time_it(compact.compress, messages, warmup=2, repeat=10, label="compact(5msgs)")
        assert stats["mean"] < BENCHMARK_THRESHOLDS["compact_pipeline"]

    def test_compact_medium_history(self, compact: CompactPipeline):
        """中等历史（20条消息）压缩速度。"""
        messages = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"消息内容_{i} " * 10}
            for i in range(20)
        ]
        stats = _time_it(compact.compress, messages, warmup=2, repeat=5, label="compact(20msgs)")
        assert stats["mean"] < BENCHMARK_THRESHOLDS["compact_pipeline"]

    def test_compact_long_history(self, compact: CompactPipeline):
        """长历史（50条消息）压缩速度。"""
        messages = [
            {
                "role": "user" if i % 2 == 0 else "assistant",
                "content": (
                    f"这是一个相对较长的消息内容_{i}，用于测试压缩管道在大批量消息下的性能表现。 "
                    * 5
                ),
            }
            for i in range(50)
        ]
        stats = _time_it(compact.compress, messages, warmup=1, repeat=3, label="compact(50msgs)")
        assert stats["mean"] < BENCHMARK_THRESHOLDS["compact_pipeline"] * 3


# ─── ToolRegistry 基准测试 ─────────────────────────────────────────


class TestToolRegistryBenchmark:
    """工具注册与查找性能基准。"""

    def test_registry_bulk_register(self):
        """批量注册工具。"""
        registry = ToolRegistry()

        def _register_tools():
            for _ in range(100):
                registry.register(BashTool(allowed_dir=None))

        stats = _time_it(_register_tools, warmup=1, repeat=5, label="registry(100reg)")
        assert stats["mean"] < BENCHMARK_THRESHOLDS["tool_registry"]

    def test_registry_lookup(self):
        """在已注册的工具列表中查找。"""
        registry = ToolRegistry()
        for _ in range(50):
            registry.register(BashTool(allowed_dir=None))

        def _lookup():
            for name in ["bash"] * 50:
                registry.get(name)

        stats = _time_it(_lookup, warmup=1, repeat=5, label="registry(50lookup)")
        assert stats["mean"] < BENCHMARK_THRESHOLDS["tool_registry"]


# ─── 记忆系统基准测试 ──────────────────────────────────────────────


class TestMemoryBenchmark:
    """文件记忆系统 I/O 性能基准。"""

    @pytest.fixture
    def mem(self) -> FileMemory:
        with tempfile.TemporaryDirectory() as td:
            yield FileMemory(base_dir=str(Path(td) / ".agent"))

    def test_memory_write_small(self, mem: FileMemory):
        """写入小内容（< 100 字符）。"""
        stats = _time_it(
            mem.write,
            "bench-note",
            "Hello World",
            description="benchmark",
            warmup=3,
            repeat=10,
            label="mem.write(small)",
        )
        assert stats["mean"] < BENCHMARK_THRESHOLDS["memory_io"]

    def test_memory_write_large(self, mem: FileMemory):
        """写入大内容（~5KB）。"""
        large_content = "这是基准测试用的较大内容。\n" * 100

        def _write():
            mem.write("bench-large", large_content, description="基准测试大内容")

        stats = _time_it(_write, warmup=2, repeat=5, label="mem.write(large)")
        assert stats["mean"] < BENCHMARK_THRESHOLDS["memory_io"]

    def test_memory_read_existing(self, mem: FileMemory):
        """读取已存在的记忆。"""
        mem.write("bench-read", "基准测试读取内容")

        stats = _time_it(mem.read, "bench-read", warmup=3, repeat=10, label="mem.read()")
        assert stats["mean"] < BENCHMARK_THRESHOLDS["memory_io"]

    def test_memory_search(self, mem: FileMemory):
        """搜索记忆。"""
        for i in range(20):
            mem.write(f"bench-{i}", f"基准测试搜索内容_{i}")

        stats = _time_it(mem.search, query="基准测试", warmup=2, repeat=5, label="mem.search()")
        assert stats["mean"] < BENCHMARK_THRESHOLDS["memory_io"]
