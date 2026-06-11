"""REPL — 交互式对话模式。

提供类 Read-Eval-Print-Loop 的交互体验，
支持多轮对话、会话持久化、上下文压缩。
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from agent_cli.compact.pipeline import CompactPipeline
from agent_cli.core.loop import AgentLoop
from agent_cli.core.provider import IModelProvider
from agent_cli.memory.manager import MemoryManager
from agent_cli.session.store import SessionStore
from agent_cli.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class REPLExit(BaseException):
    """REPL 退出信号，用于测试中捕获而非直接 sys.exit。"""


class REPLMode:
    """REPL 交互模式。

    提供类 Read-Eval-Print-Loop 的交互体验。
    支持多轮对话、会话持久化、上下文压缩。

    Usage:
        repl = REPLMode(provider=provider, tools=registry)
        repl.run()
    """

    def __init__(
        self,
        provider: IModelProvider,
        tools: ToolRegistry,
        session_store: SessionStore | None = None,
        memory: MemoryManager | None = None,
        compact: CompactPipeline | None = None,
        max_iterations: int = 20,
        verbose: bool = False,
        resume_session: str | None = None,
        metrics: Any = None,
        alerts: Any = None,
    ):
        self.provider = provider
        self.tools = tools
        self.session_store = session_store
        self.memory = memory
        self.compact = compact
        self.max_iterations = max_iterations
        self.verbose = verbose
        self.metrics = metrics
        self.alerts = alerts
        self._history: list[dict] = []
        self._session_id: str | None = None
        self._resume_session = resume_session

    def run(self) -> None:
        """启动 REPL 交互循环。

        用户输入 → Agent 执行 → 输出结果 → 等待下一轮输入。
        输入 /exit、/quit 或 Ctrl+C 退出。
        输入 /help 查看命令帮助。
        输入 /save 保存当前会话。
        """
        print("Agent-CLI REPL 模式 (输入 /exit 退出, /help 查看帮助)")
        print("─" * 50)

        # 创建或恢复会话
        if self.session_store:
            if self._resume_session:
                stored = self.session_store.load(self._resume_session)
                if stored:
                    self._session_id = self._resume_session
                    self._history = stored
                    print(f"已恢复会话: {self._session_id} ({len(stored)} 条消息)")
                else:
                    print(f"会话不存在: {self._resume_session}，创建新会话")
                    self._session_id = self.session_store.create()
                    print(f"会话 ID: {self._session_id}")
            else:
                self._session_id = self.session_store.create()
                print(f"会话 ID: {self._session_id}")

        # 注入记忆上下文
        if self.memory:
            ctx = self.memory.build_context()
            if ctx:
                self._history.insert(
                    0,
                    {"role": "system", "content": f"[记忆上下文]\n{ctx[:1500]}"},
                )
                print("(已加载记忆上下文)")

        print("─" * 50)

        while True:
            try:
                user_input = input(">>> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                print("再见！")
                break

            if not user_input:
                continue

            # 处理内置命令
            if user_input.startswith("/"):
                try:
                    self._handle_command(user_input)
                except REPLExit:
                    break
                continue

            # 运行 Agent
            self._run_agent(user_input)

    def _handle_command(self, cmd: str) -> None:
        """处理 REPL 内置命令。"""
        cmd = cmd.lower().strip()

        if cmd in ("/exit", "/quit"):
            print("再见！")
            raise REPLExit()

        elif cmd in ("/help", "/?"):
            self._show_help()

        elif cmd == "/save":
            if self.session_store and self._session_id:
                self.session_store.append(self._session_id, self._history[-2:])
                print(f"会话已保存: {self._session_id}")
            else:
                print("未创建会话，无法保存。")

        elif cmd == "/clear":
            self._history.clear()
            print("对话历史已清空。")

        elif cmd == "/stats":
            if self.compact:
                stats = self.compact.get_stats()
                print(f"压缩触发: {stats['compression_count']} 次")
                print(f"最后一次压缩比: {stats['last_ratio']:.1%}")
            print(f"消息数: {len(self._history)}")
            if self.metrics:
                print(self.metrics.get_tool_summary())
            if self.alerts:
                summary = self.alerts.get_alerts_summary()
                if summary.strip() != "无告警记录。":
                    print(summary)

        elif cmd.startswith("/sessions") or cmd.startswith("/session"):
            if not self.session_store:
                print("会话存储未启用。")
                return
            parts = cmd.split(maxsplit=1)
            if len(parts) > 1:
                sub = parts[1]
                if sub == "--list" or sub == "-l":
                    self._list_sessions()
                elif sub.startswith("--search") or sub.startswith("-s"):
                    keyword = sub.split("=", 1)[1] if "=" in sub else ""
                    if keyword:
                        self._search_sessions(keyword)
                    else:
                        print("请指定搜索关键词: /sessions --search=关键词")
                else:
                    # 尝试作为会话 ID 查看
                    self._show_session(sub)
            else:
                self._list_sessions()

        elif cmd.startswith("/resume"):
            parts = cmd.split(maxsplit=1)
            if len(parts) > 1:
                session_id = parts[1]
                stored = self.session_store.load(session_id) if self.session_store else []
                if stored:
                    self._session_id = session_id
                    self._history = stored
                    print(f"已恢复会话: {session_id} ({len(stored)} 条消息)")
                else:
                    print(f"会话不存在: {session_id}")
            else:
                print("用法: /resume <session_id>")

        elif cmd.startswith("/memory"):
            if self.memory:
                entries = self.memory.file.list_all()
                if entries:
                    print(f"文件记忆 ({len(entries)} 条):")
                    for e in entries:
                        print(f"  [{e.name}] {e.description}")
                else:
                    print("暂无文件记忆。")
            else:
                print("记忆系统未启用。")

        elif cmd.startswith("/metrics"):
            if self.metrics:
                print(self.metrics.get_tool_summary())
            else:
                print("监控系统未启用。")

        elif cmd.startswith("/alerts"):
            if self.alerts:
                print(self.alerts.get_alerts_summary())
            else:
                print("告警系统未启用。")

        else:
            print(f"未知命令: {cmd} (输入 /help 查看可用命令)")

    def _list_sessions(self) -> None:
        """列出所有会话。"""
        if not self.session_store:
            return
        sessions = self.session_store.list_sessions()
        if not sessions:
            print("暂无会话记录。")
            return
        print(f"会话列表 ({len(sessions)} 个):\n")
        for s in sessions[:10]:
            marker = " ← 当前" if s["id"] == self._session_id else ""
            print(f"  {s['id']}{marker}")
            print(f"      创建: {s['created']}")
            print(f"      消息: {s['message_count']} 条")
            print(f"      大小: {s['size']} 字节\n")
        if len(sessions) > 10:
            print(f"  ... 还有 {len(sessions) - 10} 个会话\n")

    def _show_session(self, session_id: str) -> None:
        """显示指定会话内容。"""
        if not self.session_store:
            return
        msgs = self.session_store.load(session_id)
        if not msgs:
            print(f"会话 '{session_id}' 不存在或为空。")
            return
        print(f"会话: {session_id} ({len(msgs)} 条消息)\n")
        for i, msg in enumerate(msgs, 1):
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, list):
                types = [b.get("type", "?") for b in content if isinstance(b, dict)]
                content = f"[{', '.join(types)}]"
            text = str(content)[:150]
            print(f"  [{i}] {role}: {text}")

    def _search_sessions(self, keyword: str) -> None:
        """搜索会话内容。"""
        if not self.session_store:
            return
        matches = self.session_store.find_by_keyword(keyword)
        if not matches:
            print(f"未找到包含 '{keyword}' 的会话。")
            return
        print(f"搜索 '{keyword}' 找到 {len(matches)} 个会话:\n")
        for s in matches:
            print(f"  {s['id']}")
            print(f"      创建: {s['created']}")
            print(f"      消息: {s['message_count']} 条\n")

    def _show_help(self) -> None:
        """显示帮助信息。"""
        print("可用命令:")
        print("  /exit, /quit    退出 REPL")
        print("  /help, /?       显示此帮助")
        print("  /save           保存当前会话")
        print("  /clear          清空对话历史")
        print("  /stats          显示压缩/会话/监控统计")
        print("  /memory         列出文件记忆")
        print("  /sessions       列出所有会话")
        print("  /sessions -l    列出所有会话")
        print("  /sessions --search=关键词  搜索会话")
        print("  /sessions <id>  查看指定会话")
        print("  /resume <id>    恢复指定会话")
        print("  /metrics        显示工具调用指标")
        print("  /alerts         显示告警记录")
        print("")
        print("直接输入文本与 Agent 对话。")

    def _run_agent(self, user_input: str) -> None:
        """运行单次 Agent 交互。

        Args:
            user_input: 用户输入。
        """
        loop = AgentLoop(
            provider=self.provider,
            tools=self.tools,
            session_store=self.session_store,
            memory=self.memory,
            compact=self.compact,
            max_iterations=self.max_iterations,
        )

        try:
            response = loop.run(
                prompt=user_input,
                messages=list(self._history) if self._history else None,
                session_id=self._session_id,
            )

            # 显示结果
            print(response.text)

            if self.verbose:
                print(f"\n[迭代: {loop._iteration} | 工具: {len(response.tool_calls)}]")

            # 更新历史
            self._history = getattr(loop, "_session_messages", self._history)

        except Exception as e:
            error_msg = f"执行出错: {e}"
            logger.exception(error_msg)
            print(error_msg)
