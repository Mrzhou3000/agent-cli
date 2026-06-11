# Agent-CLI 架构详解

> **版本**: v0.2.0 | **最后更新**: 2026-06-11

---

## 目录

1. [架构总览](#1-架构总览)
2. [分层架构](#2-分层架构)
3. [数据流](#3-数据流)
4. [核心设计模式](#4-核心设计模式)
5. [扩展点](#5-扩展点)

---

## 1. 架构总览

Agent-CLI 是一个**轻量级个人助手命令行工具**，围绕 **Agent = 模型 + Harness** 的设计哲学构建。整个系统分为五层，每层职责清晰，层间通过接口解耦。

```
                      ┌──────────────────────┐
                      │    用户 (终端)         │
                      └──────────┬───────────┘
                                 │ stdin/stdout
                      ┌──────────▼───────────┐
                      │    CLI 层 (Typer)     │
                      │  run / repl / init   │
                      │  plan / skill / mcp  │
                      │  swarm / permission  │
                      └──────────┬───────────┘
                                 │ Typer callback
                      ┌──────────▼───────────┐
                      │   Agent Loop 层       │
                      │  (core/loop.py)      │
                      │   ~60行核心循环       │
                      └──────────┬───────────┘
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │ Provider  │ │ ToolReg  │ │ Hooks    │
              │ (模型抽象) │ │ (工具注册) │ │ (生命周期) │
              └──────────┘ └──────────┘ └──────────┘
                    │
              ┌─────┴─────────────────┐
              │  挂载机制 (Plugins)     │
              │  记忆 · 压缩 · 技能    │
              │  子Agent · MCP · Swarm │
              └────────────────────────┘
```

### 核心思想

| 原则 | 说明 |
|:-----|:------|
| **最小化核心循环** | Agent Loop 本身只有 ~60 行，所有复杂机制都挂在循环上 |
| **工具优先** | 新增能力 = 注册一个新的 Tool Handler |
| **文件即通信** | JSONL 文件作为消息总线，零外部依赖 |
| **渐进式复杂** | 从 MockProvider 开始，逐步替换为真实 Provider |

---

## 2. 分层架构

### 2.1 CLI 层 (`src/agent_cli/main.py`)

基于 **Typer** 构建的命令行框架，负责：

- 参数解析与验证
- 子命令分发（run / repl / init / plan / skill / mcp / sessions / memory / permission / swarm）
- 全局日志配置
- 组件组装（依赖注入的入口）

```python
# 典型流程：main.py 组装所有组件
provider = _create_provider(provider=provider_opt, model=model, ...)
registry = _create_registry(allowed_dir=work_dir)
loop = AgentLoop(provider=provider, tools=registry, ...)
```

所有子命令共享 `_create_provider()` 和 `_create_registry()` 工厂函数，确保 Provider 和工具的创建逻辑统一。

### 2.2 Agent Loop 层 (`src/agent_cli/core/loop.py`)

系统的**心脏**，一个极其精简的 while 循环：

```
                    ┌─────────────────────┐
                    │    用户输入/恢复消息   │
                    └──────────┬──────────┘
                               ▼
                    ┌─────────────────────┐
          ┌─────── │  PRE_LOOP Hook       │ ← 技能注入 · 记忆检索
          │        └──────────┬──────────┘
          │                   ▼
          │        ┌─────────────────────┐
          │        │  LLM API 调用        │ ← Provider 抽象层
          │        └──────────┬──────────┘
          │                   ▼
          │        ┌─────────────────────┐
          │        │  解析响应            │
          │        └───────┬─────────────┘
          │           ┌────┴────┐
          │           ▼         ▼
          │    ┌──────────┐ ┌──────────┐
          │    │ 有工具调用 │ │ 无工具调用 │
          │    └─────┬────┘ └─────┬────┘
          │          ▼            ▼
          │  ┌──────────────┐  ┌──────┐
          │  │ PRE_TOOL Hook│  │ 返回  │
          │  │ (权限检查)    │  │ 结果  │
          │  └──────┬───────┘  └──────┘
          │         ▼
          │  ┌──────────────┐
          │  │ 执行工具      │
          │  └──────┬───────┘
          │         ▼
          │  ┌──────────────┐
          │  │ POST_TOOL    │ ← 监控指标采集
          │  │ Hook         │
          │  └──────┬───────┘
          │         ▼
          │  ┌──────────────┐
          │  │ POST_LOOP    │ ← 压缩 · 记忆更新
          │  │ Hook         │
          └──┴──────┬───────┘
                     ▼ (回到 LLM 调用，直到无工具调用)
```

**关键特性**：
- 循环本身不知道任何挂载机制的存在 — 它只负责调用 Hook
- `max_iterations` 防止无限循环
- 异常安全：`PRE_TOOL` 阶段的权限拒绝不会炸掉整个循环

### 2.3 Provider 抽象层 (`src/agent_cli/core/provider.py`)

实现 **模型适配器** 模式，三个实现共享同一个 `IModelProvider` 接口：

```
┌─────────────────────────────────────────────┐
│              IModelProvider                   │
│  + chat(messages) → ModelResponse            │
└─────────────────────────────────────────────┘
          ▲              ▲              ▲
          │              │              │
┌─────────┴────┐ ┌──────┴────────┐ ┌───┴────────┐
│ MockProvider  │ │AnthropicProv. │ │CompatProv. │
│ (测试用)       │ │ (Claude API)  │ │ (OpenAI兼容) │
│ 无API Key     │ │ 消息API       │ │ DeepSeek等  │
└──────────────┘ └───────────────┘ └────────────┘
```

选择策略（`_create_provider`）：
1. `auto` → 检测环境变量 `ANTHROPIC_API_KEY` > `COMPATIBLE_API_KEY` > Mock
2. `anthropic` → 强制使用 Claude
3. `compatible` → 强制使用兼容 API（可配置 `--base-url`）
4. `mock` → 强制 Mock（离线测试）

### 2.4 工具系统 (`src/agent_cli/tools/`)

基于 **Registry 模式** 的工具管理：

```
┌────────────────────────────────────────────┐
│              ToolRegistry                    │
│  + register(tool)                           │
│  + execute(name, args) → ToolResult         │
│  + list_tools() → list[ToolSpec]            │
└────────────────────────────────────────────┘
        │                           ▲
        │ register                  │ execute(name)
        ▼                           │
┌────────────────────────────────────────────┐
│               BaseTool                      │
│  + name: str                                │
│  + execute(input) → ToolResult              │
│  + to_param() → ToolParam                   │
└────────────────────────────────────────────┘
        ▲           ▲        ▲       ▲
        │           │        │       │
┌───────┴──┐ ┌──────┴──┐ ┌──┴────┐ ┌┴──────────┐
│ BashTool │ │ReadTool │ │WriteT.│ │WebFetchT. │ ...
│          │ │EditTool │ │GlobT. │ │AgentTool  │
│          │ │GrepTool │ │       │ │           │
└──────────┘ └─────────┘ └───────┘ └───────────┘
```

内置 8+ 工具，涵盖文件操作、命令执行、网络请求、子Agent 等场景。

### 2.5 挂载机制体系

所有挂载机制都通过 **Hook 系统** 集成到 Agent Loop 中：

| 挂载机制 | 挂载点 | 说明 |
|:---------|:-------|:------|
| **技能注入** | `PRE_LOOP` | 匹配用户输入关键词，自动注入技能内容 |
| **记忆检索** | `PRE_LOOP` | 从三级记忆检索相关上下文 |
| **权限检查** | `PRE_TOOL` | 四级权限决策链 |
| **监控指标** | `PRE_LOOP` / `POST_TOOL` / `POST_LOOP` | 工具调用统计、Token 追踪 |
| **上下文压缩** | `POST_LOOP` | L1-L4 渐进压缩，前 3 层零 API 成本 |
| **记忆更新** | `POST_LOOP` | 自动提取关键信息写入文件级记忆 |

---

## 3. 数据流

### 3.1 单次 `run` 的完整数据流

```
用户输入 "分析项目结构"
        │
        ▼
┌───────────────────┐
│  main.py          │
│  创建 Provider    │ ──→ Provider 根据 --provider 参数选择实现
│  创建 ToolRegistry│ ──→ 注册所有内置工具
│  创建 AgentLoop   │ ──→ 挂载 Hooks（记忆、监控、权限...）
│  调用 loop.run()  │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│  Agent Loop        │
│  [PRE_LOOP Hook]   │ ──→ 技能注入 + 记忆检索
│  Provider.chat()   │ ──→ LLM API 调用
│  解析响应           │
│  [工具调用?]        │
│    ├── 无 → 返回     │
│    └── 有 →          │
│         [PRE_TOOL]  │ ──→ 权限检查
│         ToolReg.    │ ──→ 执行具体工具
│          execute()  │
│         [POST_TOOL] │ ──→ 记录指标
│  [POST_LOOP Hook]   │ ──→ 压缩 + 记忆更新
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│  format_result()   │ ──→ 按 normal/verbose/json 格式输出
│  print()           │ ──→ 终端显示
└───────────────────┘
```

### 3.2 多 Agent 模式数据流

```
┌──────────────────────────────────────────────────┐
│               Swarm Coordinator                    │
│                                                    │
│  sequential(["任务A", "任务B"])                     │
│    ┌──────┐    ┌──────┐                           │
│    │任务A │───→│任务B │ (结果传递)                 │
│    └──────┘    └──────┘                           │
│                                                    │
│  parallel(["任务A", "任务B"])                       │
│    ┌──────┐                                       │
│    │任务A │  (同时执行，分别返回)                   │
│    ├──────┤                                       │
│    │任务B │                                       │
│    └──────┘                                       │
│                                                    │
│  vote("问题?", voters=3)                          │
│    ┌──────┐ ┌──────┐ ┌──────┐                    │
│    │投票1 │ │投票2 │ │投票3 │ → 统计共识          │
│    └──────┘ └──────┘ └──────┘                    │
│                                                    │
│  debate("主题", rounds=2)                         │
│    ┌──────────┐  ┌──────────┐                     │
│    │ 正方 R1  │→ │ 反方 R1  │                     │
│    └──────────┘  └──────────┘                     │
│         │              │                           │
│    ┌────▼─────┐  ┌─────▼─────┐                   │
│    │ 正方 R2  │  │ 反方 R2   │ → 总结             │
│    └──────────┘  └───────────┘                   │
└──────────────────────────────────────────────────┘
```

### 3.3 数据存储架构

```
.agent/
├── memory/           # 文件级记忆（Markdown + YAML Frontmatter）
│   ├── project.md    # 项目概况
│   └── *.md          # 每文件一条记忆
├── sessions/         # 会话记录（JSONL，每行一条消息）
│   └── *.jsonl
├── logs/             # 运行日志（按日期轮转）
├── archives/         # 超时会话归档
├── plans/            # 任务计划（JSON）
├── skills/           # 技能文件（Markdown）
├── permissions.json  # 权限规则持久化
└── mcp.json          # MCP 服务器配置
```

---

## 4. 核心设计模式

### 4.1 Hook 模式

四个生命周期点，实现机制与核心循环的解耦：

```python
# PRE_LOOP: 在 LLM 调用之前
loop.hooks.on(PRE_LOOP, inject_skills)
loop.hooks.on(PRE_LOOP, retrieve_memory)

# PRE_TOOL: 在工具执行之前
loop.hooks.on(PRE_TOOL, check_permission)

# POST_TOOL: 在工具执行之后
loop.hooks.on(POST_TOOL, collect_metrics)

# POST_LOOP: 在一次循环迭代之后
loop.hooks.on(POST_LOOP, compact_context)
loop.hooks.on(POST_LOOP, update_memory)
```

### 4.2 四级权限决策链

```
用户请求执行工具
       │
       ▼
┌─────────────────┐
│  自定义规则检查    │ → Allow: 直接放行
│  (permissions.json)│ → Deny: 直接拒绝
└────────┬─────────┘ → Always_Ask: 强制询问
         │ 未匹配
         ▼
┌─────────────────┐
│  工具安全等级检查  │ → safe: Allow
│  (内置分类)       │ → sensitive: Ask
└────────┬─────────┘ → dangerous: Deny
         │            → always_ask: Ask
         │ 未匹配
         ▼
┌─────────────────┐
│  默认策略         │ → Ask（询问用户）
└─────────────────┘
```

### 4.3 三级记忆架构

```
┌──────────────────────────────────────────────────┐
│  MemoryManager（统一入口）                         │
│  - 自动选择合适的记忆层                             │
│  - search() 跨层检索                              │
└──────┬──────────────┬──────────────┬─────────────┘
       │              │              │
       ▼              ▼              ▼
┌────────────┐ ┌────────────┐ ┌────────────┐
│ 文件级记忆  │ │ 会话级记忆  │ │ 项目级记忆  │
│ (FileMemory)│ │(SessionMem)│ │(ProjMemory)│
│            │ │            │ │            │
│ 长期持久    │ │ 短期上下文  │ │ 全局知识    │
│ Markdown   │ │ JSONL      │ │ Markdown   │
│ 用户/反馈/  │ │ 自动摘要    │ │ 项目概况    │
│ 项目/参考   │ │ 滑动窗口    │ │ 技术决策    │
└────────────┘ └────────────┘ └────────────┘
```

### 4.4 四层上下文压缩 (L1-L4)

```
L1: Token 计数        ─ 纯计算，零 API 成本
    ↓ 超限
L2: 消息合并          ─ 合并连续同角色消息
    ↓ 仍超限
L3: 系统消息摘要      ─ 保留最新 N 条完整消息
    ↓ 仍超限
L4: LLM 压缩          ─ 调用模型进行智能摘要（消耗 API）
```

---

## 5. 扩展点

系统的可扩展性体现在以下维度：

### 5.1 新增工具

```python
# 1. 继承 BaseTool
class MyTool(BaseTool):
    name = "my_tool"
    def execute(self, input: str) -> ToolResult:
        ...

# 2. 注册到 registry
registry.register(MyTool())
```

### 5.2 新增 Provider

```python
# 1. 实现 IModelProvider 接口
class MyProvider(IModelProvider):
    def chat(self, messages, **kwargs) -> ModelResponse:
        ...

# 2. 在 _create_provider() 中添加分支
```

### 5.3 新增 Hook

```python
# 1. 定义 handler
def my_handler(messages):
    ...

# 2. 挂载到生命周期点
loop.hooks.on(PRE_LOOP, my_handler)
```

### 5.4 新增 MCP 工具

```python
# 在 .agent/mcp.json 中添加配置
{
  "mcp_servers": [
    {
      "name": "my-server",
      "command": "python",
      "args": ["-m", "my_mcp_server"]
    }
  ]
}
```

### 5.5 新增技能

```bash
agent-cli skill --name "代码审查" \
  --desc "审查代码质量" \
  --triggers "review,审查,code review" \
  --content "你是高级代码审查专家..."
```
