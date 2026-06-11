"""监控系统单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from agent_cli.core.provider import Usage
from agent_cli.monitor.alerts import Alert, AlertLevel, AlertManager
from agent_cli.monitor.metrics import MetricsCollector


class TestMetricsCollector:
    """MetricsCollector 测试。"""

    @pytest.fixture
    def metrics(self):
        return MetricsCollector()

    def test_init_empty(self, metrics):
        stats = metrics.get_stats()
        assert stats["tool_calls"]["total"] == 0
        assert stats["loop_iterations"] == 0
        assert stats["errors"]["total"] == 0

    def test_on_pre_loop(self, metrics):
        metrics.on_pre_loop([])
        stats = metrics.get_stats()
        assert stats["loop_iterations"] == 1

    def test_on_pre_loop_multiple(self, metrics):
        metrics.on_pre_loop([])
        metrics.on_pre_loop([])
        metrics.on_pre_loop([])
        stats = metrics.get_stats()
        assert stats["loop_iterations"] == 3

    def test_on_pre_tool_and_post_tool_success(self, metrics):
        tool_call = MagicMock()
        tool_call.id = "tu_001"
        tool_call.name = "bash"

        metrics.on_pre_tool(tool_call)
        metrics.on_post_tool(tool_call, {"stdout": "hello"})

        stats = metrics.get_stats()
        assert stats["tool_calls"]["total"] == 1
        assert stats["errors"]["total"] == 0

    def test_on_pre_tool_and_post_tool_error(self, metrics):
        tool_call = MagicMock()
        tool_call.id = "tu_002"
        tool_call.name = "write"

        metrics.on_pre_tool(tool_call)
        metrics.on_post_tool(tool_call, {"error": "写入失败"})

        stats = metrics.get_stats()
        assert stats["tool_calls"]["total"] == 1
        assert stats["errors"]["total"] == 1

    def test_multiple_tool_calls(self, metrics):
        for i in range(3):
            tc = MagicMock()
            tc.id = f"tu_{i:03d}"
            tc.name = f"tool_{i}"
            metrics.on_pre_tool(tc)
            metrics.on_post_tool(tc, {"result": "ok"})

        stats = metrics.get_stats()
        assert stats["tool_calls"]["total"] == 3
        assert len(stats["tool_calls"]["by_tool"]) == 3

    def test_on_post_loop_with_usage(self, metrics):
        response = MagicMock()
        response.usage = Usage(input_tokens=100, output_tokens=50)

        metrics.on_post_loop(response)

        stats = metrics.get_stats()
        assert stats["token_usage"]["total"] == 150

    def test_on_post_loop_without_usage(self, metrics):
        response = MagicMock()
        response.usage = None

        metrics.on_post_loop(response)  # Should not crash

        stats = metrics.get_stats()
        assert stats["token_usage"]["total"] == 0

    def test_tool_summary_empty(self, metrics):
        summary = metrics.get_tool_summary()
        assert "暂无工具调用记录" in summary

    def test_tool_summary_with_data(self, metrics):
        tc = MagicMock()
        tc.id = "tu_001"
        tc.name = "bash"
        metrics.on_pre_tool(tc)
        metrics.on_post_tool(tc, {"stdout": "ok"})

        summary = metrics.get_tool_summary()
        assert "bash" in summary
        assert "1 次调用" in summary

    def test_reset(self, metrics):
        metrics.on_pre_loop([])
        tc = MagicMock()
        tc.id = "tu_001"
        tc.name = "test"
        metrics.on_pre_tool(tc)
        metrics.on_post_tool(tc, {"result": "ok"})
        metrics.reset()

        stats = metrics.get_stats()
        assert stats["loop_iterations"] == 0
        assert stats["tool_calls"]["total"] == 0


class TestAlertManager:
    """AlertManager 测试。"""

    @pytest.fixture
    def metrics(self):
        m = MetricsCollector()
        return m

    @pytest.fixture
    def alerts(self, metrics):
        return AlertManager(metrics=metrics)

    def test_init_no_alerts(self, alerts):
        assert len(alerts.get_active_alerts()) == 0
        summary = alerts.get_alerts_summary()
        assert "无告警记录" in summary

    def test_check_no_alerts(self, alerts):
        new_alerts = alerts.check()
        assert len(new_alerts) == 0

    def test_check_loop_iterations_warning(self, alerts):
        for _ in range(35):
            alerts._metrics.on_pre_loop([])

        new_alerts = alerts.check()
        assert any(a.level == AlertLevel.WARNING for a in new_alerts)

    def test_check_loop_iterations_critical(self, alerts):
        for _ in range(55):
            alerts._metrics.on_pre_loop([])

        new_alerts = alerts.check()
        assert any(a.level == AlertLevel.CRITICAL for a in new_alerts)

    def test_check_error_rate(self, alerts):
        """错误率超过阈值应触发告警。"""
        # 模拟高错误率
        for i in range(10):
            tc = MagicMock()
            tc.id = f"tu_{i:03d}"
            tc.name = "bash"
            alerts._metrics.on_pre_tool(tc)
            if i < 3:  # 30% error rate
                alerts._metrics.on_post_tool(tc, {"error": "failed"})
            else:
                alerts._metrics.on_post_tool(tc, {"stdout": "ok"})

        new_alerts = alerts.check()
        assert any(a.level == AlertLevel.ERROR for a in new_alerts)

    def test_max_alerts_cap(self, alerts):
        """测试告警数量上限（通过 check 方法触发）。"""
        for i in range(150):
            alerts._alerts.append(Alert(level=AlertLevel.INFO, message="test"))
            # 每添加一些就触发 check，触发 cap
            if i % 20 == 0:
                alerts.check()

    def test_check_max_alerts_cap(self, alerts):
        """check 方法应控制告警数量。"""
        # 模拟多次 check 积累告警
        for _ in range(30):
            alerts._metrics.on_pre_loop([])
        for _ in range(10):
            alerts.check()
        assert len(alerts._alerts) <= 100

    def test_clear(self, alerts):
        alerts._alerts.append(Alert(level=AlertLevel.INFO, message="test"))
        alerts.clear()
        assert len(alerts._alerts) == 0

    def test_get_alerts_summary_with_alerts(self, alerts):
        alerts._alerts.append(Alert(level=AlertLevel.WARNING, message="测试告警"))
        summary = alerts.get_alerts_summary()
        assert "告警记录" in summary

    def test_filter_by_min_level(self, alerts):
        alerts._alerts.append(Alert(level=AlertLevel.INFO, message="info"))
        alerts._alerts.append(Alert(level=AlertLevel.CRITICAL, message="critical"))

        critical_only = alerts.get_active_alerts(min_level=AlertLevel.CRITICAL)
        assert len(critical_only) == 1
        assert critical_only[0].level == AlertLevel.CRITICAL


class TestAlert:
    """Alert 数据类测试。"""

    def test_formatted_info(self):
        alert = Alert(level=AlertLevel.INFO, message="测试信息")
        text = alert.formatted()
        assert "INFO" in text
        assert "测试信息" in text

    def test_formatted_warning(self):
        alert = Alert(level=AlertLevel.WARNING, message="测试警告")
        text = alert.formatted()
        assert "WARNING" in text

    def test_formatted_critical(self):
        alert = Alert(level=AlertLevel.CRITICAL, message="严重告警")
        text = alert.formatted()
        assert "CRITICAL" in text
