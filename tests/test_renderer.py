"""UI 渲染器单元测试。

目标模块: src/agent_cli/ui/renderer.py
当前覆盖率: 0% → 目标 100%

renderer 是纯函数模块，零依赖，最容易测试。
"""

from __future__ import annotations

import json

from agent_cli.ui.renderer import (
    format_error,
    format_info,
    format_result,
    format_tool_call,
)


class TestFormatResult:
    """format_result 函数测试 —— 三种输出模式。"""

    def test_normal_mode(self):
        """normal 模式：直接返回文本，不追加元信息。"""
        result = format_result("你好，世界！", mode="normal")
        assert result == "你好，世界！"

    def test_normal_mode_ignores_meta(self):
        """normal 模式下传入迭代次数不应影响输出。"""
        result = format_result("Hello", iterations=5, tool_calls=3, mode="normal")
        assert result == "Hello"

    def test_verbose_mode(self):
        """verbose 模式：文本末尾追加元信息行。"""
        result = format_result("完成", iterations=3, tool_calls=2, mode="verbose")
        assert "完成" in result
        assert "迭代次数: 3" in result
        assert "工具调用: 2" in result

    def test_verbose_mode_zero_counts(self):
        """verbose 模式：迭代和调用次数为 0 的边界情况。"""
        result = format_result("无操作", iterations=0, tool_calls=0, mode="verbose")
        assert "迭代次数: 0" in result
        assert "工具调用: 0" in result

    def test_verbose_mode_large_numbers(self):
        """verbose 模式：大数值。"""
        result = format_result("批量处理", iterations=999, tool_calls=888, mode="verbose")
        assert "迭代次数: 999" in result
        assert "工具调用: 888" in result

    def test_json_mode(self):
        """json 模式：返回合法 JSON 字符串。"""
        result = format_result("处理完成", iterations=2, tool_calls=1, mode="json")
        parsed = json.loads(result)
        assert parsed["response"] == "处理完成"
        assert parsed["meta"]["iterations"] == 2
        assert parsed["meta"]["tool_calls"] == 1

    def test_json_mode_ensure_ascii_false(self):
        """json 模式：中文不应被转义为 \\u 序列。"""
        result = format_result("你好", mode="json")
        assert "\\u" not in result

    def test_json_mode_pretty_print(self):
        """json 模式：输出应有缩进。"""
        result = format_result("ok", mode="json")
        assert "\n" in result  # indent=2 产生换行


class TestFormatError:
    """format_error 函数测试。"""

    def test_error_message(self):
        """测试错误信息以 ❌ 开头。"""
        result = format_error("文件不存在")
        assert result == "❌ 文件不存在"

    def test_error_empty_string(self):
        """传入空字符串的边界情况。"""
        result = format_error("")
        assert result == "❌ "


class TestFormatInfo:
    """format_info 函数测试。"""

    def test_info_message(self):
        """测试信息提示以 ℹ️ 开头。"""
        result = format_info("系统已就绪")
        assert result == "ℹ️ 系统已就绪"

    def test_info_empty_string(self):
        """传入空字符串的边界情况。"""
        result = format_info("")
        assert result == "ℹ️ "


class TestFormatToolCall:
    """format_tool_call 函数测试。"""

    def test_basic_tool_call(self):
        """基本格式：🛠 [工具名](k=v, ...)。"""
        result = format_tool_call("bash", {"command": "ls"})
        assert "🛠" in result
        assert "[bash]" in result
        assert "command=ls" in result

    def test_multiple_parameters(self):
        """多个参数时用逗号分隔。"""
        result = format_tool_call("read", {"path": "test.txt", "offset": "10"})
        assert "path=test.txt" in result
        assert "offset=10" in result

    def test_empty_dict(self):
        """空参数字典：括号内为空。"""
        result = format_tool_call("noop", {})
        assert result == "🛠 [noop]()"

    def test_mixed_value_types(self):
        """不同类型的参数值（int, str）。"""
        result = format_tool_call("write", {"path": "f.txt", "chars": 42})
        assert "path=f.txt" in result
        assert "chars=42" in result
