"""WebFetch 工具 — 获取网页内容。

使用 httpx 获取 URL 内容，转换为 Markdown 格式返回。
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseTool, SafetyLevel, ToolSpec

logger = logging.getLogger(__name__)


class WebFetchTool(BaseTool):
    """网页内容获取工具。"""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="web_fetch",
            description="获取指定 URL 的网页内容。返回 Markdown 格式的页面内容。"
            "用于获取在线文档、文章等。",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要获取的网页 URL（必须以 http:// 或 https:// 开头）",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "对返回内容的提取说明（可选），如 '提取文章主要内容'",
                    },
                },
                "required": ["url"],
            },
            handler=self.execute,
            safety=SafetyLevel.ALWAYS_ASK,
        )

    def execute(  # type: ignore[override]
        self, url: str, prompt: str | None = None, **kwargs: Any
    ) -> dict:
        if not url.startswith(("http://", "https://")):
            return {"error": "URL 必须以 http:// 或 https:// 开头", "content": ""}

        try:
            import httpx

            logger.info("获取网页: %s", url)
            resp = httpx.get(url, timeout=30.0, follow_redirects=True)
            resp.raise_for_status()

            # 返回原始 HTML 长度和状态信息
            content_type = resp.headers.get("content-type", "")
            text_length = len(resp.text)
            # 简易 HTML→文本提取
            import re

            text = resp.text
            text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            # 截断到 10000 字符
            if len(text) > 10000:
                text = text[:10000] + "\n\n[... 内容已截断 ...]"

            logger.info("网页获取成功: %s (%d 字符 → %d 字符)", url, text_length, len(text))
            return {
                "url": url,
                "content": text,
                "content_type": content_type,
                "length": len(text),
            }
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP {e.response.status_code}: {e}", "content": ""}
        except httpx.TimeoutException:
            return {"error": f"请求超时: {url}", "content": ""}
        except Exception as e:
            logger.error("网页获取失败: %s — %s", url, e)
            return {"error": str(e), "content": ""}
