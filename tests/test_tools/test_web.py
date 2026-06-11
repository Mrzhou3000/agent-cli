"""WebFetchTool 单元测试。

目标模块: src/agent_cli/tools/web.py
当前覆盖率: 0% → 目标 94%

测试策略：mock httpx.get 避免真实网络请求。
使用 MagicMock 模拟响应对象，避免 httpx.Response 构造复杂性。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent_cli.tools.base import SafetyLevel
from agent_cli.tools.web import WebFetchTool


class TestWebFetchTool:
    """WebFetchTool 单元测试。"""

    def make_mock_response(
        self,
        text: str,
        content_type: str = "text/html",
        status_code: int = 200,
    ):
        """创建模拟的 httpx 响应对象（MagicMock 完全控制）。"""
        mock_resp = MagicMock()
        mock_resp.text = text
        mock_resp.headers = {"content-type": content_type}
        mock_resp.status_code = status_code
        # raise_for_status 默认不抛异常
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    # ── spec() 测试 ──────────────────────────────────────────────────────

    def test_spec_name(self):
        """spec() 返回的 name 应为 web_fetch。"""
        tool = WebFetchTool()
        spec = tool.spec()
        assert spec.name == "web_fetch"

    def test_spec_safety(self):
        """web_fetch 安全等级应为 ALWAYS_ASK。"""
        tool = WebFetchTool()
        spec = tool.spec()
        assert spec.safety == SafetyLevel.ALWAYS_ASK

    def test_spec_parameters(self):
        """spec() 参数中 url 为必需，prompt 可选。"""
        tool = WebFetchTool()
        spec = tool.spec()
        assert "url" in spec.parameters.get("required", [])
        assert "prompt" in spec.parameters.get("properties", {})

    # ── execute(): URL 校验 ─────────────────────────────────────────────

    def test_execute_invalid_url_no_scheme(self):
        """URL 不以 http/https 开头时应返回 error。"""
        tool = WebFetchTool()
        result = tool.execute(url="ftp://example.com")
        assert "error" in result
        assert result["content"] == ""

    def test_execute_invalid_url_empty(self):
        """空 URL 应返回 error。"""
        tool = WebFetchTool()
        result = tool.execute(url="")
        assert "error" in result

    # ── execute(): 正常请求 ──────────────────────────────────────────────

    def test_execute_success(self):
        """正常页面应返回 url、content、content_type、length。"""
        tool = WebFetchTool()
        with patch("httpx.get") as mock_get:
            mock_get.return_value = self.make_mock_response(
                text="<html><body>Hello World</body></html>",
                content_type="text/html; charset=utf-8",
            )
            result = tool.execute(url="https://example.com")
            assert result["url"] == "https://example.com"
            assert "Hello World" in result["content"]
            assert "text/html" in result["content_type"]
            assert result["length"] > 0
            mock_get.assert_called_once_with(
                "https://example.com", timeout=30.0, follow_redirects=True
            )

    def test_execute_strips_script_tags(self):
        """<script> 标签内容应从输出中移除。"""
        tool = WebFetchTool()
        html = "<html><script>alert('xss')</script><body>Safe</body></html>"
        with patch("httpx.get") as mock_get:
            mock_get.return_value = self.make_mock_response(text=html)
            result = tool.execute(url="https://example.com")
            assert "alert" not in result["content"]
            assert "Safe" in result["content"]

    def test_execute_strips_style_tags(self):
        """<style> 标签内容应从输出中移除。"""
        tool = WebFetchTool()
        html = "<html><style>body { color: red; }</style><body>Visible</body></html>"
        with patch("httpx.get") as mock_get:
            mock_get.return_value = self.make_mock_response(text=html)
            result = tool.execute(url="https://example.com")
            assert "color: red" not in result["content"]
            assert "Visible" in result["content"]

    def test_execute_truncates_long_content(self):
        """超过 10000 字符的内容应被截断。"""
        tool = WebFetchTool()
        long_text = "<html><body>" + "x" * 20000 + "</body></html>"
        with patch("httpx.get") as mock_get:
            mock_get.return_value = self.make_mock_response(text=long_text)
            result = tool.execute(url="https://example.com")
            # 10000 字符 + 截断提示
            assert len(result["content"]) <= 10000 + len("\n\n[... 内容已截断 ...]")
            assert "内容已截断" in result["content"]

    # ── execute(): 错误处理 ──────────────────────────────────────────────

    def test_execute_http_404(self):
        """HTTP 404 应通过 raise_for_status 返回错误信息。"""
        tool = WebFetchTool()
        import httpx

        with patch("httpx.get") as mock_get:
            mock_resp = self.make_mock_response(text="Not Found", status_code=404)
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "404 Client Error",
                request=MagicMock(),
                response=mock_resp,
            )
            mock_get.return_value = mock_resp
            result = tool.execute(url="https://example.com/404")
            assert "error" in result
            assert "404" in result["error"]

    def test_execute_timeout(self):
        """请求超时应返回超时错误。"""
        tool = WebFetchTool()
        import httpx

        with patch("httpx.get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("timeout")
            result = tool.execute(url="https://example.com")
            assert "error" in result
            assert "超时" in result["error"]

    def test_execute_generic_exception(self):
        """通用异常应返回异常字符串。"""
        tool = WebFetchTool()
        with patch("httpx.get") as mock_get:
            mock_get.side_effect = ConnectionError("网络不可达")
            result = tool.execute(url="https://example.com")
            assert "error" in result
            assert "网络不可达" in result["error"]
