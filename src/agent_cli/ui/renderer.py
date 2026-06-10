"""CLI 输出渲染。

设计依据：模块 4.10 — 输出分级 normal/verbose/json。
"""

from __future__ import annotations

import json


def format_result(
    response_text: str,
    iterations: int = 0,
    tool_calls: int = 0,
    mode: str = "normal",
) -> str:
    """格式化 Agent 输出。

    Args:
        response_text: 模型回复文本。
        iterations: 循环迭代次数。
        tool_calls: 工具调用次数。
        mode: 输出模式：normal / verbose / json。

    Returns:
        格式化后的输出字符串。
    """
    if mode == "json":
        return json.dumps(
            {
                "response": response_text,
                "meta": {"iterations": iterations, "tool_calls": tool_calls},
            },
            ensure_ascii=False,
            indent=2,
        )

    if mode == "verbose":
        meta = f"\n[元信息] 迭代次数: {iterations} | 工具调用: {tool_calls}"
        return response_text + meta

    return response_text


def format_error(error: str) -> str:
    """格式化错误信息。"""
    return f"❌ {error}"


def format_info(msg: str) -> str:
    """格式化信息提示。"""
    return f"ℹ️ {msg}"


def format_tool_call(name: str, inp: dict) -> str:
    """格式化工具调用信息。"""
    inp_str = ", ".join(f"{k}={v}" for k, v in inp.items())
    return f"🛠 [{name}]({inp_str})"
