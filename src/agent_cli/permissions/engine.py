"""PermissionEngine — 权限引擎。

设计哲学（来源：claude-code-complete-guide_v2 + 14days-build）：
  四级决策链：Allow / Deny / Ask / Always。
  Phase 1 实现三级简化版（Allow / Deny / Ask），Always 在 Phase 4 加入。
  规则持久化到 .agent/permissions.json。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Decision = Literal["allow", "deny", "ask", "always_ask"]


class PermissionEngine:
    """权限引擎。

    根据规则和工具安全等级做出权限决策。
    支持规则持久化到 JSON 文件。

    Usage:
        engine = PermissionEngine()
        decision = engine.check("bash", "sensitive")  # → "ask"
        engine.allow("read")  # 永久允许 read 工具
    """

    def __init__(self, rules_file: str | None = None):
        self.rules_file = rules_file
        self._rules: dict[str, Decision] = {}
        self._load_rules()

    def _load_rules(self) -> None:
        """从文件加载持久化的规则。"""
        if not self.rules_file:
            return
        path = Path(self.rules_file)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._rules = data.get("rules", {})
                logger.debug("加载权限规则: %d 条", len(self._rules))
            except Exception as e:
                logger.warning("加载权限规则失败: %s", e)

    def _save_rules(self) -> None:
        """将规则持久化到文件。"""
        if not self.rules_file:
            return
        try:
            path = Path(self.rules_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"rules": self._rules}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("保存权限规则失败: %s", e)

    def check(self, tool_name: str, safety: str = "safe") -> Decision:
        """检查操作权限。

        决策优先级：
          1. 已有规则匹配 → 返回规则决策
          2. DANGEROUS → deny
          3. ALWAYS_ASK → ask
          4. SENSITIVE → ask
          5. SAFE → allow

        Args:
            tool_name: 工具名。
            safety: 安全等级字符串。

        Returns:
            "allow" | "deny" | "ask" | "always_ask"
        """
        # 1. 检查已有规则
        if tool_name in self._rules:
            return self._rules[tool_name]

        # 2. 根据安全等级决策
        safety_map: dict[str, Decision] = {
            "dangerous": "deny",
            "always_ask": "ask",
            "sensitive": "ask",
            "safe": "allow",
        }
        return safety_map.get(safety, "ask")

    def allow(self, tool_name: str) -> None:
        """永久允许某工具。"""
        self._rules[tool_name] = "allow"
        self._save_rules()
        logger.info("权限规则: 允许 '%s'", tool_name)

    def deny(self, tool_name: str) -> None:
        """永久拒绝某工具。"""
        self._rules[tool_name] = "deny"
        self._save_rules()
        logger.info("权限规则: 拒绝 '%s'", tool_name)

    def always_ask(self, tool_name: str) -> None:
        """设置某工具为总是询问。"""
        self._rules[tool_name] = "always_ask"
        self._save_rules()
        logger.info("权限规则: 总是询问 '%s'", tool_name)

    def set_rule(self, tool_name: str, decision: Decision) -> None:
        """设置任意规则。

        Args:
            tool_name: 工具名。
            decision: allow / deny / always_ask 之一。
                     （ask 是默认行为，不需要持久化规则）
        """
        if decision == "ask":
            self.revoke(tool_name)
            return
        self._rules[tool_name] = decision
        self._save_rules()
        logger.info("权限规则: %s '%s'", decision, tool_name)

    def revoke(self, tool_name: str) -> None:
        """撤销某工具的规则。"""
        self._rules.pop(tool_name, None)
        self._save_rules()

    def clear(self) -> None:
        """清除所有规则。"""
        self._rules.clear()
        self._save_rules()

    def get_rules(self) -> dict[str, Decision]:
        """获取当前所有规则。"""
        return dict(self._rules)

    def describe(self) -> str:
        """人类可读的规则描述。"""
        if not self._rules:
            return "当前无自定义权限规则。所有工具使用默认安全等级决策。\n"
        lines = ["当前权限规则:\n"]
        for name, decision in sorted(self._rules.items()):
            icon = {"allow": "✅", "deny": "❌", "always_ask": "❓"}.get(decision, "•")
            lines.append(f"  {icon} {name} → {decision}")
        lines.append("")
        return "\n".join(lines)

    def get_stats(self) -> dict:
        """获取权限引擎统计。"""
        decisions = {"allow": 0, "deny": 0, "always_ask": 0}
        for d in self._rules.values():
            if d in decisions:
                decisions[d] += 1
        return {
            "total_rules": len(self._rules),
            "decisions": decisions,
            "rules_file": self.rules_file,
        }
