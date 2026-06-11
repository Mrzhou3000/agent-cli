"""BashTool 单元测试（补全覆盖率）。

目标模块: src/agent_cli/tools/bash.py
当前覆盖率: 81% → 目标 100%

现有测试在 test_tools/test_registry.py 中覆盖了基本执行和 rm -rf 安全过滤。
本文件补全 spec()、_check_safety 黑名单、超时、异常分支。
"""

from __future__ import annotations

import os
import subprocess
from unittest.mock import patch

from agent_cli.tools.base import SafetyLevel
from agent_cli.tools.bash import BashTool


class TestBashToolSpec:
    """BashTool.spec() 测试。"""

    def test_spec_name(self):
        """spec() 的 name 应为 bash。"""
        tool = BashTool()
        spec = tool.spec()
        assert spec.name == "bash"

    def test_spec_safety(self):
        """bash 安全等级应为 SENSITIVE。"""
        tool = BashTool()
        spec = tool.spec()
        assert spec.safety == SafetyLevel.SENSITIVE

    def test_spec_parameters(self):
        """spec() 参数含 command（必需）和 timeout（可选，默认 30）。"""
        tool = BashTool()
        spec = tool.spec()
        props = spec.parameters.get("properties", {})
        assert "command" in props
        assert "timeout" in props
        assert "command" in spec.parameters.get("required", [])

    def test_spec_timeout_default(self):
        """timeout 参数默认值应为 30。"""
        tool = BashTool()
        spec = tool.spec()
        timeout_prop = spec.parameters["properties"]["timeout"]
        assert timeout_prop.get("default") == 30


class TestBashToolInit:
    """BashTool.__init__ 测试。"""

    def test_default_allowed_dir(self):
        """默认 allowed_dir 为当前工作目录。"""
        tool = BashTool()
        assert tool.allowed_dir == os.getcwd()

    def test_custom_allowed_dir(self):
        """可以设置自定义 allowed_dir。"""
        tool = BashTool(allowed_dir="/tmp")
        assert tool.allowed_dir == "/tmp"


class TestCheckSafety:
    """_check_safety 安全过滤测试。"""

    def test_safe_command_returns_none(self):
        """安全的命令应返回 None。"""
        tool = BashTool()
        assert tool._check_safety("echo hello") is None
        assert tool._check_safety("ls -la") is None
        assert tool._check_safety("python script.py") is None

    def test_block_rm_rf_root(self):
        """rm -rf / 应被拦截。"""
        tool = BashTool()
        result = tool._check_safety("rm -rf /")
        assert result is not None
        assert "黑名单" in result

    def test_block_rm_rf_no_preserve_root(self):
        """rm -rf --no-preserve-root 应被拦截。"""
        tool = BashTool()
        result = tool._check_safety("rm -rf --no-preserve-root /")
        assert result is not None

    def test_block_mkfs(self):
        """mkfs. 格式化命令应被拦截。"""
        tool = BashTool()
        result = tool._check_safety("mkfs.ext4 /dev/sda1")
        assert result is not None

    def test_block_dd_if(self):
        """dd if= 磁盘写入应被拦截。"""
        tool = BashTool()
        result = tool._check_safety("dd if=/dev/zero of=/dev/sda")
        assert result is not None

    def test_block_sudo(self):
        """sudo 命令应被拦截。"""
        tool = BashTool()
        result = tool._check_safety("sudo rm file")
        assert result is not None

    def test_block_chmod_root(self):
        """chmod 777 / 应被拦截。"""
        tool = BashTool()
        result = tool._check_safety("chmod 777 /")
        assert result is not None

    def test_block_chown(self):
        """chown 应被拦截。"""
        tool = BashTool()
        result = tool._check_safety("chown root:root /etc/shadow")
        assert result is not None

    def test_path_traversal_with_cd(self):
        """cd + ../ 路径逃逸应被拦截。"""
        tool = BashTool()
        result = tool._check_safety("cd ../ && ls")
        assert result is not None
        assert "路径逃逸" in result

    def test_case_insensitive_check(self):
        """安全检查不区分大小写。"""
        tool = BashTool()
        result = tool._check_safety("SUDO rm file")
        assert result is not None


class TestBashToolExecute:
    """BashTool.execute() 测试（mock subprocess）。"""

    def test_execute_success(self):
        """正常命令应返回 stdout/stderr/exit_code。"""
        tool = BashTool()
        with patch("agent_cli.tools.bash.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "hello world\n"
            mock_run.return_value.stderr = ""
            mock_run.return_value.returncode = 0
            result = tool.execute(command="echo hello")
            assert result["stdout"].strip() == "hello world"
            assert result["exit_code"] == 0

    def test_execute_with_stderr(self):
        """命令产生 stderr 应正确返回。"""
        tool = BashTool()
        with patch("agent_cli.tools.bash.subprocess.run") as mock_run:
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = "warning: something"
            mock_run.return_value.returncode = 1
            result = tool.execute(command="invalid_cmd")
            assert "warning" in result["stderr"]
            assert result["exit_code"] == 1

    def test_execute_timeout(self):
        """超时应返回超时错误。"""
        tool = BashTool()
        with patch("agent_cli.tools.bash.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd="sleep 100", timeout=5
            )
            result = tool.execute(command="sleep 100", timeout=5)
            assert result["exit_code"] == -1
            assert "超时" in result["stderr"]

    def test_execute_file_not_found(self):
        """命令不存在应返回执行错误。"""
        tool = BashTool()
        with patch("agent_cli.tools.bash.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("not found")
            result = tool.execute(command="nonexistent_cmd")
            assert result["exit_code"] == -1
            assert "执行错误" in result["stderr"]

    def test_execute_safety_block(self):
        """危险命令应被安全机制拦截。"""
        tool = BashTool()
        result = tool.execute(command="rm -rf /")
        assert result["exit_code"] == -1
        assert "安全拒绝" in result["stderr"]

    def test_execute_passes_cwd(self):
        """execute 应将 allowed_dir 作为 cwd 传递给 subprocess。"""
        tool = BashTool(allowed_dir="/tmp")
        with patch("agent_cli.tools.bash.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "ok"
            mock_run.return_value.stderr = ""
            mock_run.return_value.returncode = 0
            tool.execute(command="pwd")
            # 验证 subprocess.run 的 cwd 参数
            _call_kwargs = mock_run.call_args.kwargs
            assert _call_kwargs["cwd"] == "/tmp"
