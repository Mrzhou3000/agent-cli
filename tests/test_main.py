"""CLI 集成测试 — 测试 Typer 命令解析和组件工厂函数。

使用 typer.testing.CliRunner 模拟命令行调用。
不启动真实 Provider，只验证参数解析和组件创建。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from agent_cli.main import _build_skill_handler, _create_provider, app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ─── 全局 CLI ────────────────────────────────────────────────────


class TestCliGlobal:
    """全局 CLI 行为测试。"""

    def test_version(self, runner: CliRunner):
        """--version 显示版本。"""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "agent-cli v" in result.output

    def test_no_args_shows_help(self, runner: CliRunner):
        """无参数显示帮助（exit_code=2 是 Typer 的行为）。"""
        result = runner.invoke(app, [])
        # Typer 的 no_args_is_help=True 用 exit_code 2 表示帮助已显示
        assert "Usage:" in result.output or "用法" in result.output or "agent-cli" in result.output

    def test_help(self, runner: CliRunner):
        """--help 显示帮助。"""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0


# ─── init 命令 ───────────────────────────────────────────────────


class TestInitCommand:
    """agent-cli init 命令测试。"""

    def test_init_creates_dirs(self, runner: CliRunner, tmp_path: Path):
        """init 创建必要的目录结构。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(app, ["init"])
                assert result.exit_code == 0
                assert ".agent/" in result.output or "创建" in result.output
                assert Path(td, ".agent", "memory").exists()
                assert Path(td, ".agent", "sessions").exists()
                assert Path(td, ".agent", "logs").exists()
                assert Path(td, ".agent", "permissions.json").exists()
            finally:
                os.chdir(orig_dir)

    def test_init_force_overwrites(self, runner: CliRunner, tmp_path: Path):
        """--force 覆盖已有配置。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                # 第一次 init
                runner.invoke(app, ["init"])
                # 第二次不带 force → 显示 skip
                result = runner.invoke(app, ["init"])
                assert "skip" in result.output or "已存在" in result.output
                # 第三次带 force → 重新创建
                result = runner.invoke(app, ["init", "--force"])
                assert result.exit_code == 0
            finally:
                os.chdir(orig_dir)


# ─── _create_provider 单元测试 ──────────────────────────────────


class TestCreateProvider:
    """_create_provider 工厂函数测试。"""

    def test_auto_no_key_returns_mock(self):
        """auto 模式无 API key 时返回 MockProvider。"""
        with patch.dict(os.environ, {}, clear=True):
            provider = _create_provider(provider="auto")
            from agent_cli.core.provider import MockProvider

            assert isinstance(provider, MockProvider)

    def test_auto_anthropic_key(self):
        """auto 模式有 ANTHROPIC_API_KEY 时返回 AnthropicProvider。"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            provider = _create_provider(provider="auto")
            from agent_cli.core.provider import AnthropicProvider

            assert isinstance(provider, AnthropicProvider)
            assert provider.model == "claude-sonnet-4-20250514"

    def test_auto_compatible_key(self):
        """auto 模式有 COMPATIBLE_API_KEY 时返回 CompatibleProvider。"""
        with patch.dict(os.environ, {"COMPATIBLE_API_KEY": "sk-test"}):
            provider = _create_provider(provider="auto")
            from agent_cli.core.provider import CompatibleProvider

            assert isinstance(provider, CompatibleProvider)
            assert "deepseek" in provider.model

    def test_mock_provider(self):
        """显式 mock 返回 MockProvider。"""
        provider = _create_provider(provider="mock")
        from agent_cli.core.provider import MockProvider

        assert isinstance(provider, MockProvider)

    def test_anthropic_explicit(self):
        """显式 anthropic 返回 AnthropicProvider。"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            provider = _create_provider(provider="anthropic")
            from agent_cli.core.provider import AnthropicProvider

            assert isinstance(provider, AnthropicProvider)

    def test_anthropic_with_api_key_arg(self):
        """--api-key 覆盖环境变量。"""
        with patch.dict(os.environ, {}, clear=True):
            provider = _create_provider(provider="anthropic", api_key="sk-ant-direct")
            assert provider is not None

    def test_compatible_explicit(self):
        """显式 compatible 返回 CompatibleProvider。"""
        with patch.dict(os.environ, {"COMPATIBLE_API_KEY": "sk-test"}):
            provider = _create_provider(provider="compatible")
            from agent_cli.core.provider import CompatibleProvider

            assert isinstance(provider, CompatibleProvider)

    def test_compatible_with_base_url(self):
        """--base-url 自定义端点。"""
        with patch.dict(os.environ, {"COMPATIBLE_API_KEY": "sk-test"}):
            provider = _create_provider(
                provider="compatible",
                base_url="https://api.openai.com/v1",
                model="gpt-4",
            )
            assert provider.base_url == "https://api.openai.com/v1"
            assert "gpt-4" in provider.model

    def test_anthropic_priority_in_auto(self):
        """auto 模式 ANTHROPIC_API_KEY 优先于 COMPATIBLE_API_KEY。"""
        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "sk-ant-test", "COMPATIBLE_API_KEY": "sk-comp-test"},
        ):
            provider = _create_provider(provider="auto")
            from agent_cli.core.provider import AnthropicProvider

            assert isinstance(provider, AnthropicProvider)

    def test_custom_model_auto(self):
        """auto 模式自定义 model 参数传递。"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            provider = _create_provider(provider="auto", model="claude-sonnet-4-20250514")
            assert "sonnet" in provider.model

    def test_case_insensitive_provider(self):
        """provider 参数大小写不敏感。"""
        with patch.dict(os.environ, {}, clear=True):
            provider = _create_provider(provider="Mock")
            from agent_cli.core.provider import MockProvider

            assert isinstance(provider, MockProvider)


# ─── _build_skill_handler 测试 ──────────────────────────────────


class TestBuildSkillHandler:
    """_build_skill_handler 工厂函数测试。"""

    def test_no_skills_returns_none(self, tmp_path: Path):
        """无技能文件时返回 None。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                handler = _build_skill_handler(base_dir=".agent")
                assert handler is None
            finally:
                os.chdir(orig_dir)

    def test_with_skills_returns_handler(self, tmp_path: Path):
        """有技能文件时返回可调用 handler。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                # 创建技能目录和技能文件
                skill_dir = Path(td, ".agent", "skills")
                skill_dir.mkdir(parents=True, exist_ok=True)
                skill_file = skill_dir / "test-skill.md"
                skill_file.write_text(
                    "---\n"
                    "name: test-skill\n"
                    "description: testing skill\n"
                    "triggers:\n"
                    "  - test\n"
                    "---\n"
                    "\n"
                    "# test skill content\n\nthis is a test.\n",
                    encoding="utf-8",
                )

                handler = _build_skill_handler(base_dir=".agent")
                assert callable(handler)
            finally:
                os.chdir(orig_dir)

    def test_handler_injects_skill_on_match(self, tmp_path: Path):
        """匹配触发词时 handler 注入技能内容到消息列表。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                skill_dir = Path(td, ".agent", "skills")
                skill_dir.mkdir(parents=True, exist_ok=True)
                skill_file = skill_dir / "test-skill.md"
                skill_file.write_text(
                    "---\n"
                    "name: test-skill\n"
                    "description: testing skill\n"
                    "triggers:\n"
                    "  - test\n"
                    "---\n"
                    "\n"
                    "skill body\n",
                    encoding="utf-8",
                )

                handler = _build_skill_handler(base_dir=".agent")
                assert handler is not None

                messages = [{"role": "user", "content": "run a test request"}]
                handler(messages)

                # verify skill was injected at the beginning
                assert len(messages) == 2
                assert messages[0]["role"] == "system"
                assert "skill body" in messages[0]["content"]
            finally:
                os.chdir(orig_dir)

    def test_handler_no_match_no_inject(self, tmp_path: Path):
        """不匹配触发词时 handler 不修改消息列表。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                skill_dir = Path(td, ".agent", "skills")
                skill_dir.mkdir(parents=True, exist_ok=True)
                skill_file = skill_dir / "test-skill.md"
                skill_file.write_text(
                    "---\n"
                    "name: test-skill\n"
                    "description: testing skill\n"
                    "triggers:\n"
                    "  - test\n"
                    "---\n"
                    "\n"
                    "skill body\n",
                    encoding="utf-8",
                )

                handler = _build_skill_handler(base_dir=".agent")
                assert handler is not None

                messages = [{"role": "user", "content": "hello, how are you?"}]
                handler(messages)

                # 技能不匹配，消息列表不变
                assert len(messages) == 1
                assert messages[0]["role"] == "user"
            finally:
                os.chdir(orig_dir)

    def test_handler_empty_messages(self, tmp_path: Path):
        """空消息列表时 handler 不报错。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                skill_dir = Path(td, ".agent", "skills")
                skill_dir.mkdir(parents=True, exist_ok=True)
                skill_file = skill_dir / "test-skill.md"
                skill_file.write_text(
                    "---\n"
                    "name: test-skill\n"
                    "description: testing skill\n"
                    "triggers:\n"
                    "  - test\n"
                    "---\n"
                    "\n"
                    "skill body\n",
                    encoding="utf-8",
                )

                handler = _build_skill_handler(base_dir=".agent")
                assert handler is not None

                # 空列表不应报错
                handler([])

                # 无 user 消息也不应报错
                handler([{"role": "system", "content": "你是助手"}])
            finally:
                os.chdir(orig_dir)


# ─── permissions 命令 ────────────────────────────────────────────


class TestPermissionCommand:
    """agent-cli permission 命令测试。"""

    def test_permission_list_empty(self, runner: CliRunner):
        """permission --list 无规则时显示空。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(app, ["permission", "--list"])
                assert result.exit_code == 0
            finally:
                os.chdir(orig_dir)

    def test_permission_allow(self, runner: CliRunner):
        """permission --allow 添加规则。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(app, ["permission", "--allow", "bash"])
                assert result.exit_code == 0
                assert "永久允许" in result.output or "Allow" in result.output
            finally:
                os.chdir(orig_dir)

    def test_permission_deny(self, runner: CliRunner):
        """permission --deny 添加规则。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(app, ["permission", "--deny", "write"])
                assert result.exit_code == 0
                assert "永久拒绝" in result.output or "Deny" in result.output
            finally:
                os.chdir(orig_dir)

    def test_permission_always_ask(self, runner: CliRunner):
        """permission --always-ask 添加规则。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(app, ["permission", "--always-ask", "web_fetch"])
                assert result.exit_code == 0
                assert "总是询问" in result.output
            finally:
                os.chdir(orig_dir)

    def test_permission_revoke(self, runner: CliRunner):
        """permission --revoke 撤销规则。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                runner.invoke(app, ["permission", "--allow", "bash"])
                result = runner.invoke(app, ["permission", "--revoke", "bash"])
                assert result.exit_code == 0
                assert "撤销" in result.output
            finally:
                os.chdir(orig_dir)

    def test_permission_show(self, runner: CliRunner):
        """permission --show 显示工具决策。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(app, ["permission", "--show", "bash"])
                assert result.exit_code == 0
                assert "bash" in result.output
            finally:
                os.chdir(orig_dir)


# ─── sessions 命令 ───────────────────────────────────────────────


class TestSessionsCommand:
    """agent-cli sessions 命令测试。"""

    def test_sessions_list_empty(self, runner: CliRunner):
        """sessions --list 无会话时显示空。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(app, ["sessions", "--list"])
                assert result.exit_code == 0
            finally:
                os.chdir(orig_dir)


# ─── plan 命令 ────────────────────────────────────────────────────


class TestPlanCommand:
    """agent-cli plan 命令测试。"""

    def test_plan_no_args_shows_usage(self, runner: CliRunner):
        """plan 无参数提示用法。"""
        result = runner.invoke(app, ["plan"])
        assert result.exit_code == 0

    def test_plan_list_empty(self, runner: CliRunner):
        """plan --list 无计划时显示空。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(app, ["plan", "--list"])
                assert result.exit_code == 0
            finally:
                os.chdir(orig_dir)


# ─── skill 命令 ──────────────────────────────────────────────────


class TestSkillCommand:
    """agent-cli skill 命令测试。"""

    def test_skill_list_empty(self, runner: CliRunner):
        """skill --list 无技能时显示空。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(app, ["skill", "--list"])
                assert result.exit_code == 0
                assert "暂无" in result.output or "0" in result.output
            finally:
                os.chdir(orig_dir)

    def test_skill_create_and_delete(self, runner: CliRunner):
        """技能创建与删除。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                # 创建
                result = runner.invoke(
                    app,
                    [
                        "skill",
                        "--name",
                        "test-skill",
                        "--desc",
                        "测试技能",
                        "--triggers",
                        "test,测试",
                        "--content",
                        "# 测试技能内容",
                    ],
                )
                assert result.exit_code == 0
                assert "创建" in result.output or "test-skill" in result.output

                # 确认文件存在
                assert Path(td, ".agent", "skills", "test-skill.md").exists()

                # 删除
                result = runner.invoke(app, ["skill", "--delete", "test-skill"])
                assert result.exit_code == 0
                assert "删除" in result.output
                assert not Path(td, ".agent", "skills", "test-skill.md").exists()
            finally:
                os.chdir(orig_dir)


# ─── mcp 命令 ────────────────────────────────────────────────────


class TestMCPCommand:
    """agent-cli mcp 命令测试。"""

    def test_mcp_status(self, runner: CliRunner):
        """mcp --status 显示状态。"""
        result = runner.invoke(app, ["mcp", "--status"])
        assert result.exit_code == 0

    def test_mcp_disconnect(self, runner: CliRunner):
        """mcp --disconnect 不报错。"""
        result = runner.invoke(app, ["mcp", "--disconnect"])
        assert result.exit_code == 0

    def test_mcp_list_no_connections(self, runner: CliRunner):
        """mcp --list 无连接时显示空。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(app, ["mcp", "--list"])
                assert result.exit_code == 0
            finally:
                os.chdir(orig_dir)


class TestMemoryCommand:
    """agent-cli memory 命令测试。"""

    def test_memory_list_empty(self, runner: CliRunner):
        """memory --list 无记忆时显示空。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(app, ["memory", "--list"])
                assert result.exit_code == 0
                assert "暂无" in result.output or "0 条" in result.output
            finally:
                os.chdir(orig_dir)

    def test_memory_write_and_show(self, runner: CliRunner):
        """记忆写入与读取。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                # 写入
                result = runner.invoke(
                    app,
                    [
                        "memory",
                        "--write",
                        "test-mem",
                        "--content",
                        "测试记忆内容",
                        "--desc",
                        "测试用记忆",
                    ],
                )
                assert result.exit_code == 0
                assert "写入" in result.output

                # 读取
                result = runner.invoke(app, ["memory", "--show", "test-mem"])
                assert result.exit_code == 0
                assert "测试记忆内容" in result.output

                # 搜索
                result = runner.invoke(app, ["memory", "--search", "测试"])
                assert result.exit_code == 0
                assert "test-mem" in result.output

                # 删除
                result = runner.invoke(app, ["memory", "--delete", "test-mem"])
                assert result.exit_code == 0
            finally:
                os.chdir(orig_dir)


# ─── run 命令 ──────────────────────────────────────────────────────


class TestRunCommand:
    """agent-cli run 命令测试（使用 MockProvider + 禁用日志文件）。"""

    @pytest.fixture(autouse=True)
    def _no_file_logging(self):
        """避免 _setup_logging 创建文件句柄导致 Windows 权限问题。"""
        with patch("agent_cli.main._setup_logging"):
            yield

    def test_run_mock_provider(self, runner: CliRunner):
        """--provider=mock 应正常执行。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(app, ["run", "你好", "--provider", "mock"])
                assert result.exit_code == 0
                assert len(result.output) > 0
            finally:
                os.chdir(orig_dir)

    def test_run_with_json(self, runner: CliRunner):
        """--json 输出模式。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(app, ["run", "hello", "--provider", "mock", "--json"])
                assert result.exit_code == 0
                assert len(result.output) > 0
            finally:
                os.chdir(orig_dir)

    def test_run_with_model_param(self, runner: CliRunner):
        """--model 参数传递。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(
                    app, ["run", "test", "--provider", "mock", "--model", "deepseek-chat"]
                )
                assert result.exit_code == 0
            finally:
                os.chdir(orig_dir)

    def test_run_with_provider_and_api_key(self, runner: CliRunner):
        """--api-key 参数传递给 compatible provider 不崩溃。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(
                    app,
                    [
                        "run",
                        "hello",
                        "--provider",
                        "compatible",
                        "--api-key",
                        "sk-test-key",
                        "--model",
                        "deepseek-chat",
                    ],
                )
                # 没有真实 key 时应该报错退出（exit_code=1），但不应崩溃
                assert result.exit_code in (0, 1)
            finally:
                os.chdir(orig_dir)

    def test_run_with_base_url(self, runner: CliRunner):
        """--base-url 参数传递。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(
                    app,
                    [
                        "run",
                        "test",
                        "--provider",
                        "compatible",
                        "--api-key",
                        "sk-test",
                        "--base-url",
                        "https://api.openai.com/v1",
                    ],
                )
                assert result.exit_code in (0, 1)
            finally:
                os.chdir(orig_dir)

    def test_run_with_max_iter(self, runner: CliRunner):
        """--max-iter 参数。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(app, ["run", "hi", "--provider", "mock", "--max-iter", "3"])
                assert result.exit_code == 0
            finally:
                os.chdir(orig_dir)

    def test_run_with_verbose(self, runner: CliRunner):
        """--verbose 输出模式。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(app, ["run", "hi", "--provider", "mock", "--verbose"])
                assert result.exit_code == 0
            finally:
                os.chdir(orig_dir)


# ─── swarm 命令 ────────────────────────────────────────────────────


class TestSwarmCommand:
    """agent-cli swarm 命令测试（使用 MockProvider + 禁用日志文件）。"""

    @pytest.fixture(autouse=True)
    def _no_file_logging(self):
        """避免 _setup_logging 创建文件句柄导致 Windows 权限问题。"""
        with patch("agent_cli.main._setup_logging"):
            yield

    def test_swarm_default_help(self, runner: CliRunner):
        """swarm 无参数显示帮助。"""
        result = runner.invoke(app, ["swarm"])
        assert result.exit_code == 0
        assert "Swarm" in result.output or "swarm" in result.output.lower()

    def test_swarm_sequential(self, runner: CliRunner):
        """--sequential 模式应正常执行。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(
                    app,
                    [
                        "swarm",
                        "--sequential",
                        "任务1\\n任务2",
                        "--provider",
                        "mock",
                        "--max-iter",
                        "2",
                    ],
                )
                assert result.exit_code == 0
            finally:
                os.chdir(orig_dir)

    def test_swarm_parallel(self, runner: CliRunner):
        """--parallel 模式应正常执行。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(
                    app,
                    [
                        "swarm",
                        "--parallel",
                        "任务A\\n任务B",
                        "--provider",
                        "mock",
                        "--max-iter",
                        "2",
                    ],
                )
                assert result.exit_code == 0
            finally:
                os.chdir(orig_dir)

    def test_swarm_vote(self, runner: CliRunner):
        """--vote 模式应正常执行。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(
                    app,
                    [
                        "swarm",
                        "--vote",
                        "这是测试问题吗？",
                        "--voters",
                        "2",
                        "--provider",
                        "mock",
                        "--max-iter",
                        "2",
                    ],
                )
                assert result.exit_code == 0
            finally:
                os.chdir(orig_dir)

    def test_swarm_debate(self, runner: CliRunner):
        """--debate 模式应正常执行。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(
                    app,
                    [
                        "swarm",
                        "--debate",
                        "测试辩论主题",
                        "--rounds",
                        "1",
                        "--provider",
                        "mock",
                        "--max-iter",
                        "2",
                    ],
                )
                assert result.exit_code == 0
            finally:
                os.chdir(orig_dir)

    def test_swarm_with_verbose(self, runner: CliRunner):
        """--verbose 输出模式。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(
                    app,
                    [
                        "swarm",
                        "--sequential",
                        "任务1\\n任务2",
                        "--verbose",
                        "--provider",
                        "mock",
                        "--max-iter",
                        "2",
                    ],
                )
                assert result.exit_code == 0
            finally:
                os.chdir(orig_dir)

    def test_swarm_with_provider_params(self, runner: CliRunner):
        """swarm 命令的 provider 参数传递。"""
        with tempfile.TemporaryDirectory() as td:
            orig_dir = os.getcwd()
            os.chdir(td)
            try:
                result = runner.invoke(
                    app,
                    [
                        "swarm",
                        "--vote",
                        "test?",
                        "--provider",
                        "mock",
                        "--api-key",
                        "sk-test",
                        "--base-url",
                        "https://api.deepseek.com/v1",
                        "--voters",
                        "2",
                        "--max-iter",
                        "2",
                    ],
                )
                assert result.exit_code == 0
            finally:
                os.chdir(orig_dir)
