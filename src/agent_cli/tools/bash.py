"""Bash 工具 — 执行 shell 命令。

安全机制：
  - cwd 边界检查：禁止逃逸到项目目录之外
  - 危险命令黑名单：rm -rf /, sudo, 等
  - 超时控制：默认 30s 超时
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

from .base import BaseTool, SafetyLevel, ToolSpec

logger = logging.getLogger(__name__)

# 危险命令前缀黑名单
DANGEROUS_COMMANDS: tuple[str, ...] = (
    "rm -rf /",
    "rm -rf --no-preserve-root",
    "mkfs.",
    "dd if=",
    ">:",
    "| shutdown",
    "| reboot",
    "sudo",
    "chmod 777 /",
    "chown",
)


class BashTool(BaseTool):
    """Bash 命令执行工具。"""

    def __init__(self, allowed_dir: str | None = None):
        self.allowed_dir = allowed_dir or os.getcwd()

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="bash",
            description="执行 shell 命令。支持管道、重定向、复杂命令组合。"
            "执行完成后返回 stdout 和 stderr 的输出。",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令。如 'ls -la'、'echo hello'",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时时间（秒），默认 30",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
            handler=self.execute,
            safety=SafetyLevel.SENSITIVE,
        )

    def execute(self, command: str, timeout: int = 30, **kwargs: Any) -> dict[str, Any]:
        """执行 bash 命令。

        Args:
            command: shell 命令。
            timeout: 超时秒数。

        Returns:
            {"stdout": "...", "stderr": "...", "exit_code": 0}

        Raises:
            ValueError: 命令被安全策略拒绝。
        """
        # 安全检查
        violation = self._check_safety(command)
        if violation:
            logger.warning("危险命令被拒绝: %s — %s", command, violation)
            return {
                "stdout": "",
                "stderr": f"[安全拒绝] {violation}",
                "exit_code": -1,
            }

        try:
            logger.info("执行命令: %s (timeout=%ds)", command, timeout)
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.allowed_dir,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            logger.warning("命令超时: %s (%ds)", command, timeout)
            return {
                "stdout": "",
                "stderr": f"命令执行超时（{timeout}秒）",
                "exit_code": -1,
            }
        except Exception as e:
            logger.error("命令执行失败: %s — %s", command, e)
            return {"stdout": "", "stderr": f"执行错误: {e}", "exit_code": -1}

    def _check_safety(self, command: str) -> str | None:
        """检查命令安全性。返回违规则由描述，否则返回 None。"""
        cmd_stripped = command.strip().lower()

        for dangerous in DANGEROUS_COMMANDS:
            if dangerous in cmd_stripped:
                return f"命令包含黑名单操作: {dangerous}"

        # cwd 边界检查：路径逃逸
        if "../" in command and "cd" in command:
            return "路径逃逸: 禁止使用 ../ 离开允许目录"

        return None
