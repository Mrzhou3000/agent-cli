"""配置管理模块测试。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from agent_cli.config import (
    _deep_merge,
    _get_env_provider,
    load_config,
    merge_config,
    save_default_config,
)


class TestLoadConfig:
    """load_config 测试。"""

    def test_config_file_not_found(self):
        """配置文件不存在返回空字典。"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "nonexistent.json"
            config = load_config(str(path))
            assert config == {}

    def test_load_valid_config(self):
        """加载有效配置文件。"""
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.json"
            cfg_path.write_text(
                json.dumps({"provider": {"default": "mock", "model": "test-model"}}, indent=2),
                encoding="utf-8",
            )
            config = load_config(str(cfg_path))
            assert config["provider"]["default"] == "mock"
            assert config["provider"]["model"] == "test-model"

    def test_load_corrupt_config(self):
        """损坏的配置文件返回空字典。"""
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.json"
            cfg_path.write_text("not valid json", encoding="utf-8")
            config = load_config(str(cfg_path))
            assert config == {}


class TestMergeConfig:
    """merge_config 优先级测试。"""

    def test_cli_overrides_file(self):
        """CLI 参数优先于配置文件。"""
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {}, clear=True):
            cfg_path = Path(td) / "config.json"
            cfg_path.write_text(
                json.dumps({"provider": {"model": "from-file"}}, indent=2),
                encoding="utf-8",
            )
            # 模拟 load_config
            with patch("agent_cli.config.get_config_path", return_value=str(cfg_path)):
                merged = merge_config({"provider": {"model": "from-cli"}})
                assert merged["provider"]["model"] == "from-cli"

    def test_file_overrides_default(self):
        """配置文件优先于默认值。"""
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {}, clear=True):
            cfg_path = Path(td) / "config.json"
            cfg_path.write_text(
                json.dumps({"logging": {"level": "DEBUG"}}, indent=2),
                encoding="utf-8",
            )
            with patch("agent_cli.config.get_config_path", return_value=str(cfg_path)):
                merged = merge_config({})
                assert merged["logging"]["level"] == "DEBUG"
                # 未覆盖的默认值保持不变
                assert merged["logging"]["format"] == "text"


class TestSaveDefaultConfig:
    """save_default_config 测试。"""

    def test_saves_valid_json(self):
        """保存的配置文件是有效 JSON 且包含所有默认字段。"""
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / ".agent" / "config.json"
            saved = save_default_config(str(cfg_path))
            assert Path(saved).exists()
            data = json.loads(Path(saved).read_text(encoding="utf-8"))
            assert "provider" in data
            assert "logging" in data
            assert "retry" in data
            assert data["provider"]["default"] == "auto"
            assert data["logging"]["format"] == "text"
            assert data["retry"]["max_retries"] == 3


class TestDeepMerge:
    """_deep_merge 测试。"""

    def test_simple_merge(self):
        """简单值覆盖。"""
        base = {"a": 1, "b": 2}
        _deep_merge(base, {"a": 10, "c": 3})
        assert base == {"a": 10, "b": 2, "c": 3}

    def test_nested_merge(self):
        """嵌套字典深度合并。"""
        base = {"outer": {"inner": 1, "other": 2}}
        _deep_merge(base, {"outer": {"inner": 99}})
        assert base == {"outer": {"inner": 99, "other": 2}}

    def test_empty_override(self):
        """空覆盖不改变原字典。"""
        base = {"a": 1}
        _deep_merge(base, {})
        assert base == {"a": 1}


class TestGetEnvProvider:
    """_get_env_provider 测试。"""

    def test_no_env_vars(self):
        """无环境变量返回空字典。"""
        with patch.dict(os.environ, {}, clear=True):
            result = _get_env_provider()
            assert result == {}

    def test_compatible_key_env(self):
        """COMPATIBLE_API_KEY 环境变量被读取。"""
        with patch.dict(os.environ, {"COMPATIBLE_API_KEY": "sk-test"}):
            result = _get_env_provider()
            assert result["provider"]["api_key"] == "sk-test"

    def test_anthropic_key_env(self):
        """ANTHROPIC_API_KEY 环境变量被读取。"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            result = _get_env_provider()
            assert result["provider"]["anthropic_key"] == "sk-ant-test"

    def test_log_level_env(self):
        """AGENT_CLI_LOG_LEVEL 环境变量被读取。"""
        with patch.dict(os.environ, {"AGENT_CLI_LOG_LEVEL": "DEBUG"}):
            result = _get_env_provider()
            assert result["logging"]["level"] == "DEBUG"

    def test_prefix_env(self):
        """带前缀的环境变量。"""
        with patch.dict(os.environ, {"COMPATIBLE_API_KEY": "sk-prefix-test"}):
            result = _get_env_provider("MY_")
            assert result["provider"]["api_key"] == "sk-prefix-test"
