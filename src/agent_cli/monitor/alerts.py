"""AlertManager — 告警管理。

设计依据（规范 7.6）：
  P0 致命: API连续失败5次 / 无限循环检测 → 终端闪红
  P1 严重: 错误率 > 5% / 内存 > 300MB → 终端警告
  P2 警告: 重试超2次 / 压缩率 < 20% → 日志WARN
  P3 通知: 会话超1小时 / Token超额50% → 日志INFO

基于 MetricsCollector 的聚合数据触发告警。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from agent_cli.monitor.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class AlertLevel(IntEnum):
    """告警级别（数字越大越严重）。"""

    INFO = 0  # P3 通知
    WARNING = 1  # P2 警告
    ERROR = 2  # P1 严重
    CRITICAL = 3  # P0 致命


LEVEL_NAMES = {
    AlertLevel.INFO: "INFO",
    AlertLevel.WARNING: "WARNING",
    AlertLevel.ERROR: "ERROR",
    AlertLevel.CRITICAL: "CRITICAL",
}

LEVEL_ICONS = {
    AlertLevel.INFO: "ℹ️",
    AlertLevel.WARNING: "⚠️",
    AlertLevel.ERROR: "🔴",
    AlertLevel.CRITICAL: "🚨",
}


@dataclass
class Alert:
    """告警记录。"""

    level: AlertLevel
    message: str
    source: str = ""
    timestamp: str = ""

    def formatted(self) -> str:
        """格式化告警文本。"""
        icon = LEVEL_ICONS.get(self.level, "•")
        level_name = LEVEL_NAMES.get(self.level, "UNKNOWN")
        return f"{icon} [{level_name}] {self.message}"


class AlertManager:
    """告警管理器。

    基于 MetricsCollector 的统计指标触发告警。
    支持自定义告警阈值和回调。

    Usage:
        metrics = MetricsCollector()
        alerts = AlertManager(metrics)
        alerts.check()  # 检测所有告警条件
        print(alerts.get_active_alerts())
    """

    def __init__(
        self,
        metrics: MetricsCollector | None = None,
    ):
        self._metrics = metrics or MetricsCollector()
        self._alerts: list[Alert] = []
        self._max_alerts = 100

        # 默认告警阈值
        self.thresholds: dict[str, Any] = {
            "max_consecutive_errors": 5,  # P0: 连续错误
            "max_error_rate": 0.05,  # P1: 错误率 > 5%
            "max_loop_iterations": 50,  # P0: 循环迭代过多
            "warn_loop_iterations": 30,  # P2: 循环迭代警告
            "max_retries": 2,  # P2: 重试超 2 次
        }

    def check(self) -> list[Alert]:
        """检查所有告警条件，返回新触发的告警。"""
        new_alerts: list[Alert] = []
        stats = self._metrics.get_stats()

        # P0: 连续错误检测
        errors = stats.get("errors", {}).get("total", 0)
        if errors >= self.thresholds["max_consecutive_errors"]:
            new_alerts.append(
                Alert(
                    level=AlertLevel.CRITICAL,
                    message=f"连续错误已达 {errors} 次，需要人工介入",
                    source="AlertManager",
                )
            )

        # P0: 循环迭代过多
        loops = stats.get("loop_iterations", 0)
        if loops >= self.thresholds["max_loop_iterations"]:
            new_alerts.append(
                Alert(
                    level=AlertLevel.CRITICAL,
                    message=f"循环迭代次数异常: {loops} 次",
                    source="AlertManager",
                )
            )

        # P2: 循环迭代警告
        if loops >= self.thresholds["warn_loop_iterations"]:
            new_alerts.append(
                Alert(
                    level=AlertLevel.WARNING,
                    message=f"循环迭代较多: {loops} 次",
                    source="AlertManager",
                )
            )

        # P1: 错误率检测
        tool_stats = stats.get("tool_calls", {})
        total_calls = tool_stats.get("total", 0)
        if total_calls > 0:
            error_rate = errors / total_calls
            if error_rate > self.thresholds["max_error_rate"]:
                new_alerts.append(
                    Alert(
                        level=AlertLevel.ERROR,
                        message=f"工具调用错误率 {error_rate:.1%} 超过阈值 "
                        f"{self.thresholds['max_error_rate']:.0%}",
                        source="AlertManager",
                    )
                )

        # 记录新告警并清理旧告警
        self._alerts.extend(new_alerts)
        if len(self._alerts) > self._max_alerts:
            self._alerts = self._alerts[-self._max_alerts :]

        # 输出告警到日志
        for alert in new_alerts:
            log_level = {
                AlertLevel.INFO: logging.INFO,
                AlertLevel.WARNING: logging.WARNING,
                AlertLevel.ERROR: logging.ERROR,
                AlertLevel.CRITICAL: logging.CRITICAL,
            }.get(alert.level, logging.WARNING)
            logger.log(log_level, "告警: %s", alert.message)

        return new_alerts

    def get_active_alerts(self, min_level: AlertLevel = AlertLevel.INFO) -> list[Alert]:
        """获取活跃告警列表。

        Args:
            min_level: 最低告警级别。

        Returns:
            符合级别的告警列表。
        """
        return [a for a in self._alerts if a.level >= min_level]

    def get_alerts_summary(self) -> str:
        """获取告警摘要文本。"""
        if not self._alerts:
            return "无告警记录。\n"

        # 按级别分组
        by_level: dict[AlertLevel, list[Alert]] = {}
        for alert in self._alerts:
            by_level.setdefault(alert.level, []).append(alert)

        lines = ["告警记录:\n"]
        for level in sorted(by_level.keys(), reverse=True):
            alerts = by_level[level]
            icon = LEVEL_ICONS.get(level, "•")
            name = LEVEL_NAMES.get(level, "")
            lines.append(f"  {icon} [{name}] {len(alerts)} 条")

        lines.append("\n最近告警:")
        for alert in self._alerts[-5:]:
            lines.append(f"  {alert.formatted()}")

        lines.append("")
        return "\n".join(lines)

    def clear(self) -> None:
        """清除所有告警记录。"""
        self._alerts.clear()
        logger.info("告警记录已清除")
