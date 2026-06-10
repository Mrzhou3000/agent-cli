"""Skill 系统数据模型。

设计依据（规范 4.8）：
  - Skill 格式: Markdown + YAML Frontmatter
  - 触发方式: 双模式（自动上下文匹配 + 手动 /skill 命令）
  - 核心哲学: "用到时再加载，别全塞 prompt 里"
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SkillSpec:
    """技能规范。

    Attributes:
        name: 技能名称（唯一标识）。
        description: 技能描述。
        triggers: 自动触发关键词列表。
        content: Markdown 格式的技能内容（注入 prompt 使用）。
        source_file: 来源文件路径。
    """

    name: str
    description: str = ""
    triggers: list[str] = field(default_factory=list)
    content: str = ""
    source_file: str = ""

    def matches(self, text: str) -> bool:
        """检查文本是否匹配任意触发器。

        Args:
            text: 要匹配的文本。

        Returns:
            匹配任意触发器返回 True。
        """
        if not self.triggers or not text:
            return False
        text_lower = text.lower()
        return any(trigger.lower() in text_lower for trigger in self.triggers)
