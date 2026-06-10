"""SkillLoader — 技能加载器。

设计依据（规范 4.8）：
  - 扫描 .agent/skills/*.md，解析 YAML Frontmatter
  - 双模式触发：自动（上下文匹配）+ 手动（/skill 命令）
  - 通过 PRE_LOOP hook 注入匹配的技能提示

使用示例:
    loader = SkillLoader()
    loader.load_all()
    matching = loader.find_matching("如何使用 pytest？")
    for skill in matching:
        print(skill.content)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent_cli.skills.models import SkillSpec

logger = logging.getLogger(__name__)


class SkillLoader:
    """技能加载器。

    管理 .agent/skills/ 目录下的技能文件，按需加载和匹配。
    通过 HookManager 注册 PRE_LOOP 处理器实现自动注入。

    Usage:
        loader = SkillLoader()
        loader.load_all()
        # 自动匹配
        matched = loader.find_matching("如何写 Python 代码？")
        # 手动获取
        skill = loader.get_skill("python-dev")
    """

    def __init__(self, base_dir: str = ".agent"):
        self._skills_dir = Path(base_dir) / "skills"
        self._skills_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, SkillSpec] = {}

    # ── 加载 ────────────────────────────────────────────────────

    def load_all(self) -> list[SkillSpec]:
        """加载所有技能文件。

        扫描 .agent/skills/*.md，解析 YAML Frontmatter + Markdown 内容。
        结果缓存在内存中。

        Returns:
            加载的技能列表。
        """
        self._cache.clear()
        loaded: list[SkillSpec] = []

        for path in sorted(self._skills_dir.glob("*.md")):
            try:
                skill = self._load_file(path)
                self._cache[skill.name] = skill
                loaded.append(skill)
                logger.debug("加载技能: %s", skill.name)
            except Exception as e:
                logger.warning("跳过技能文件 %s: %s", path.name, e)

        logger.info("技能加载完成: %d 个", len(loaded))
        return loaded

    def _load_file(self, path: Path) -> SkillSpec:
        """加载单个技能文件。

        Args:
            path: .md 文件路径。

        Returns:
            SkillSpec 实例。

        Raises:
            ValueError: Frontmatter 解析失败。
        """
        text = path.read_text(encoding="utf-8")

        # 解析 YAML Frontmatter（--- 分隔）
        frontmatter: dict[str, Any] = {}
        body = text

        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                raw_yaml = parts[1].strip()
                frontmatter = self._parse_yaml(raw_yaml)
                body = parts[2].strip()

        name = frontmatter.get("name", path.stem)
        description = frontmatter.get("description", "")
        raw_triggers = frontmatter.get("triggers", [])

        # 支持 triggers 为字符串列表或逗号分隔
        if isinstance(raw_triggers, str):
            triggers = [t.strip() for t in raw_triggers.split(",") if t.strip()]
        elif isinstance(raw_triggers, list):
            triggers = [str(t) for t in raw_triggers]
        else:
            triggers = []

        return SkillSpec(
            name=str(name),
            description=str(description),
            triggers=triggers,
            content=body,
            source_file=str(path),
        )

    def _parse_yaml(self, raw: str) -> dict[str, Any]:
        """简易 YAML Frontmatter 解析器（无需 pyyaml 依赖）。

        支持: 字符串、列表、嵌套字典、布尔值。

        Args:
            raw: YAML 格式字符串。

        Returns:
            解析后的字典。
        """
        result: dict[str, Any] = {}
        current_list: list[str] | None = None

        for line in raw.split("\n"):
            stripped = line.strip()

            # 跳过空行和注释
            if not stripped or stripped.startswith("#"):
                continue

            # 列表项
            if stripped.startswith("- "):
                val = stripped[2:].strip().strip('"').strip("'")
                if current_list is not None:
                    current_list.append(val)
                continue

            current_list = None

            # 键值对
            if ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip()
                value = value.strip()

                if not value:
                    # 空值 → 开始列表
                    current_list = []
                    result[key] = current_list
                else:
                    result[key] = self._parse_yaml_value(value)

        return result

    def _parse_yaml_value(self, value: str) -> Any:
        """解析 YAML 标量值。"""
        # 引号字符串
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]

        # 布尔值
        if value.lower() in ("true", "yes", "on"):
            return True
        if value.lower() in ("false", "no", "off"):
            return False

        # 列表（方括号语法）
        if value.startswith("[") and value.endswith("]"):
            items = value[1:-1].split(",")
            return [item.strip().strip('"').strip("'") for item in items if item.strip()]

        # 数字
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        return value

    # ── 查询 ────────────────────────────────────────────────────

    def find_matching(self, text: str) -> list[SkillSpec]:
        """根据文本匹配技能触发器。

        双模式自动匹配的核心方法。
        将文本与每个技能的 triggers 列表对比。

        Args:
            text: 用户输入或上下文文本。

        Returns:
            匹配的技能列表（按触发词数量降序）。
        """
        if not text:
            return []

        matches = []
        text_lower = text.lower()

        for skill in self._cache.values():
            match_count = 0
            for trigger in skill.triggers:
                if trigger.lower() in text_lower:
                    match_count += 1
            if match_count > 0:
                matches.append((match_count, skill))

        # 按匹配度降序排列
        matches.sort(key=lambda x: x[0], reverse=True)
        return [skill for _, skill in matches]

    def get_skill(self, name: str) -> SkillSpec | None:
        """按名称获取技能。

        Args:
            name: 技能名称。

        Returns:
            SkillSpec 实例，不存在返回 None。
        """
        # 先检查缓存
        if name in self._cache:
            return self._cache[name]

        # 尝试从文件直接加载
        path = self._skills_dir / f"{name}.md"
        if path.exists():
            try:
                skill = self._load_file(path)
                self._cache[skill.name] = skill
                return skill
            except Exception as e:
                logger.warning("加载技能失败 %s: %s", name, e)

        return None

    def list_skills(self) -> list[SkillSpec]:
        """列出所有已加载的技能。"""
        return list(self._cache.values())

    def reload(self) -> list[SkillSpec]:
        """重新加载所有技能。"""
        return self.load_all()
