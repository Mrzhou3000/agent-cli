"""Tests for Phase 3 — Skill System."""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_cli.skills.loader import SkillLoader
from agent_cli.skills.models import SkillSpec

# ─── 辅助函数 ───────────────────────────────────────────────────


def _create_skill_file(base: Path, name: str, content: str) -> Path:
    """创建技能文件。"""
    skill_dir = base / ".agent" / "skills"
    skill_dir.mkdir(parents=True, exist_ok=True)
    path = skill_dir / f"{name}.md"
    path.write_text(content, encoding="utf-8")
    return path


# ─── SkillSpec 测试 ────────────────────────────────────────────


class TestSkillSpec:
    """SkillSpec 数据模型测试。"""

    def test_matches_with_triggers(self):
        """触发器应匹配输入文本。"""
        skill = SkillSpec(name="test", triggers=["python", "pytest"])
        assert skill.matches("如何使用 pytest？")
        assert skill.matches("Python 代码")
        assert not skill.matches("Rust 代码")

    def test_matches_case_insensitive(self):
        """触发器匹配应不区分大小写。"""
        skill = SkillSpec(name="test", triggers=["Python"])
        assert skill.matches("python 编程")
        assert skill.matches("PYTHON")

    def test_matches_empty_triggers(self):
        """空触发器列表应返回 False。"""
        skill = SkillSpec(name="test")
        assert not skill.matches("任何文本")

    def test_matches_empty_text(self):
        """空文本应返回 False。"""
        skill = SkillSpec(name="test", triggers=["python"])
        assert not skill.matches("")
        assert not skill.matches(None)  # type: ignore[arg-type]


# ─── SkillLoader 测试 ──────────────────────────────────────────


class TestSkillLoader:
    """SkillLoader 功能测试。"""

    @pytest.fixture
    def loader(self, tmp_path: Path) -> SkillLoader:
        """临时目录的 SkillLoader fixture。"""
        return SkillLoader(base_dir=str(tmp_path / ".agent"))

    def test_load_all_empty(self, loader: SkillLoader):
        """无技能文件时加载应返回空列表。"""
        skills = loader.load_all()
        assert skills == []

    def test_load_single_skill(self, tmp_path: Path, loader: SkillLoader):
        """加载单个技能文件。"""
        _create_skill_file(
            tmp_path,
            "python-dev",
            """---
name: python-dev
description: Python 开发最佳实践
triggers:
  - python
  - pytest
  - pip
---
# Python 开发准则

优先使用 Python 3.10+ 特性。
""",
        )
        skills = loader.load_all()
        assert len(skills) == 1
        skill = skills[0]
        assert skill.name == "python-dev"
        assert "pytest" in skill.triggers
        assert "Python 开发准则" in skill.content

    def test_load_multiple_skills(self, tmp_path: Path, loader: SkillLoader):
        """加载多个技能文件。"""
        _create_skill_file(
            tmp_path,
            "python-dev",
            """---
name: python-dev
triggers: [python]
---
Python content
""",
        )
        _create_skill_file(
            tmp_path,
            "git-dev",
            """---
name: git-dev
triggers: [git]
---
Git content
""",
        )
        skills = loader.load_all()
        assert len(skills) == 2

    def test_find_matching(self, tmp_path: Path, loader: SkillLoader):
        """find_matching 应正确匹配触发器。"""
        _create_skill_file(
            tmp_path,
            "python-dev",
            """---
name: python-dev
description: Python best practices
triggers:
  - python
  - pytest
---
Python content
""",
        )
        _create_skill_file(
            tmp_path,
            "web-dev",
            """---
name: web-dev
description: Web development
triggers:
  - html
  - css
  - javascript
---
Web content
""",
        )
        loader.load_all()

        # 匹配 python
        matched = loader.find_matching("如何使用 python 写测试？")
        assert len(matched) == 1
        assert matched[0].name == "python-dev"

        # 不匹配任何
        matched = loader.find_matching("今天天气怎么样")
        assert matched == []

    def test_find_matching_multiple_match(self, tmp_path: Path, loader: SkillLoader):
        """匹配多个技能时应按匹配度降序排列。"""
        _create_skill_file(
            tmp_path,
            "python-dev",
            """---
name: python-dev
triggers: [python, pytest, pip]
---
""",
        )
        _create_skill_file(
            tmp_path,
            "python-basic",
            """---
name: python-basic
triggers: [python]
---
""",
        )
        loader.load_all()

        matched = loader.find_matching("python 和 pytest")
        assert len(matched) == 2
        # python-dev 匹配 2 个词，应排前面
        assert matched[0].name == "python-dev"

    def test_get_skill_by_name(self, tmp_path: Path, loader: SkillLoader):
        """按名称获取技能。"""
        _create_skill_file(
            tmp_path,
            "my-skill",
            """---
name: my-skill
description: Test skill
---
Content here
""",
        )
        loader.load_all()

        skill = loader.get_skill("my-skill")
        assert skill is not None
        assert skill.description == "Test skill"

        skill = loader.get_skill("nonexistent")
        assert skill is None

    def test_reload(self, tmp_path: Path, loader: SkillLoader):
        """reload 应重新扫描所有技能文件。"""
        _create_skill_file(tmp_path, "skill-a", "---\nname: skill-a\n---\nA")
        loader.load_all()
        assert len(loader.list_skills()) == 1

        _create_skill_file(tmp_path, "skill-b", "---\nname: skill-b\n---\nB")
        loader.reload()
        assert len(loader.list_skills()) == 2

    def test_yaml_parser(self, loader: SkillLoader):
        """YAML 解析器应正确处理各种格式。"""
        parsed = loader._parse_yaml("""
name: test
description: A "quoted" string
triggers:
  - python
  - pytest
enabled: true
count: 42
""")
        assert parsed["name"] == "test"
        assert "quoted" in parsed["description"]
        assert parsed["triggers"] == ["python", "pytest"]
        assert parsed["enabled"] is True
        assert parsed["count"] == 42
