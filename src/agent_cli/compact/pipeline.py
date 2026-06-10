"""CompactPipeline — 四层上下文压缩管道。

设计哲学（来源：learn-claude-code）：
  这是 learn-claude-code 项目最有特色的设计。
  L1-L3 零 API 调用，纯算法压缩。
  L4 使用 LLM 重写关键上下文。
  70% 阈值触发 L1-L3，90% 阈值触发 L4。

L1 (丢弃层):
  - 丢弃已完成的 tool_use 调用 details（保留 tool_result）
  - 丢弃 tool_result 中过大的内容（> 2000 字符截断）
  - 移除空的 tool_result 块

L2 (合并层):
  - 合并连续的 tool_result 消息
  - 合并连续的 text-only assistant 消息
  - 合并连续的 user 消息

L3 (摘要层):
  - 对早期对话做结构化摘要
  - 提取关键决策和结论
  - 移除非核心的中间步骤

L4 (重写层 — 需要 LLM):
  - 用 LLM 重写关键上下文
  - 保持语义完整性
  - 标记压缩来源位置
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

from agent_cli.core.provider import IModelProvider

logger = logging.getLogger(__name__)

# 估算 token 数的经验常量
_CHARS_PER_TOKEN = 4
_TOOL_BLOCK_BASE = 50  # 每个 tool_use block 的固定开销


def _estimate_tokens(data: Any) -> int:
    """估算任意数据的 token 数。

    使用简单字符计数法（~4 chars/token），
    对结构化的 tool block 添加额外开销估算。
    """
    if isinstance(data, str):
        return math.ceil(len(data) / _CHARS_PER_TOKEN)
    if isinstance(data, list):
        return sum(_estimate_tokens(item) for item in data)
    if isinstance(data, dict):
        total = sum(_estimate_tokens(v) for v in data.values())
        # tool block 有结构化开销
        if data.get("type") in ("tool_use", "tool_result"):
            total += _TOOL_BLOCK_BASE
        return total
    return len(str(data)) // _CHARS_PER_TOKEN


class CompactPipeline:
    """四层上下文压缩管道。

    Usage:
        pipeline = CompactPipeline(max_tokens=100000)
        if pipeline.should_compact(messages):
            messages = pipeline.compress(messages)
    """

    COMPACT_RATIO = 0.7  # 70% → 触发 L1-L3
    CRITICAL_RATIO = 0.9  # 90% → 触发 L4

    def __init__(
        self,
        max_tokens: int = 100000,
        provider: IModelProvider | None = None,
    ):
        self._max_tokens = max_tokens
        self._provider = provider
        self.compression_count = 0
        self.last_ratio = 0.0

    def should_compact(self, messages: list[dict]) -> bool:
        """检查是否需要压缩。

        Args:
            messages: 消息列表。

        Returns:
            超过 70% 阈值返回 True。
        """
        if not messages:
            return False
        current = _estimate_tokens(messages)
        ratio = current / self._max_tokens
        self.last_ratio = ratio
        return ratio >= self.COMPACT_RATIO

    def compress(self, messages: list[dict]) -> list[dict]:
        """执行渐进压缩。

        根据当前 Token 比率自动选择压缩层级：
          - < 70%: 不压缩
          - 70-90%: L1 丢弃
          - >= 90%: L1 → L2 → L3

        Args:
            messages: 消息列表。

        Returns:
            压缩后的消息列表。
        """
        if not messages:
            return messages

        ratio = _estimate_tokens(messages) / self._max_tokens
        self.last_ratio = ratio
        self.compression_count += 1

        if ratio < self.COMPACT_RATIO:
            logger.debug("压缩跳过: ratio=%.2f < %.2f", ratio, self.COMPACT_RATIO)
            return messages

        logger.info("压缩触发 #%d: ratio=%.2f", self.compression_count, ratio)

        # L1: 丢弃层
        compressed = self._layer1_discard(messages)
        if ratio < self.CRITICAL_RATIO:
            compressed.append(self._compression_marker("L1"))
            logger.info("L1 压缩完成: %d → %d 条", len(messages), len(compressed))
            return compressed

        # L2: 合并层
        compressed = self._layer2_merge(compressed)
        compressed.append(self._compression_marker("L1+L2"))
        logger.info("L1+L2 压缩完成: %d → %d 条", len(messages), len(compressed))

        # L3: 摘要层
        compressed = self._layer3_summarize(compressed)

        # L4: 重写层（仅当有 LLM Provider 时）
        if ratio >= self.CRITICAL_RATIO and self._provider is not None:
            compressed = self._layer4_rewrite(compressed)

        compressed.append(self._compression_marker("L3+L4" if self._provider else "L3"))
        logger.info("压缩完成: %d → %d 条", len(messages), len(compressed))
        return compressed

    def _compression_marker(self, level: str) -> dict:
        """生成压缩标记消息。"""
        return {
            "role": "system",
            "content": f"[compressed: {level}] 上下文已压缩以减少 Token 消耗。"
            f" 压缩 #{self.compression_count}, ratio={self.last_ratio:.1%}",
        }

    # ── L1: 丢弃层 ──────────────────────────────────────────

    def _layer1_discard(self, messages: list[dict]) -> list[dict]:
        """丢弃过时细节，保留核心信息。"""
        result: list[dict] = []
        for msg in messages:
            content = msg.get("content", "")

            # 跳过空的 tool_result
            if isinstance(content, list):
                filtered_blocks = []
                for block in content:
                    if block.get("type") == "tool_result":
                        block_content = block.get("content", "")
                        # 截断过大的 tool_result
                        if isinstance(block_content, str) and len(block_content) > 2000:
                            block = dict(block)
                            block["content"] = block_content[:2000] + "\n... [截断]"
                        # 跳过完全空的 tool_result
                        if not block_content or (
                            isinstance(block_content, dict) and block_content.get("content") == ""
                        ):
                            continue
                    filtered_blocks.append(block)
                if filtered_blocks:
                    result.append({**msg, "content": filtered_blocks})
                continue

            if isinstance(content, str) and len(content) > 4000:
                result.append({**msg, "content": content[:4000] + "\n... [截断]"})
                continue

            result.append(msg)

        return result

    # ── L2: 合并层 ──────────────────────────────────────────

    def _layer2_merge(self, messages: list[dict]) -> list[dict]:
        """合并相邻同类消息。"""
        if not messages:
            return messages

        merged: list[dict] = [messages[0]]

        for msg in messages[1:]:
            last = merged[-1]
            last_role = last.get("role", "")
            curr_role = msg.get("role", "")

            # 合并连续 tool_result (user role)
            last_content = last.get("content")
            msg_content = msg.get("content")

            def _all_tool_results(items: list) -> bool:
                return all(isinstance(b, dict) and b.get("type") == "tool_result" for b in items)

            if (
                last_role == "user"
                and curr_role == "user"
                and isinstance(last_content, list)
                and isinstance(msg_content, list)
                and _all_tool_results(last_content)
                and _all_tool_results(msg_content)
            ):
                merged[-1] = {**last, "content": last["content"] + msg["content"]}
                continue

            # 合并连续 assistant text-only 消息
            if last_role == "assistant" and curr_role == "assistant":
                last_text = self._get_text_content(last)
                curr_text = self._get_text_content(msg)
                if last_text and curr_text:
                    merged[-1] = {
                        "role": "assistant",
                        "content": last_text + "\n" + curr_text,
                    }
                    continue

            merged.append(msg)

        return merged

    def _get_text_content(self, msg: dict) -> str:
        """从消息中提取文本内容。"""
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            return " ".join(parts)
        return ""

    # ── L3: 摘要层 ──────────────────────────────────────────

    def _layer3_summarize(self, messages: list[dict]) -> list[dict]:
        """对早期对话做结构化摘要。

        保留最近 6 条消息完整，之前的消息压缩为摘要。
        """
        if len(messages) <= 6:
            return messages

        keep_recent = messages[-6:]
        early = messages[:-6]

        # 从早期消息中提取关键信息
        topics: list[str] = []
        files: set[str] = set()

        for msg in early:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                text = content if isinstance(content, str) else ""
                if text:
                    topics.append(text[:100])

            elif role == "assistant":
                text = content if isinstance(content, str) else ""
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            text += block.get("text", "") or ""
                # 提取文件路径
                import re

                found_files = re.findall(r"[\w/.-]+\.\w+", text)
                files.update(f for f in found_files if "/" in f or "\\" in f)

        summary_text = (
            f"[对话摘要] 共 {len(early)} 条早期消息。\n"
            f"涉及文件: {', '.join(list(files)[:10]) if files else 'N/A'}\n"
        )
        if topics:
            summary_text += f"关键主题: {' | '.join(topics[:5])}\n"

        return [
            {"role": "system", "content": summary_text},
            *keep_recent,
        ]

    # ── L4: 重写层 ──────────────────────────────────────────

    def _layer4_rewrite(self, messages: list[dict]) -> list[dict]:
        """用 LLM 重写关键上下文。"""
        if not self._provider:
            logger.warning("L4 需要 LLM Provider，跳过")
            return messages

        try:
            prompt = (
                "请压缩以下对话历史，保留所有关键信息、决策和上下文，"
                "但使用更简洁的表达。请直接输出压缩后的对话内容。\n\n"
                f"对话历史:\n{json.dumps(messages[-20:], ensure_ascii=False)}"
            )

            response = self._provider.invoke(
                messages=[{"role": "user", "content": prompt}],
            )

            if response.text:
                return [
                    {
                        "role": "system",
                        "content": f"[compressed: L4 - LLM 重写]\n{response.text[:5000]}",
                    },
                ]
        except Exception as e:
            logger.error("L4 重写失败: %s", e)

        return messages

    def get_stats(self) -> dict:
        """获取压缩统计信息。"""
        return {
            "compression_count": self.compression_count,
            "last_ratio": round(self.last_ratio, 3),
            "max_tokens": self._max_tokens,
            "compact_ratio": self.COMPACT_RATIO,
            "critical_ratio": self.CRITICAL_RATIO,
        }
