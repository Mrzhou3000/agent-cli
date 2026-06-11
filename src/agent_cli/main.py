"""CLI 入口 — Agent-CLI 命令行工具。

设计依据（模块 4.10）：
  - CLI 框架: Typer（来源：14days-build）
  - 交互模式: 命令行 + REPL（Phase 2 实现）
  - 输出分级: normal / verbose / json
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import typer
from typer import Argument, Option

from agent_cli import __version__
from agent_cli.compact.pipeline import CompactPipeline
from agent_cli.core.loop import AgentLoop
from agent_cli.core.provider import (
    AnthropicProvider,
    CompatibleProvider,
    IModelProvider,
    MockProvider,
)
from agent_cli.hooks.manager import PRE_LOOP, HookManager
from agent_cli.mcp.bridge import MCPToolBridge
from agent_cli.memory.manager import MemoryManager
from agent_cli.monitor.alerts import AlertManager
from agent_cli.monitor.metrics import MetricsCollector
from agent_cli.permissions.engine import PermissionEngine
from agent_cli.permissions.hook import PermissionHook
from agent_cli.planning.planner import TaskPlanner
from agent_cli.session.store import SessionStore
from agent_cli.skills.loader import SkillLoader
from agent_cli.subagent.manager import SubagentManager
from agent_cli.swarm.coordinator import Coordinator
from agent_cli.tools.agent_tool import AgentTool
from agent_cli.tools.bash import BashTool
from agent_cli.tools.file import EditTool, GlobTool, GrepTool, ReadTool, WriteTool
from agent_cli.tools.registry import ToolRegistry
from agent_cli.tools.web import WebFetchTool
from agent_cli.ui.renderer import format_result
from agent_cli.ui.repl import REPLMode

# ─── 日志配置 ────────────────────────────────────────────────────

_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


def _setup_logging(verbose: bool = False, log_dir: str = ".agent/logs") -> None:
    """配置日志。

    Args:
        verbose: 是否启用详细日志（DEBUG 级别）。
        log_dir: 日志文件目录。
    """
    level = logging.DEBUG if verbose else logging.WARNING
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    # 控制台日志
    logging.basicConfig(level=level, format=fmt, stream=sys.stderr)

    # 文件日志
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_path / "agent-cli.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(fmt))
    logging.getLogger("agent_cli").addHandler(fh)


# ─── 工具初始化 ────────────────────────────────────────────────────


def _create_registry(allowed_dir: str | None = None) -> ToolRegistry:
    """创建并注册所有内置工具。"""
    registry = ToolRegistry()
    registry.register(BashTool(allowed_dir=allowed_dir))
    registry.register(ReadTool(allowed_dir=allowed_dir))
    registry.register(WriteTool(allowed_dir=allowed_dir))
    registry.register(EditTool(allowed_dir=allowed_dir))
    registry.register(GlobTool(allowed_dir=allowed_dir))
    registry.register(GrepTool(allowed_dir=allowed_dir))
    registry.register(WebFetchTool())
    registry.register(AgentTool())
    return registry


def _create_provider(
    provider: str = "auto",
    model: str = "",
    api_key: str | None = None,
    base_url: str | None = None,
    max_tokens: int = 4096,
) -> IModelProvider:
    """根据参数和自动检测创建合适的 Provider。

    策略:
      auto      → 优先 ANTHROPIC_API_KEY → AnthropicProvider
                  其次 COMPATIBLE_API_KEY → CompatibleProvider
                  否则 → MockProvider
      anthropic → AnthropicProvider（需 ANTHROPIC_API_KEY）
      compatible → CompatibleProvider（需 COMPATIBLE_API_KEY 或 --api-key）
      mock      → MockProvider（不需要 API key）
    """
    ptype = provider.lower().strip()

    if ptype == "mock":
        return MockProvider()

    if ptype == "anthropic":
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        resolved_model = model or "claude-sonnet-4-20250514"
        return AnthropicProvider(api_key=key, model=resolved_model, max_tokens=max_tokens)

    if ptype == "compatible":
        key = api_key or os.environ.get("COMPATIBLE_API_KEY")
        resolved_model = model or "deepseek-chat"
        resolved_base = base_url or "https://api.deepseek.com/v1"
        return CompatibleProvider(
            base_url=resolved_base,
            api_key=key,
            model=resolved_model,
            max_tokens=max_tokens,
        )

    # auto: 自动检测环境变量
    anthropic_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    compatible_key = api_key or os.environ.get("COMPATIBLE_API_KEY")

    if anthropic_key:
        resolved_model = model or "claude-sonnet-4-20250514"
        return AnthropicProvider(api_key=anthropic_key, model=resolved_model, max_tokens=max_tokens)
    if compatible_key:
        resolved_model = model or "deepseek-chat"
        resolved_base = base_url or "https://api.deepseek.com/v1"
        return CompatibleProvider(
            base_url=resolved_base,
            api_key=compatible_key,
            model=resolved_model,
            max_tokens=max_tokens,
        )

    import logging

    logging.getLogger(__name__).info(
        "未检测到任何 API key，使用 MockProvider（仅测试用）"
    )
    return MockProvider()


# ─── Typer 应用 ────────────────────────────────────────────────────

app = typer.Typer(
    name="agent-cli",
    help="轻量级个人助手 Agent — 集三大开源项目设计思想之大成的融合实现",
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: bool = Option(False, "--version", "-V", help="显示版本信息"),
):
    """全局回调。"""
    if version:
        print(f"agent-cli v{__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        # 没有子命令时显示 help
        print(ctx.get_help())
        raise typer.Exit()


@app.command()
def run(
    prompt: str = Argument(..., help="用户指令"),
    model: str = Option("", "--model", "-m", help="模型名（auto→claude, comp→deepseek）"),
    verbose: bool = Option(False, "--verbose", "-v", help="详细输出模式"),
    json_output: bool = Option(False, "--json", "-j", help="JSON 输出模式"),
    provider_opt: str = Option("auto", "--provider", "-p", help="auto/anthropic/compatible/mock"),
    api_key: str | None = Option(None, "--api-key", "-k", help="API 密钥，覆盖环境变量"),
    base_url: str | None = Option(None, "--base-url", help="兼容 API 的基础 URL（如 https://api.deepseek.com/v1）"),
    resume: str | None = Option(None, "--resume", help="恢复会话 ID"),
    max_iterations: int = Option(20, "--max-iter", help="最大循环迭代次数"),
    allowed_dir: str | None = Option(None, "--dir", "-d", help="允许的工作目录"),
    memory: bool = Option(True, "--memory/--no-memory", help="启用/禁用三级记忆"),
    compact: bool = Option(True, "--compact/--no-compact", help="启用/禁用上下文压缩"),
    max_tokens: int = Option(100000, "--max-tokens", help="上下文窗口上限（Token 数）"),
):
    """执行一次 Agent 会话。

    接收用户指令，运行 Agent 循环，返回处理结果。
    支持工具调用、文件操作、命令执行等功能。
    """
    _setup_logging(verbose=verbose)

    # 输出模式
    output_mode = "json" if json_output else ("verbose" if verbose else "normal")

    # 工作目录
    work_dir = allowed_dir or os.getcwd()
    logger = logging.getLogger(__name__)
    logger.info("工作目录: %s", work_dir)

    # 初始化各组件
    registry = _create_registry(allowed_dir=work_dir)
    session_store = SessionStore(base_dir=".agent")
    mem_mgr = MemoryManager(base_dir=".agent") if memory else None
    compact_pipe = CompactPipeline(max_tokens=max_tokens) if compact else None

    # 创建 Provider（支持多模型切换）
    provider = _create_provider(
        provider=provider_opt,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

    # 会话管理
    session_id = session_store.create()

    # 恢复会话
    messages = None
    if resume:
        stored = session_store.load(resume)
        if stored:
            messages = stored
            session_id = resume
            print(format_result(f"恢复会话: {resume}", mode=output_mode))

    # 初始化监控（Phase 4）
    metrics = MetricsCollector()

    # 构建 Agent Loop
    loop = AgentLoop(
        provider=provider,
        tools=registry,
        session_store=session_store,
        memory=mem_mgr,
        compact=compact_pipe,
        max_iterations=max_iterations,
    )

    # 注册监控 Hook（Phase 4）
    from agent_cli.hooks.manager import POST_LOOP, POST_TOOL, PRE_TOOL

    loop.hooks.on(PRE_LOOP, metrics.on_pre_loop)
    loop.hooks.on(POST_TOOL, metrics.on_post_tool)
    loop.hooks.on(POST_LOOP, metrics.on_post_loop)

    # 权限 Hook — 在 PRE_TOOL 阶段检查权限（Phase 4）
    perm_hook = PermissionHook(PermissionEngine(rules_file=".agent/permissions.json"))
    loop.hooks.on(PRE_TOOL, perm_hook.check_tool)

    # 运行
    try:
        response = loop.run(prompt, messages=messages, session_id=session_id)
        output = format_result(
            response.text,
            iterations=loop._iteration,
            tool_calls=len(response.tool_calls),
            mode=output_mode,
        )
        print(output)

        # 更新项目记忆
        if mem_mgr:
            mem_mgr.project.append(
                "使用记录",
                f"{prompt[:60]}... ({session_id})",
            )
    except KeyboardInterrupt:
        print("\n\n[interrupt] 用户中断")
        sys.exit(130)
    except Exception as e:
        error_msg = f"运行失败: {e}"
        logging.getLogger(__name__).exception(error_msg)
        print(format_result(error_msg, mode=output_mode), file=sys.stderr)
        sys.exit(1)


@app.command()
def repl(
    verbose: bool = Option(False, "--verbose", "-v", help="详细输出模式"),
    model: str = Option("", "--model", "-m", help="模型名（auto→claude, comp→deepseek）"),
    provider_opt: str = Option("auto", "--provider", "-p", help="auto/anthropic/compatible/mock"),
    api_key: str | None = Option(None, "--api-key", "-k", help="API 密钥，覆盖环境变量"),
    base_url: str | None = Option(None, "--base-url", help="兼容 API 的基础 URL（如 https://api.deepseek.com/v1）"),
    allowed_dir: str | None = Option(None, "--dir", "-d", help="允许的工作目录"),
    memory: bool = Option(True, "--memory/--no-memory", help="启用/禁用三级记忆"),
    compact: bool = Option(True, "--compact/--no-compact", help="启用/禁用上下文压缩"),
    max_tokens: int = Option(100000, "--max-tokens", help="上下文窗口上限（Token 数）"),
    resume: str | None = Option(None, "--resume", help="恢复会话 ID"),
):
    """进入交互式 REPL 模式。

    多轮对话，支持会话持久化、记忆系统、上下文压缩。
    输入 /exit 退出，/help 查看命令帮助。
    """
    _setup_logging(verbose=verbose)
    work_dir = allowed_dir or os.getcwd()

    # 初始化组件
    registry = _create_registry(allowed_dir=work_dir)
    session_store = SessionStore(base_dir=".agent")
    mem_mgr = MemoryManager(base_dir=".agent") if memory else None
    compact_pipe = CompactPipeline(max_tokens=max_tokens) if compact else None
    metrics = MetricsCollector()
    alerts = AlertManager(metrics)

    provider = _create_provider(
        provider=provider_opt,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

    # 启动 REPL
    repl_session = REPLMode(
        provider=provider,
        tools=registry,
        session_store=session_store,
        memory=mem_mgr,
        compact=compact_pipe,
        verbose=verbose,
        resume_session=resume,
        metrics=metrics,
        alerts=alerts,
    )
    repl_session.run()


@app.command()
def init(
    force: bool = Option(False, "--force", "-f", help="强制覆盖已有配置"),
):
    """初始化当前目录的 .agent/ 配置。

    创建运行所需的数据目录结构和默认配置文件。
    """
    base = Path(".agent")
    dirs = ["memory", "sessions", "logs", "archives", "plans", "skills"]
    files = {
        "permissions.json": '{\n  "rules": {}\n}',
        "mcp.json": '{\n  "mcp_servers": []\n}',
        "project.md": "# 项目记忆\n\n> 自动由 Agent 维护的项目知识文档。\n",
    }

    for d in dirs:
        (base / d).mkdir(parents=True, exist_ok=True)

    for name, content in files.items():
        path = base / name
        if path.exists() and not force:
            print(f"  [skip] 已存在: {path} (使用 --force 覆盖)")
        else:
            path.write_text(content, encoding="utf-8")
            print(f"  [ok] 创建: {path}")

    print("\n[ok] .agent/ 初始化完成！")
    print("   目录结构:")
    for d in dirs:
        print(f"     .agent/{d}/")
    for name in files:
        print(f"     .agent/{name}")


@app.command()
def sessions(
    list_sessions: bool = Option(False, "--list", "-l", help="列出所有会话"),
    show: str | None = Option(None, "--show", help="显示指定会话内容"),
    delete: str | None = Option(None, "--delete", help="删除指定会话"),
    archive: str | None = Option(None, "--archive", help="归档指定会话"),
):
    """管理会话记录。"""
    store = SessionStore(base_dir=".agent")

    if list_sessions or (not show and not delete and not archive):
        sessions_list = store.list_sessions()
        if not sessions_list:
            print("暂无会话记录。")
            return
        print(f"共 {len(sessions_list)} 个会话:\n")
        for s in sessions_list:
            print(f"  [file] {s['id']}")
            print(f"      创建: {s['created']}")
            print(f"      消息: {s['message_count']} 条")
            print(f"      大小: {s['size']} 字节\n")
        return

    if show:
        msgs = store.load(show)
        if not msgs:
            print(f"会话 '{show}' 不存在或为空。")
            return
        for i, msg in enumerate(msgs, 1):
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = str(content)
            print(f"  [{i}] {role}: {content[:200]}")

    if delete:
        if store.delete(delete):
            print(f"已删除会话: {delete}")
        else:
            print(f"会话不存在: {delete}")

    if archive:
        if store.archive(archive):
            print(f"已归档会话: {archive}")
        else:
            print(f"会话不存在: {archive}")


@app.command()
def memory(
    list_memories: bool = Option(False, "--list", "-l", help="列出所有记忆"),
    show: str | None = Option(None, "--show", help="显示指定记忆"),
    write: str | None = Option(None, "--write", help="写入记忆的名称"),
    content: str | None = Option(None, "--content", "-c", help="记忆内容"),
    description: str = Option("", "--desc", help="记忆描述"),
    delete: str | None = Option(None, "--delete", help="删除指定记忆"),
    search: str | None = Option(None, "--search", "-s", help="搜索记忆"),
):
    """管理 Agent 的文件级记忆。

    记忆以 Markdown + YAML Frontmatter 格式存储在 .agent/memory/。
    """
    mgr = MemoryManager(base_dir=".agent")

    if write and content:
        path = mgr.write_note(name=write, content=content, description=description)
        print(f"已写入记忆: {path}")
        return

    if show:
        entry = mgr.read_note(show)
        if entry:
            print(f"名称: {entry.name}")
            print(f"描述: {entry.description}")
            print(f"标签: {entry.tags}")
            print(f"---\n{entry.content}")
        else:
            print(f"记忆 '{show}' 不存在。")
        return

    if delete:
        from agent_cli.memory.file_memory import FileMemory

        fm = FileMemory(base_dir=".agent")
        if fm.delete(delete):
            print(f"已删除记忆: {delete}")
        else:
            print(f"记忆 '{delete}' 不存在。")
        return

    if search:
        entries = mgr.search(query=search)
        if entries:
            print(f"搜索 '{search}' 找到 {len(entries)} 条:\n")
            for e in entries:
                print(f"  [{e.name}] {e.description}")
                print(f"    {e.content[:100]}...\n")
        else:
            print(f"未找到匹配 '{search}' 的记忆。")
        return

    # 默认：列出所有
    entries = mgr.file.list_all()
    if not entries:
        print("暂无文件级记忆。使用 --write 创建新记忆。")
        return
    print(f"文件级记忆 ({len(entries)} 条):\n")
    for e in entries:
        tags = f" tags: {','.join(e.tags)}" if e.tags else ""
        print(f"  [{e.name}] {e.description}{tags}")
        print(f"    {e.content[:120]}...\n")


# ─── Phase 3: 技能自动注入 Hook ─────────────────────────────────


def _build_skill_hook(base_dir: str = ".agent") -> HookManager | None:
    """创建带技能自动注入的 HookManager。

    在 PRE_LOOP 阶段检测用户输入，自动注入匹配的技能内容。

    Args:
        base_dir: .agent 目录路径。

    Returns:
        配置好的 HookManager，或 None（无技能文件时）。
    """
    loader = SkillLoader(base_dir=base_dir)
    skills = loader.load_all()
    if not skills:
        return None

    hooks = HookManager()

    def inject_skills(messages: list[dict]) -> None:
        """PRE_LOOP handler: 自动注入匹配的技能。"""
        if not messages:
            return
        # 从最近的 user 消息提取关键词
        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                user_text = content if isinstance(content, str) else ""
                break

        if not user_text:
            return

        matched = loader.find_matching(user_text)
        if matched:
            skill_texts = []
            for skill in matched[:3]:  # 最多注入 3 个
                skill_texts.append(f"## 技能: {skill.name}\n{skill.description}\n{skill.content}")
            inject = "\n\n---\n".join(skill_texts)
            messages.insert(0, {"role": "system", "content": f"[匹配技能]\n{inject[:2000]}"})

    hooks.on(PRE_LOOP, inject_skills)
    return hooks


# ─── Phase 3 CLI 命令 ──────────────────────────────────────────


@app.command()
def plan(
    prompt: str | None = Argument(None, help="自然语言任务描述（可选，也可用 --tasks JSON）"),
    tasks: str | None = Option(
        None, "--tasks", "-t", help='JSON 格式任务列表: [{"id":"t1","title":"..."}]'
    ),
    show: bool = Option(False, "--show", "-s", help="显示当前计划"),
    approve: bool = Option(False, "--approve", "-a", help="审批通过当前计划"),
    next_task: bool = Option(False, "--next", "-n", help="显示下一个可执行任务"),
    summarize: bool = Option(False, "--summary", "-m", help="显示执行总结"),
    list_plans: bool = Option(False, "--list", "-l", help="列出所有计划"),
    plan_id: str | None = Option(None, "--plan", "-p", help="指定计划 ID"),
):
    """任务规划与审批闭环。

    支持从自然语言或 JSON 创建任务计划，含审批流程和依赖管理。
    """
    planner = TaskPlanner()

    if list_plans:
        plans = planner.list_plans()
        if not plans:
            print("暂无计划。")
            return
        print(f"共 {len(plans)} 个计划:\n")
        for p in plans:
            statuses = ", ".join(sorted(p["statuses"])) if p["statuses"] else "N/A"
            print(f"  [file] {p['plan_id']}")
            print(f"      创建: {p['created_at']}")
            print(f"      任务: {p['task_count']} 个")
            print(f"      状态: {statuses}\n")
        return

    if show:
        plan_obj = planner.current_plan
        if plan_id:
            plan_obj = planner._load(plan_id)
        print(planner.show_plan(plan_obj))
        return

    if approve:
        if planner.approve_plan(plan_id):
            print("计划已审批通过！")
        else:
            print("审批失败：计划不存在。")
        return

    if next_task:
        tasks = planner.get_next_tasks(plan_id)
        if tasks:
            print("可执行任务:")
            for t in tasks:
                print(f"  [file] {t.id}: {t.title}")
        else:
            print("当前无可执行任务（等待审批或依赖未完成）。")
        return

    if summarize:
        print(planner.summarize(plan_id))
        return

    # 默认：从 prompt 或 tasks 创建计划
    if not prompt and not tasks:
        print("请提供任务描述（prompt）或 --tasks JSON。使用 --help 查看帮助。")
        return

    if tasks:
        import json

        try:
            task_list = json.loads(tasks)
            planner.create_plan(task_list)
        except json.JSONDecodeError as e:
            print(f"JSON 解析错误: {e}")
            return
    elif prompt:
        # 简易解析：从自然语言提取任务
        lines = [ln.strip() for ln in prompt.strip().split("\n") if ln.strip()]
        task_list = []
        for i, line in enumerate(lines):
            if line.startswith("- ") or line.startswith("* "):
                line = line[2:]
            task_list.append({"id": f"t{i + 1}", "title": line, "description": line})
        planner.create_plan(task_list)

    print(planner.show_plan())
    print("\n使用 --approve 审批通过后执行。")


@app.command()
def skill(
    list_skills: bool = Option(False, "--list", "-l", help="列出所有技能"),
    show: str | None = Option(None, "--show", help="显示指定技能内容"),
    name: str | None = Option(None, "--name", "-n", help="技能名称"),
    content: str | None = Option(None, "--content", "-c", help="技能内容（Markdown）"),
    description: str = Option("", "--desc", help="技能描述"),
    triggers: str = Option("", "--triggers", "-t", help="触发关键词（逗号分隔）"),
    delete: str | None = Option(None, "--delete", help="删除指定技能"),
):
    """管理技能系统（双模式触发）。

    技能以 Markdown + YAML Frontmatter 格式存储在 .agent/skills/。
    自动匹配用户输入中的 trigger 关键词。
    """
    loader = SkillLoader()

    if list_skills:
        loader.load_all()
        skills = loader.list_skills()
        if not skills:
            print("暂无技能。使用 --name 和 --content 创建新技能。")
            return
        print(f"技能列表 ({len(skills)} 个):\n")
        for s in skills:
            triggers_str = ", ".join(s.triggers[:5]) if s.triggers else "无"
            print(f"  [file] {s.name}")
            print(f"      描述: {s.description}")
            print(f"      触发: {triggers_str}\n")
        return

    if show:
        loader.load_all()
        skill = loader.get_skill(show)
        if skill:
            print(f"名称: {skill.name}")
            print(f"描述: {skill.description}")
            print(f"触发: {skill.triggers}")
            print(f"---\n{skill.content}")
        else:
            print(f"技能 '{show}' 不存在。")
        return

    if delete:
        path = Path(".agent") / "skills" / f"{delete}.md"
        if path.exists():
            path.unlink()
            print(f"已删除技能: {delete}")
        else:
            print(f"技能 '{delete}' 不存在。")
        return

    # 创建技能
    if not name:
        print("请提供 --name。使用 --help 查看帮助。")
        return

    skill_content = content or f"# {name}\n\n{description}"

    # 构建 triggers YAML 列表
    trigger_items = ""
    if triggers:
        trigger_items = "\n" + "\n".join(
            f"  - {t.strip()}" for t in triggers.split(",") if t.strip()
        )

    frontmatter = f"""---
name: {name}
description: {description}
triggers:{trigger_items}
---
"""
    skill_dir = Path(".agent") / "skills"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / f"{name}.md"
    skill_file.write_text(frontmatter + "\n" + skill_content, encoding="utf-8")
    print(f"技能已创建: {skill_file}")


@app.command()
def mcp(
    connect: bool = Option(False, "--connect", "-c", help="连接到配置的所有 MCP 服务器"),
    list_tools: bool = Option(False, "--list", "-l", help="列出已发现的工具"),
    status: bool = Option(False, "--status", "-s", help="显示 MCP 连接状态"),
    disconnect: bool = Option(False, "--disconnect", "-d", help="断开所有 MCP 连接"),
):
    """管理 MCP 外部工具桥接。

    从 .agent/mcp.json 加载配置，连接外部工具服务器。
    """
    bridge = MCPToolBridge()

    if connect:
        bridge.load_config()
        connected = bridge.connect_all()
        if connected:
            tools = bridge.discover_tools()
            print(f"MCP 已连接: {', '.join(connected)}")
            print(f"发现工具: {len(tools)} 个")
        else:
            print("未连接到任何 MCP 服务器。请检查 .agent/mcp.json 配置。")
        return

    if list_tools:
        bridge.load_config()
        bridge.connect_all()
        tools = bridge.discover_tools()
        if tools:
            print(f"MCP 工具 ({len(tools)} 个):\n")
            for t in tools:
                print(f"  [file] {t.name}")
                print(f"      源: {t.server_name}")
                print(f"      描述: {t.description[:100]}\n")
        else:
            print("未发现 MCP 工具。")
        return

    if status:
        bridge.load_config()
        print("MCP Bridge — 外部工具协议")
        print("使用 --connect 连接到 MCP 服务器。")
        return

    if disconnect:
        bridge.disconnect_all()
        print("MCP 连接已断开。")
        return

    # 默认显示帮助
    print("MCP Bridge — 外部工具协议\n")
    print("用法:")
    print("  agent-cli mcp --connect     连接到 MCP 服务器")
    print("  agent-cli mcp --list        列出发现的工具")
    print("  agent-cli mcp --status      显示连接状态")
    print("  agent-cli mcp --disconnect  断开连接")


# ─── Phase 4 CLI 命令 ──────────────────────────────────────────


@app.command()
def permission(
    list_rules: bool = Option(False, "--list", "-l", help="列出所有权限规则"),
    allow: str | None = Option(None, "--allow", help="永久允许某工具"),
    deny: str | None = Option(None, "--deny", help="永久拒绝某工具"),
    always_ask: str | None = Option(None, "--always-ask", help="设置某工具为总是询问"),
    revoke: str | None = Option(None, "--revoke", help="撤销某工具的规则"),
    clear: bool = Option(False, "--clear", help="清除所有规则"),
    show: str | None = Option(None, "--show", help="显示某工具的当前决策"),
    status: bool = Option(False, "--status", "-s", help="显示权限引擎状态"),
    rules_file: str = Option(".agent/permissions.json", "--rules-file", help="规则文件路径"),
):
    """管理工具权限规则（四级权限：Allow/Deny/Ask/Always_Ask）。

    权限决策优先级:
      1. 自定义规则 (allow/deny/always_ask)
      2. 工具安全等级 (safe → allow / sensitive → ask / dangerous → deny / always_ask → ask)
      3. 默认 → ask
    """
    engine = PermissionEngine(rules_file=rules_file)

    if list_rules:
        print(engine.describe())
        return

    if allow:
        engine.allow(allow)
        print(f"已永久允许: {allow}")
        return

    if deny:
        engine.deny(deny)
        print(f"已永久拒绝: {deny}")
        return

    if always_ask:
        engine.always_ask(always_ask)
        print(f"已设为总是询问: {always_ask}")
        return

    if revoke:
        engine.revoke(revoke)
        print(f"已撤销规则: {revoke}")
        return

    if clear:
        engine.clear()
        print("已清除所有规则。")
        return

    if show:
        # 尝试推断安全等级
        safety = "safe"
        dangerous_tools = {"bash", "write", "edit"}
        always_ask_tools = {"web_fetch", "agent"}
        if show in dangerous_tools:
            safety = "sensitive"
        elif show in always_ask_tools:
            safety = "always_ask"
        decision = engine.check(show, safety)
        print(f"工具 '{show}' 的当前决策: {decision}")
        if show in engine.get_rules():
            print(f"  (自定义规则: {engine.get_rules()[show]})")
        else:
            print(f"  (默认决策，基于安全等级: {safety})")
        return

    if status:
        stats = engine.get_stats()
        print("权限引擎状态:\n")
        print(f"  规则文件: {stats['rules_file'] or '无'}")
        print(f"  自定义规则: {stats['total_rules']} 条")
        for decision, count in stats["decisions"].items():
            if count > 0:
                print(f"    {decision}: {count} 条")
        print()
        print(engine.describe())
        return

    # 默认显示所有规则
    print(engine.describe())
    print("使用 --help 查看完整用法。")


@app.command()
def swarm(
    sequential: str | None = Option(
        None,
        "--sequential",
        "-s",
        help="顺序执行（多行任务用 \\n 分隔）",
    ),
    parallel: str | None = Option(
        None,
        "--parallel",
        "-p",
        help="并行执行（多行任务用 \\n 分隔）",
    ),
    vote: str | None = Option(None, "--vote", "-v", help="投票问题"),
    voters: int = Option(3, "--voters", help="投票者数量（默认 3）"),
    debate: str | None = Option(None, "--debate", "-d", help="辩论主题"),
    rounds: int = Option(2, "--rounds", "-r", help="辩论轮数（默认 2）"),
    verbose: bool = Option(False, "--verbose", "-V", help="显示详细结果"),
    max_iterations: int = Option(5, "--max-iter", help="每个 Worker 最大迭代次数"),
    model: str = Option("", "--model", "-m", help="模型名（auto→claude, comp→deepseek）"),
    provider_opt: str = Option("auto", "--provider", "-p", help="auto/anthropic/compatible/mock"),
    api_key: str | None = Option(None, "--api-key", "-k", help="API 密钥，覆盖环境变量"),
    base_url: str | None = Option(None, "--base-url", help="兼容 API 的基础 URL（如 https://api.deepseek.com/v1）"),
):
    """多 Agent 协作模式。

    支持四种编排模式：
      - 顺序 (--sequential): 任务依次执行，结果传递
      - 并行 (--parallel): 所有任务同时执行
      - 投票 (--vote): 多个 Agent 独立回答并投票
      - 辩论 (--debate): 正反双方多轮辩论
    """
    # 创建最小运行时
    registry = _create_registry()
    provider = _create_provider(
        provider=provider_opt,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

    loop = AgentLoop(
        provider=provider,
        tools=registry,
        max_iterations=max_iterations,
    )
    sub_mgr = SubagentManager(loop, max_iterations=max_iterations)
    coord = Coordinator(sub_mgr)

    if sequential:
        tasks = [t.strip() for t in sequential.split("\\n") if t.strip()]
        print(f"🔄 顺序执行: {len(tasks)} 个任务\n")
        result = coord.sequential(tasks)
        _print_swarm_result(result, verbose)
        return

    if parallel:
        tasks = [t.strip() for t in parallel.split("\\n") if t.strip()]
        print(f"⚡ 并行执行: {len(tasks)} 个任务\n")
        result = coord.parallel(tasks)
        _print_swarm_result(result, verbose)
        return

    if vote:
        print(f"🗳️  投票模式: {voters} 位投票者\n")
        print(f"问题: {vote}\n")
        vote_result = coord.vote(vote, voters=voters)
        print(f"结果: {vote_result.agreement} 同意 / {vote_result.disagreement} 反对")
        print(f"共识: {'✅ 达成' if vote_result.consensus else '❌ 未达成'}")
        if verbose:
            print("\n详细投票:")
            for i, v in enumerate(vote_result.votes, 1):
                status = "✅" if v["success"] else "❌"
                print(f"\n  [{i}] {status}")
                print(f"      {v['agent_output'][:200]}")
        return

    if debate:
        print(f"🎭 辩论模式: {rounds} 轮\n")
        print(f"主题: {debate}\n")
        result = coord.debate(debate, rounds=rounds)
        print(result.summary)
        return

    # 默认
    print("Swarm — 多 Agent 协作系统\n")
    print("用法:")
    print('  agent-cli swarm --sequential "任务1\\n任务2\\n任务3"  顺序执行')
    print('  agent-cli swarm --parallel "任务1\\n任务2"            并行执行')
    print('  agent-cli swarm --vote "这个方案好吗？"              投票')
    print('  agent-cli swarm --debate "微服务还是单体？"          辩论')
    print("\n使用 --help 查看完整用法。")


def _print_swarm_result(result: Any, verbose: bool = False) -> None:
    """打印 Swarm 执行结果。"""
    print(f"模式: {result.pattern}")
    print(f"耗时: {result.duration:.2f}s")
    print(f"成功: {result.success_count}/{len(result.results)}")
    print()

    if verbose:
        for i, r in enumerate(result.results, 1):
            status = "✅" if r.success else "❌"
            print(f"[{i}] {r.task[:60]} {status}")
            if r.success:
                print(f"    {r.output[:300]}")
            else:
                print(f"    ❌ {r.error}")
            print()
    else:
        print(result.summary[:500])


if __name__ == "__main__":
    app()
