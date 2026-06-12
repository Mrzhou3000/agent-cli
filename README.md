# Agent-CLI — 轻量级个人助手

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue)]()
[![PyPI version](https://img.shields.io/pypi/v/agent-cli-Mrzhou300)]()
[![Ruff](https://img.shields.io/badge/code%20style-ruff-000000)]()
[![License MIT](https://img.shields.io/badge/license-MIT-green)]()
[![Tests](https://img.shields.io/badge/tests-668%20passing-brightgreen)]()
[![CI](https://github.com/Mrzhou3000/agent-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/Mrzhou3000/agent-cli/actions/workflows/ci.yml)

> 集三大开源项目设计思想之大成的轻量级个人助手 Agent。
> 融合 [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)、[14days-build-claude-code-cli](https://github.com/bozhouDev/14days-build-claude-code-cli)、[claude-code-complete-guide_v2](https://github.com/bcefghj/claude-code-complete-guide_v2) 的设计精华。

---

## ✨ 特性

| 层次 | 特性 | 说明 |
|:----|:-----|:------|
| **核心** | 极简 Agent Loop | ~60 行核心循环，所有复杂机制挂在循环上 |
| **模型** | 多 Provider | MockProvider(测试) / Anthropic(Claude) / Compatible(DeepSeek等) |
| **工具** | 8+ 内置工具 | Bash / Read / Write / Edit / Glob / Grep / WebFetch / Agent |
| **权限** | 四级安全 | Allow ✅ / Deny ❌ / Ask ❓ / Always_Ask ⚠️ — 可持久化规则 |
| **记忆** | 三级架构 | 文件级(长期) + 会话级(短期) + 项目级(全局) |
| **上下文** | 四层压缩 | L1-L4 渐进管理，前三层零 API 成本 |
| **任务** | 审批闭环 | TodoItem 状态机 + 拓扑排序依赖 + JSON 持久化 |
| **技能** | 双模式触发 | 自动上下文匹配 + 手动 `/skill` 命令 |
| **多Agent** | 4种编排模式 | 顺序 / 并行 / 投票 / 辩论 — Coordinator 模式 |
| **子Agent** | 独立上下文 | 共享工具集，独立消息列表，结构化结果 |
| **MCP** | 外部工具协议 | JSON-RPC over stdio，动态注册到 ToolRegistry |
| **Hook** | 4个生命周点 | PRE_LOOP / POST_LOOP / PRE_TOOL / POST_TOOL |
| **监控** | 指标 + 告警 | P0-P3 四级告警，工具调用统计，Token 追踪 |
| **会话** | JSONL 持久 | --resume 恢复，关键词搜索，自动归档 |

---

## 🚀 快速开始

### 安装

```bash
# 方式一：从 PyPI 安装（推荐）
pip install agent-cli-Mrzhou300

# 方式二：从源码安装
git clone https://github.com/your-username/agent-cli.git
cd agent-cli
uv sync
```

### 配置 API Key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 运行

```bash
# 命令行模式（pip 安装后直接用）
agent-cli run "你好，请搜索项目中的 TODO 注释"

# 从源码运行需加 uv run 前缀
uv run agent-cli run "你好"

# REPL 交互模式（支持 --resume 恢复会话）
agent-cli repl

# 恢复指定会话
agent-cli repl --resume sess_20260610_143022_abc123

# 详细输出模式
agent-cli run --verbose "分析代码质量"

# JSON 输出模式
agent-cli run --json "查看系统状态"

# 初始化项目配置
agent-cli init
```

### 模型切换（v0.2.0）

支持 Anthropic Claude 和 OpenAI 兼容 API（如 DeepSeek）之间的自由切换：

```bash
# 使用 Claude（设置 ANTHROPIC_API_KEY 环境变量，或者 auto 自动检测）
export ANTHROPIC_API_KEY=sk-ant-xxx
agent-cli run "分析代码" --provider anthropic

# 使用 DeepSeek（设置 COMPATIBLE_API_KEY 环境变量）
export COMPATIBLE_API_KEY=sk-xxx
agent-cli run "写一个排序算法" --provider compatible

# auto 模式按优先级自动检测：ANTHROPIC_API_KEY > COMPATIBLE_API_KEY > Mock
agent-cli run "你好"        # 自动选择可用模型

# 显式指定 API key 和模型名称
agent-cli repl --provider compatible --api-key sk-xxx --model deepseek-chat

# 使用其他兼容 API（如 OpenAI）
agent-cli repl --provider compatible --base-url https://api.openai.com/v1 --api-key sk-xxx

# 显式使用 Mock 模式（无需 API key）
agent-cli run "你好" --provider mock
```

### 流式输出

`CompatibleProvider` 和 `AnthropicProvider` 支持流式输出（SSE），逐字返回结果：

```bash
# DeepSeek 流式输出
agent-cli run "讲个故事" --provider compatible --api-key sk-xxx

# Claude 流式输出（默认启用）
agent-cli run "讲个故事"
```

---

## 🏗 架构一览

```
┌──────────────────────────────────────────────────────────────────┐
│                        CLI 层 (Typer)                             │
│    run "指令"   │   repl   │   init   │   plan   │   skill       │
│    permission   │   swarm  │   mcp    │ sessions │   memory       │
└──────────────────────┬───────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────┐
│                         Agent Loop 层                             │
│  ┌──────────┐  ┌────────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ Provider │  │ ToolReg.   │  │ TaskPlan │  │ HookManager   │  │
│  │ (Mock/   │  │ (8+工具)   │  │ (审批闭环)│  │ (4个Hook点)   │  │
│  │ Anthrop) │  │            │  │          │  │               │  │
│  └──────────┘  └────────────┘  └──────────┘  └───────────────┘  │
│  ┌──────────┐  ┌────────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ Skills   │  │ Subagent   │  │ Memory   │  │ MCP Bridge   │  │
│  │ (按需加载)│  │ (独立上下文)│  │ (三级记忆)│  │ (外部工具)    │  │
│  └──────────┘  └────────────┘  └──────────┘  └───────────────┘  │
│  ┌──────────┐  ┌────────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ Compact  │  │ Coordinator│  │ Monitor  │  │ Permission   │  │
│  │ (L1-L4)  │  │ (多Agent)  │  │ (监控告警)│  │ (四级权限)    │  │
│  └──────────┘  └────────────┘  └──────────┘  └───────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                     数据存储层 (.agent/)                          │
│  .agent/{memory, sessions, logs, archives, plans, skills}/      │
│  .agent/{permissions.json, mcp.json, project.md}                │
│  零外部依赖 — 一切基于文件系统，Git 可追踪                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🛠 命令大全

### 核心命令

| 命令 | 用途 | 示例 |
|:----|:-----|:------|
| `run` | 执行单次 Agent 任务 | `agent-cli run "搜索 TODO"` |
| `repl` | 进入交互式 REPL 模式 | `agent-cli repl` |
| `init` | 初始化 `.agent/` 目录 | `agent-cli init` |

### Phase 3 命令

| 命令 | 用途 | 示例 |
|:----|:-----|:------|
| `plan` | 任务规划与审批 | `agent-cli plan "任务1\n任务2" --approve` |
| `skill` | 管理技能系统 | `agent-cli skill --list` |
| `mcp` | 管理 MCP 工具 | `agent-cli mcp --connect` |
| `sessions` | 管理会话 | `agent-cli sessions --list` |
| `memory` | 管理记忆 | `agent-cli memory --list` |

### Phase 4 命令

| 命令 | 用途 | 示例 |
|:----|:-----|:------|
| `permission` | 四级权限管理 | `agent-cli permission --allow bash` |
| `swarm` | 多Agent协作 | `agent-cli swarm --vote "这个方案好么?"` |

---

## 🔐 权限管理

四级权限决策链：

```bash
# 查看所有规则
agent-cli permission --list

# 永久允许某工具
agent-cli permission --allow bash

# 永久拒绝某工具
agent-cli permission --deny write

# 设为总是询问
agent-cli permission --always-ask web_fetch

# 撤销规则
agent-cli permission --revoke bash

# 查看某工具的当前决策
agent-cli permission --show bash

# 查看权限引擎状态
agent-cli permission --status
```

决策优先级：
1. 自定义规则 (allow / deny / always_ask)
2. 工具安全等级 (safe → allow / sensitive → ask / dangerous → deny)
3. 默认 → ask

---

## 🤖 多Agent协作

四种编排模式：

### 顺序执行

```bash
# 任务依次执行，前一个结果传递给下一个
agent-cli swarm --sequential "分析项目结构\n查找配置文件\n生成报告"
```

### 并行执行

```bash
# 所有任务同时执行
agent-cli swarm --parallel "搜索TODO\n搜索FIXME\n搜索BUG"
```

### 投票模式

```bash
# 多个 Agent 独立回答同一问题
agent-cli swarm --vote "这个代码重构方案可靠吗？"
agent-cli swarm --vote "当前架构适合微服务吗？" --voters 5
```

### 辩论模式

```bash
# 正反双方多轮辩论
agent-cli swarm --debate "用 Rust 重写核心模块？"
agent-cli swarm --debate "微服务还是单体？" --rounds 3
```

---

## 📊 监控与告警

REPL 模式内置监控：

```
/stats      → 显示工具调用统计
/metrics    → 查看详细指标
/alerts     → 查看告警记录
```

告警分级：
- 🚨 **P0 致命**: API连续失败5次 / 循环迭代异常
- 🔴 **P1 严重**: 错误率 > 5%
- ⚠️ **P2 警告**: 重试超2次 / 循环迭代较多
- ℹ️ **P3 通知**: 常规信息

---

## 💬 REPL 命令

REPL 模式下可用命令：

```
/exit, /quit           退出 REPL
/help, /?              显示帮助
/save                  保存当前会话
/clear                 清空对话历史
/stats                 显示压缩/会话/监控统计
/memory                列出文件记忆
/sessions              列出所有会话
/sessions <id>         查看指定会话
/sessions --search=关键词  搜索会话内容
/resume <id>           恢复指定会话
/metrics               显示工具调用指标
/alerts                显示告警记录
```

---

## 📚 详细文档

- [开发规范文档](DEVELOPMENT_SPECIFICATION.md) — 完整的14个模块规范
- [架构详解](docs/architecture.md) — 五层架构、数据流、核心设计模式、扩展点
- [模块详解](docs/modules.md) — 14个模块的职责、接口、设计决策

---

## 🧪 测试

```bash
# 运行所有测试
uv run pytest tests/ -v

# 覆盖率报告
uv run pytest tests/ --cov=agent_cli --cov-report=term

# 代码质量检查
uv run ruff check src/ tests/
uv run ruff format src/ tests/ --check

# 类型检查（非阻塞）
uv run mypy src/ || true
```

**668 测试全部通过**（覆盖率 87% • `--cov-fail-under=80`），覆盖：
- 数据模型 (9) · Provider (61) · Agent Loop (7) · ToolRegistry (8)
- Hooks (9) · Session (17) · Memory (30) · Compact (13)
- Permission (18) · Planning (17) · Skills (20) · MCP (10)
- Subagent (24) · 监控 (18) · Swarm (24) · 文件工具 (30)
- Bash (22) · Web (12) · AgentTool (10) · Executor (6)
- Renderer (16) · REPL (38) · SessionMemory (9)

---

## 💡 设计哲学

1. **Agent = 模型 + Harness** — 工程师不是在编写智能，而是在构建智能栖居的世界
2. **最小化 Agent Loop** — ~60 行核心循环，所有复杂机制"挂在循环上"
3. **工具优先** — 新增能力 = 注册新工具 handler
4. **渐进式复杂** — 从最小可行 Harness 开始，每步只加一个机制
5. **文件即通信** — JSONL 文件作为消息总线，零外部依赖

---

## 🙏 致谢

本项目的设计思想融合自以下优秀开源项目：

- [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) (62.9k ⭐) — 循环结构、上下文压缩、Hook 模式
- [bozhouDev/14days-build-claude-code-cli](https://github.com/bozhouDev/14days-build-claude-code-cli) — Provider 抽象、ToolRegistry、CLI 框架
- [bcefghj/claude-code-complete-guide_v2](https://github.com/bcefghj/claude-code-complete-guide_v2) — 四级权限、三级记忆、Agent Teams

---

> **协议**: MIT
> **版本**: 0.2.0
> **最后更新**: 2026-06-11
