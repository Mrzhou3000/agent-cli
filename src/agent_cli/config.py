"""配置管理 — 从 config.json 加载默认设置。

设计原则：
  - 配置文件位于 .agent/config.json
  - CLI 参数 > 环境变量 > 配置文件 > 默认值
  - 支持 provider、logging、retry 等配置项
  - init 命令自动创建默认配置
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = ".agent/config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "provider": {
        "default": "auto",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "max_tokens": 4096,
    },
    "logging": {
        "level": "WARNING",
        "format": "text",
        "file": ".agent/logs/agent-cli.log",
    },
    "retry": {
        "max_retries": 3,
        "base_delay": 1.0,
        "max_delay": 30.0,
    },
}


def get_config_path(path: str | None = None) -> str:
    """获取配置文件路径。"""
    return path or os.environ.get("AGENT_CLI_CONFIG") or DEFAULT_CONFIG_PATH


def load_config(path: str | None = None) -> dict[str, Any]:
    """从 JSON 文件加载配置。

    如果文件不存在或格式错误，返回默认配置。

    Args:
        path: 配置文件路径。默认使用 .agent/config.json。

    Returns:
        合并后的配置字典。
    """
    config_path = Path(get_config_path(path))
    if not config_path.exists():
        return {}

    try:
        raw = config_path.read_text(encoding="utf-8")
        user_config: dict = json.loads(raw)
        return user_config
    except (json.JSONDecodeError, OSError) as e:
        import logging

        logging.getLogger(__name__).warning("加载配置文件失败 %s: %s", config_path, e)
        return {}


def merge_config(
    cli_args: dict[str, Any],
    env_prefix: str = "",
) -> dict[str, Any]:
    """合并 CLI 参数、环境变量、配置文件。

    优先级（从高到低）：
      1. CLI 参数（显式传入的值）
      2. 环境变量
      3. 配置文件（.agent/config.json）
      4. 默认值

    Args:
        cli_args: CLI 参数字典（已解析的值）。
        env_prefix: 环境变量前缀（用于查找覆盖）。

    Returns:
        合并后的配置。
    """
    config = dict(DEFAULT_CONFIG)
    file_config = load_config()

    # 深度合并文件配置
    _deep_merge(config, file_config)

    # 环境变量覆盖
    provider_env = _get_env_provider(env_prefix)
    _deep_merge(config, provider_env)

    # CLI 参数覆盖（只覆盖非 None/非空的值）
    _deep_merge(config, cli_args)

    return config


def _deep_merge(base: dict, override: dict) -> None:
    """深度合并两个字典。"""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _get_env_provider(prefix: str = "") -> dict:
    """从环境变量读取 provider 配置。"""
    env: dict[str, Any] = {}
    api_key = os.environ.get(f"{prefix}COMPATIBLE_API_KEY") or os.environ.get("COMPATIBLE_API_KEY")
    anthro_key = os.environ.get(f"{prefix}ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

    if api_key or anthro_key:
        env["provider"] = {}
        if api_key:
            env["provider"]["api_key"] = api_key
        if anthro_key:
            env["provider"]["anthropic_key"] = anthro_key

    log_level = os.environ.get(f"{prefix}AGENT_CLI_LOG_LEVEL") or os.environ.get(
        "AGENT_CLI_LOG_LEVEL"
    )
    if log_level:
        env["logging"] = {"level": log_level}

    return env


def save_config(config: dict[str, Any], path: str | None = None) -> str:
    """保存配置到 JSON 文件。

    Args:
        config: 要保存的配置字典。
        path: 配置文件路径。默认使用 .agent/config.json。

    Returns:
        保存的配置文件路径。
    """
    from copy import deepcopy

    cfg_path = Path(get_config_path(path))
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    # 清理空值，避免写入 null
    cleaned = _clean_none(deepcopy(config))

    cfg_path.write_text(
        json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return str(cfg_path)


def _clean_none(d: dict[str, Any]) -> dict[str, Any]:
    """递归删除字典中的 None 值。"""
    result = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, dict):
            sub = _clean_none(v)
            if sub:
                result[k] = sub
        else:
            result[k] = v
    return result


def save_default_config(path: str | None = None) -> str:
    """保存默认配置文件。"""
    return save_config(DEFAULT_CONFIG, path=path)
