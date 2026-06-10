"""MetricsCollector — 监控指标采集器。

设计依据（规范 7.3）：
  模型调用: 请求量、Token消耗、延时
  工具执行: 调用量、成功率、平均耗时、权限拒绝
  上下文:   Token曲线、压缩触发次数
  系统资源: 内存占用（预留）

通过 Hook 系统采集数据，零侵入式。
提供 get_stats() 查询聚合指标。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    """单次工具调用记录。"""

    name: str
    start_time: float
    end_time: float = 0.0
    duration: float = 0.0
    success: bool = True
    error: str = ""


@dataclass
class TokenUsageRecord:
    """单次模型调用的 Token 消耗。"""

    input_tokens: int = 0
    output_tokens: int = 0


class MetricsCollector:
    """指标采集器。

    通过 Hook 注册，自动采集以下指标：
      - 工具调用次数、耗时、成功率
      - Token 消耗量
      - 循环迭代次数
      - 错误统计

    Usage:
        metrics = MetricsCollector()
        hooks.on(PRE_TOOL, metrics.on_pre_tool)
        hooks.on(POST_TOOL, metrics.on_post_tool)
        hooks.on(POST_LOOP, metrics.on_post_loop)
        print(metrics.get_stats())
    """

    def __init__(self):
        self._tool_calls: list[ToolCallRecord] = []
        self._token_usage: list[TokenUsageRecord] = []
        self._loop_count: int = 0
        self._errors: list[dict] = []
        self._start_time: float = time.time()
        self._active_tools: dict[str, ToolCallRecord] = {}

    # ── Hook Handlers ───────────────────────────────────────────

    def on_pre_loop(self, messages: list[dict]) -> None:
        """PRE_LOOP handler: 记录循环次数。"""
        self._loop_count += 1

    def on_pre_tool(self, tool_call: Any) -> None:
        """PRE_TOOL handler: 开始计时工具调用。"""
        tool_id = getattr(tool_call, "id", str(time.time()))
        tool_name = getattr(tool_call, "name", str(tool_call))
        record = ToolCallRecord(name=tool_name, start_time=time.time())
        self._active_tools[tool_id] = record

    def on_post_tool(self, tool_call: Any, result: Any) -> None:
        """POST_TOOL handler: 记录工具调用结果。"""
        tool_id = getattr(tool_call, "id", "")
        record = self._active_tools.pop(tool_id, None)
        if record is None:
            return

        record.end_time = time.time()
        record.duration = record.end_time - record.start_time

        if isinstance(result, dict):
            error = result.get("error", "")
            if error:
                record.success = False
                record.error = str(error)
                self._errors.append(
                    {
                        "tool": record.name,
                        "error": str(error),
                        "time": time.strftime("%H:%M:%S"),
                    }
                )

        self._tool_calls.append(record)
        logger.debug(
            "工具指标 [%s]: %.3fs %s",
            record.name,
            record.duration,
            "✅" if record.success else "❌",
        )

    def on_post_loop(self, response: Any) -> None:
        """POST_LOOP handler: 记录 Token 用量。"""
        usage = getattr(response, "usage", None)
        if usage:
            record = TokenUsageRecord(
                input_tokens=getattr(usage, "input_tokens", 0),
                output_tokens=getattr(usage, "output_tokens", 0),
            )
            self._token_usage.append(record)

    # ── 指标查询 ─────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """获取所有采集的指标。"""
        elapsed = time.time() - self._start_time
        total_tokens = sum(r.input_tokens + r.output_tokens for r in self._token_usage)

        # 按工具聚合
        tool_stats: dict[str, dict] = {}
        for record in self._tool_calls:
            if record.name not in tool_stats:
                tool_stats[record.name] = {
                    "calls": 0,
                    "successes": 0,
                    "failures": 0,
                    "total_duration": 0.0,
                    "avg_duration": 0.0,
                }
            s = tool_stats[record.name]
            s["calls"] += 1
            s["successes"] += 1 if record.success else 0
            s["failures"] += 0 if record.success else 1
            s["total_duration"] += record.duration

        for s in tool_stats.values():
            s["avg_duration"] = round(s["total_duration"] / s["calls"], 3) if s["calls"] else 0.0
            s["total_duration"] = round(s["total_duration"], 3)

        return {
            "uptime_seconds": round(elapsed, 1),
            "loop_iterations": self._loop_count,
            "tool_calls": {
                "total": len(self._tool_calls),
                "by_tool": tool_stats,
            },
            "token_usage": {
                "total": total_tokens,
                "per_call": [
                    {"input": r.input_tokens, "output": r.output_tokens} for r in self._token_usage
                ],
            },
            "errors": {
                "total": len(self._errors),
                "recent": self._errors[-5:],
            },
        }

    def get_tool_summary(self) -> str:
        """获取工具调用的人类可读摘要。"""
        stats = self.get_stats()
        tools = stats["tool_calls"]["by_tool"]
        if not tools:
            return "暂无工具调用记录。"

        lines = ["工具调用统计:\n"]
        for name, s in sorted(tools.items()):
            rate = round(s["successes"] / s["calls"] * 100, 1) if s["calls"] else 0
            lines.append(
                f"  {name}: {s['calls']} 次调用, 成功率 {rate}%, 平均耗时 {s['avg_duration']:.2f}s"
            )

        errs = stats["errors"]["total"]
        if errs:
            lines.append(f"\n  错误: {errs} 次")
        lines.append(f"\n总循环: {stats['loop_iterations']} 次")
        return "\n".join(lines)

    def reset(self) -> None:
        """重置所有指标。"""
        self._tool_calls.clear()
        self._token_usage.clear()
        self._loop_count = 0
        self._errors.clear()
        self._start_time = time.time()
        self._active_tools.clear()
        logger.info("指标已重置")
