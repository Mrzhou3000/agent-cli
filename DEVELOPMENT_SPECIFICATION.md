# Agent-CLI 个人助手 · 工业级开发规范文档

> **版本**: v1.0.0  
> **最后更新**: 2026-06-10  
> **项目定位**: 轻量级个人助手 Agent —— 集三大开源项目（learn-claude-code / 14days-build-claude-code-cli / claude-code-complete-guide_v2）设计思想之大成的融合实现

---

## 📑 目录

1. [项目概述与定位](#1-项目概述与定位)
2. [设计哲学](#2-设计哲学)
3. [系统架构](#3-系统架构)
4. [模块规范（14个功能域）](#4-模块规范14个功能域)
   - 4.1 Agent Loop 核心循环
   - 4.2 Tool System 工具系统
   - 4.3 Permission System 权限体系
   - 4.4 Memory System 记忆系统
   - 4.5 Context Management 上下文管理
   - 4.6 Task Planning 任务规划
   - 4.7 Subagent System 子Agent系统
   - 4.8 Skill System 技能系统
   - 4.9 Hook System 钩子系统
   - 4.10 CLI / User Interaction 用户交互
   - 4.11 MCP Integration 外部工具协议
   - 4.12 Multi-Agent Collaboration 多Agent协作
   - 4.13 Error Handling 错误处理
   - 4.14 Session / Persistence 会话与持久化
5. [接口规范](#5-接口规范)
6. [数据流转](#6-数据流转)
7. [质量保障体系](#7-质量保障体系)
8. [部署与交付](#8-部署与交付)
9. [附录](#9-附录)

---

## 1. 项目概述与定位

### 1.1 项目背景

本项目的目标是从零构建一个**轻量级个人助手 Agent CLI**，集成了以下三个顶级开源项目的设计思想精华：

| 编号 | 项目 | Stars | 定位 | 核心贡献 |
|:---:|:----|:----:|:-----|:--------|
| ① | [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) | 62,900+ | Claude Code 逆向工程教学 | **Agent = Model + Harness** 哲学、四层上下文压缩、Hook 设计模式 |
| ② | [bozhouDev/14days-build-claude-code-cli](https://github.com/bozhouDev/14days-build-claude-code-cli) | 新兴项目 | 手搓代码 Agent CLI | **ModelProvider 抽象层**、ToolRegistry 注册中心、Safe Edit、权限引擎 |
| ③ | [bcefghj/claude-code-complete-guide_v2](https://github.com/bcefghj/claude-code-complete-guide_v2) | ~200 | Claude Code 源码深度解读 | **四级权限决策链**、记忆三层架构、Agent Teams 编排 |

### 1.2 项目定位

- **求职作品**：体现 Agent 开发全流程的广度（14个功能域全覆盖）与技术深度（融合三大设计哲学）
- **轻量级**：代码结构清晰、文档简洁易懂、支持个人独立阅读与迭代优化
- **教学相长**：每部分设计都有明确的出处和决策理由，方便后续维护者理解

### 1.3 技术栈

| 层面 | 选型 | 理由 |
|:----|:-----|:-----|
| **语言** | Python 3.13+ | 三个项目中两个使用 Python，生态成熟，学习成本低 |
| **CLI框架** | Typer | 14days-build 项目验证，类型安全、自动生成 --help |
| **LLM API** | Anthropic Messages API | 行业标准格式，兼容性广 |
| **Provider** | Mock / Anthropic / Compatible 三层 | 14days-build 设计模式，测试友好 |
| **测试** | pytest | Python 生态标准 |
| **代码质量** | Ruff + mypy | 现代 Python 项目标配 |
| **依赖管理** | uv | 比 pip/poetry 更快、更现代 |

---

## 2. 设计哲学

### 2.1 五大核心共识

经过对三大项目设计思想的系统性分析，提炼出以下五条贯穿整个项目的核心原则：

#### 共识 1：Agent = 模型 + Harness

> **Agency 来自模型训练，Harness 是工程师的职责。**

工程师不是在编写智能，而是在构建智能栖居的世界。Harness 包含：工具（Tools）、知识（Knowledge）、观察（Observation）、行动接口（Action Interfaces）、权限（Permissions）。

#### 共识 2：最小化 Agent Loop

> **核心循环本身极其简单（约 30 行），所有复杂机制都挂在循环上，而非写进循环里。**

循环骨架在项目演进中 **从不改变**。新增能力 = 新增挂载机制，而非修改循环本身。

#### 共识 3：工具优先

> **新增能力 = 新增工具 handler。**

工具注册表（ToolRegistry）是扩展系统的核心入口。加一个工具，只加一个 handler——dispatch map 新增一个条目。

#### 共识 4：渐进式复杂

> **从最小可行 Harness 开始，每步只加一个机制。**

各机制之间松散耦合，可独立开发、测试、启用/禁用。

#### 共识 5：文件即通信

> **JSONL 文件作为消息总线，零依赖、可调试、天然持久。**

不使用数据库，不依赖外部中间件。一切持久化基于文件系统，Git 可追踪，人类可阅读。

### 2.2 设计原则优先序

```
1. 最小可用  > 过度设计       (不为未来可能的需求增加复杂度)
2. 可读性    > 炫技写法       (代码是写给人读的)
3. 可测试性  > 运行时效率     (可测试是长期维护的基石)
4. 渐进扩展  > 一步到位       (每个模块都有清晰的演进路径)
5. 文件存储  > 外部依赖       (零外部服务依赖)
```

---

## 3. 系统架构

### 3.1 整体架构分层

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLI 层 (Typer)                                 │
│    agent run "指令"     │    agent repl      │    agent --resume ...    │
│    agent --help         │    agent version   │    agent init            │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────────┐
│                         Session 层                                       │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │  MessageStore     │  │  ContextManager   │  │  PermissionEngine    │  │
│  │  (JSONL 读写)     │  │  (压缩/恢复)      │  │  (四级决策)          │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────────┐
│                       Agent Loop 层                                      │
│                                                                          │
│  ┌────────────┐  ┌──────────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ ModelProv. │  │ ToolRegistry │  │ TaskPlan │  │ HookManager      │  │
│  │ (Mock/     │  │ (ToolSpec)   │  │ (Todo+   │  │ (4个Hook点)       │  │
│  │ Anthropic) │  │ 8个内置工具   │  │ 审批闭环) │  │ pre/post loop/tool│  │
│  └────────────┘  └──────────────┘  └──────────┘  └──────────────────┘  │
│                                                                          │
│  ┌────────────┐  ┌──────────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ SkillLoader│  │ SubagentMgr  │  │ MemMgr   │  │ MCPBridge        │  │
│  │ (按需加载)  │  │ (独立上下文)  │  │ (三级记忆)│  │ (外部工具扩展)    │  │
│  └────────────┘  └──────────────┘  └──────────┘  └──────────────────┘  │
│                                                                          │
│  ┌──────────────┐  ┌──────────────────┐                                 │
│  │ CompactPipe  │  │ SwarmCoordinator │                                 │
│  │ (L1-L4压缩)  │  │ (多Agent编排)    │                                 │
│  └──────────────┘  └──────────────────┘                                 │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────────┐
│                      执行层 (Executor)                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Bash     │  │ File     │  │ Web      │  │ MCP      │  │ SubAgent │  │
│  │ Executor │  │ Operator │  │ Fetcher  │  │ Client   │  │ Launcher │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────────┐
│                       数据存储层 (.agent/)                               │
│                                                                          │
│  .agent/                                                                 │
│  ├── memory/          # 文件级记忆 (*.md + YAML frontmatter)            │
│  ├── sessions/        # 会话记录 (*.jsonl)                               │
│  ├── permissions.json # 权限规则持久化                                    │
│  ├── mcp.json         # MCP 服务端配置                                    │
│  ├── project.md       # 项目级记忆                                       │
│  ├── logs/            # 运行日志 (JSON Lines, 每日轮转)                   │
│  └── archives/        # 超过24小时的会话归档                              │
│                                                                          │
│  零外部依赖 —— 一切基于文件系统，Git 可追踪，人类可阅读                    │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 项目目录结构

```
agent-cli/                          # 项目根目录
│
├── README.md                       # 项目介绍 + 快速开始
├── DEVELOPMENT_SPECIFICATION.md    # 本开发规范文档（你正在阅读的）
├── pyproject.toml                  # 项目元数据 + 依赖管理
├── .pre-commit-config.yaml         # pre-commit 钩子配置
├── .github/workflows/              # CI/CD 配置
│   └── test.yml                    # 自动测试流水线
│
├── .agent/                         # 运行时数据目录（.gitignore）
│   ├── memory/                     # 文件级记忆
│   ├── sessions/                   # 会话记录
│   ├── permissions.json            # 权限规则
│   ├── mcp.json                    # MCP 配置
│   ├── project.md                  # 项目记忆
│   ├── logs/                       # 运行日志
│   └── archives/                   # 会话归档
│
├── src/agent_cli/                  # 主源码目录
│   ├── __init__.py
│   ├── main.py                     # CLI 入口（Typer）
│   │
│   ├── core/                       # 核心运行时
│   │   ├── __init__.py
│   │   ├── loop.py                 # Agent Loop ~60行核心
│   │   ├── provider.py             # ModelProvider 抽象 + 实现
│   │   └── executor.py             # 工具执行器
│   │
│   ├── tools/                      # 工具系统
│   │   ├── __init__.py
│   │   ├── registry.py             # ToolRegistry 注册中心
│   │   ├── base.py                 # BaseTool 抽象基类
│   │   ├── bash.py                 # Bash 工具
│   │   ├── file.py                 # Read / Write / Edit / Glob / Grep
│   │   ├── web.py                  # WebFetch 工具
│   │   └── agent_tool.py           # Agent（子Agent）工具
│   │
│   ├── memory/                     # 记忆系统
│   │   ├── __init__.py
│   │   ├── file_memory.py          # 文件级记忆（MemDir）
│   │   ├── session_memory.py       # 会话级记忆（JSONL）
│   │   └── project_memory.py       # 项目级记忆
│   │
│   ├── permissions/                # 权限体系
│   │   ├── __init__.py
│   │   └── engine.py               # Permission Engine
│   │
│   ├── planning/                   # 任务规划
│   │   ├── __init__.py
│   │   ├── todo.py                 # TodoWrite
│   │   └── task_graph.py           # 任务图 + 依赖管理
│   │
│   ├── hooks/                      # 钩子系统
│   │   ├── __init__.py
│   │   └── manager.py              # HookManager
│   │
│   ├── skills/                     # 技能系统
│   │   ├── __init__.py
│   │   └── loader.py               # Skill Loader
│   │
│   ├── subagent/                   # 子Agent系统
│   │   ├── __init__.py
│   │   └── manager.py              # 子Agent管理器
│   │
│   ├── mcp/                        # MCP 集成
│   │   ├── __init__.py
│   │   └── bridge.py               # MCPToolBridge
│   │
│   ├── swarm/                      # 多Agent协作
│   │   ├── __init__.py
│   │   └── coordinator.py          # Coordinator 模式
│   │
│   ├── compact/                    # 上下文压缩
│   │   ├── __init__.py
│   │   └── pipeline.py             # L1-L4 渐进压缩管道
│   │
│   ├── session/                    # 会话管理
│   │   ├── __init__.py
│   │   └── store.py                # 会话存储与恢复
│   │
│   └── ui/                         # 用户交互
│       ├── __init__.py
│       └── renderer.py             # CLI 输出渲染
│
├── tests/                          # 测试目录
│   ├── test_loop.py                # Agent Loop 测试
│   ├── test_tools/                 # 工具系统测试
│   │   ├── test_registry.py
│   │   ├── test_bash.py
│   │   └── test_file.py
│   ├── test_memory.py              # 记忆系统测试
│   ├── test_permissions.py         # 权限测试
│   ├── test_compact.py             # 上下文压缩测试
│   ├── test_planning.py            # 任务规划测试
│   ├── test_hooks.py               # 钩子测试
│   └── conftest.py                 # 共享 fixtures（MockProvider）
│
├── docs/                           # 文档目录
│   ├── architecture.md             # 架构详解
│   ├── modules.md                  # 各模块详解
│   ├── quickstart.md               # 快速入门
│   └── examples/                   # 使用示例
│       ├── basic-qa.md
│       ├── multi-step.md
│       └── multi-agent.md
│
└── examples/                       # 可运行示例脚本
    └── demo_basic.py
```

---

## 4. 模块规范（14个功能域）

### 4.1 Agent Loop（核心循环）

#### 设计决策

| 决策项 | 方案 | 来源 | 理由 |
|:------|:-----|:----|:-----|
| **循环结构** | `while True` + `stop_reason` 判断 | ① | 保持最小化，核心逻辑一目了然 |
| **Provider抽象** | Interface + Mock/Anthropic/Compatible 三层 | ② | 支持多模型切换，测试友好 |
| **Phase标记** | 轻量注释标记（非强制状态机） | ③ | 为 Hook/事件提供插入点 |
| **消息格式** | Anthropic Messages API 标准 | 三者共识 | 行业标准，兼容性最广 |

#### 核心代码骨架

```python
# src/agent_cli/core/loop.py

class AgentLoop:
    """
    Agent 核心循环。
    
    设计哲学：循环本身极其简单，所有复杂机制"挂在循环上"而非"写进循环里"。
    
    Usage:
        loop = AgentLoop(provider=AnthropicProvider(), tools=ToolRegistry())
        result = loop.run(messages=[{"role": "user", "content": "你好"}])
    """
    
    def __init__(self, provider: IModelProvider, tools: ToolRegistry):
        self.provider = provider      # ModelProvider 抽象层
        self.tools = tools            # ToolRegistry 注册中心
        self.hooks = HookManager()    # 4个 Hook 点
        self.memory = MemoryManager() # 三级记忆
        self.compact = CompactPipeline() # L1-L4压缩管道
    
    def run(self, messages: list) -> str:
        """运行 Agent 循环，返回最终文本回复。"""
        while True:
            # === Phase 1: 模型推理 ===
            response = self.provider.invoke(messages, self.tools.schemas())
            messages.append(response)
            
            # === Phase 2: 判断 ===
            if response.stop_reason != "tool_use":
                # 文本回复 → 输出并结束
                return response.text
            
            # === Phase 3: 工具执行 ===
            for block in response.content:
                if block.type != "tool_use":
                    continue
                
                self.hooks.trigger("pre_tool", block)
                try:
                    result = self.tools.execute(block.name, **block.input)
                except Exception as e:
                    result = {"error": str(e)}
                self.hooks.trigger("post_tool", block, result)
                
                messages.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": block.id, "content": result}]
                })
            
            # === Phase 4: 上下文压缩检测 ===
            if self.compact.should_compact(messages):
                messages = self.compact.compress(messages)
```

#### Provider 接口

```python
# src/agent_cli/core/provider.py

class IModelProvider(ABC):
    """模型提供者接口。"""
    
    @abstractmethod
    def invoke(self, messages: list, tools: list[dict]) -> Response:
        """调用模型，返回响应。"""
        ...

class MockProvider(IModelProvider):
    """Mock 实现：返回预设响应，用于测试。"""

class AnthropicProvider(IModelProvider):
    """Anthropic Claude API 实现。"""

class CompatibleProvider(IModelProvider):
    """兼容 API 实现（如 DeepSeek 兼容模式）。"""
```

---

### 4.2 Tool System（工具系统）

#### 设计决策

| 决策项 | 方案 | 来源 |
|:------|:-----|:----|
| **注册机制** | `ToolRegistry` 统一注册中心 + `ToolSpec` 元信息 | ② |
| **内置工具** | 8个核心工具：Bash / Read / Write / Edit / Glob / Grep / WebFetch / Agent | ①+② |
| **安全机制** | cwd 边界检查 + read-before-edit + diff preview | ② |
| **扩展方式** | 预留 `MCPToolBridge` 接口 | ①+③ |

#### ToolSpec 定义

```python
# src/agent_cli/tools/base.py

@dataclass
class ToolSpec:
    """工具元信息规范。"""
    name: str                        # 工具名（唯一标识）
    description: str                 # 人类可读描述
    parameters: dict                 # JSON Schema 参数定义
    handler: Callable                # 执行函数
    safety: SafetyLevel              # 安全等级

class SafetyLevel(Enum):
    SAFE = "safe"          # 无风险，直接执行
    SENSITIVE = "sensitive" # 敏感操作，需要确认
    DANGEROUS = "dangerous" # 危险操作，必须审批
    ALWAYS_ASK = "always_ask" # 总是询问

class BaseTool(ABC):
    """工具基类。所有工具必须继承此类。"""
    
    @abstractmethod
    def spec(self) -> ToolSpec:
        """返回工具的元信息描述。"""
        ...
    
    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """执行工具逻辑。"""
        ...
```

#### ToolRegistry 注册中心

```python
# src/agent_cli/tools/registry.py

class ToolRegistry:
    """工具注册中心。
    
    管理所有工具的注册、查找、执行。
    支持自动生成 LLM 所需的 JSON Schema 格式。
    
    Usage:
        registry = ToolRegistry()
        registry.register(BashTool())
        schemas = registry.schemas()  # → LLM 可用的 tool 列表
        result = registry.execute("bash", command="echo hello")
    """
    
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool) -> None:
        """注册工具。同名工具会覆盖并产生警告。"""
    
    def schemas(self) -> list[dict]:
        """生成 LLM API 所需的 tools 参数格式。"""
    
    def execute(self, name: str, **kwargs) -> Any:
        """执行指定工具。"""
```

---

### 4.3 Permission System（权限体系）

#### 设计决策

| 决策项 | 方案 | 来源 |
|:------|:-----|:----|
| **决策模型** | 四级：Allow / Deny / Ask / Always | ③ |
| **边界检查** | cwd 目录边界 + 危险命令分类黑名单 | ② |
| **持久化** | 项目级 `.agent/permissions.json` + 用户级全局规则 | ②+③ |
| **审批回退** | 默认 Ask → 用户选择后可记忆 | ① |

#### 决策流程

```
操作请求
  │
  ├─ 规则引擎匹配
  │   ├─ match(allow) ───────→ ✅ 直接放行
  │   ├─ match(deny) ────────→ ❌ 拒绝并反馈理由
  │   ├─ match(always_ask) ──→ 必须用户确认
  │   └─ no match ───────────→ 进入边界检查
  │
  ├─ 边界检查
  │   ├─ 安全(still within cwd) ─→ Ask 用户
  │   └─ 危险(escape cwd/rm -rf) → Deny + 警告
  │
  └─ 用户回应
      ├─ 同意 → 放行 + 可选记录规则
      ├─ 拒绝 → 拒绝 + 告知 Agent
      └─ 信任此操作 → 放行 + 持久化 allow 规则
```

---

### 4.4 Memory System（记忆系统）

#### 设计决策

| 决策项 | 方案 | 来源 |
|:------|:-----|:----|
| **层级架构** | 三级全量：文件级 + 会话级 + 项目级 | ①+③ |
| **文件级格式** | Markdown + YAML Frontmatter | ① |
| **会话级格式** | JSONL | ② |
| **存储位置** | `.agent/memory/` / `.agent/sessions/` | 三者融合 |
| **容量控制** | Token 阈值检测 + LLM 自动摘要压缩 | ③ |

#### 三层记忆详解

```
文件级记忆 (FileMemory) — 长期持久知识
  位置: .agent/memory/*.md
  格式: Markdown + YAML Frontmatter
          ---
          name: user-preferences
          description: 用户偏好设置
          metadata:
            type: user
            created: 2026-06-10
          ---
          用户 prefers 使用中文回复
          用户工作在 Python/TypeScript 项目
  索引: 通过文件名 + frontmatter 标签检索
  容量: 每条 < 2K tokens，超额触发摘要

会话级记忆 (SessionMemory) — 当前/近期上下文
  位置: .agent/sessions/*.jsonl
  格式: JSONL（每行一个完整消息对象）
  内容: 完整对话历史 + 工具调用记录
  隔离: 每个会话一个文件
  恢复: --resume <session_id> 参数加载

项目级记忆 (ProjectMemory) — 项目全局知识
  位置: .agent/project.md
  格式: 自动维护的项目知识文档
  内容: 项目结构、代码规范、技术选型、设计决策
  更新: Agent 在每次 loop 间歇自动同步
```

---

### 4.5 Context Management（上下文管理）

#### 设计决策

| 决策项 | 方案 | 来源 |
|:------|:-----|:----|
| **压缩策略** | 四层渐进压缩 L1-L4 | ①（该项目最有特色的设计） |
| **L1-L3** | 零 API 调用，纯算法压缩 | ① |
| **L4** | 模型摘要重写关键上下文 | ① |
| **触发阈值** | 70% → L1-L3；90% → L4 | ① |
| **压缩标记** | 压缩后消息添加 `[compressed]` 标记 | ① |

#### L1-L4 压缩管道

```python
# src/agent_cli/compact/pipeline.py

class CompactPipeline:
    """
    四层上下文压缩管道。
    
    L1 (丢弃层 - 零API):
        - 丢弃已完成的工具调用 block 细节
        - 丢弃过期的系统消息片段
        - 压缩文件路径为相对/短路径
    
    L2 (合并层 - 零API):
        - 合并相邻同类消息（连续 tool_result）
        - 压缩重复出现的代码块引用
    
    L3 (摘要层 - 零API):
        - 对早期对话做结构化摘要
        - 提取关键决策和结论
        - 移除非核心的中间步骤
    
    L4 (重写层 - 模型API):
        - 用 LLM 重写关键上下文
        - 保持语义完整性
        - 标记压缩来源位置
    """
    
    COMPACT_RATIO = 0.7   # 70% 阈值触发 L1-L3
    CRITICAL_RATIO = 0.9  # 90% 阈值触发 L4
    
    def should_compact(self, messages: list) -> bool:
        """检查是否需要压缩。"""
        current = self._count_tokens(messages)
        return current > self._max_tokens * self.COMPACT_RATIO
    
    def compress(self, messages: list) -> list:
        """执行渐进压缩。"""
        ratio = self._count_tokens(messages) / self._max_tokens
        
        if ratio < self.COMPACT_RATIO:
            return messages
        messages = self._layer1_discard(messages)
        if ratio < self.CRITICAL_RATIO:
            return messages
        messages = self._layer2_merge(messages)
        messages = self._layer3_summarize(messages)
        # L4 仅当超过 90% 阈值时调用
        if ratio >= self.CRITICAL_RATIO:
            messages = self._layer4_rewrite(messages)
        return messages
```

---

### 4.6 Task Planning（任务规划）

#### 设计决策

| 决策项 | 方案 | 来源 |
|:------|:-----|:----|
| **流程** | 含审批闭环：规划→展示→确认→执行→汇总 | ② |
| **任务格式** | `TodoItem`: id + title + status + deps | ①+③ |
| **依赖支持** | 任务图 + 拓扑排序 | ① |
| **持久化** | 任务图持久化为 JSON 文件 | ① |

#### 任务状态机

```
            ┌──────────┐
            │ pending  │  ← 新创建的任务
            └────┬─────┘
                 │ 用户确认
            ┌────▼─────┐
            │ approved │  ← 审批通过
            └────┬─────┘
                 │ 开始执行
            ┌────▼──────┐
            │ in_progress│ ← 正在执行
            └────┬──────┘
               ┌─┴──┐
          ┌────▼┐ ┌▼─────┐
          │compl│ │failed│
          │eted │ │     │
          └─────┘ └─────┘
```

---

### 4.7 Subagent System（子Agent系统）

#### 设计决策

| 决策项 | 方案 | 来源 |
|:------|:-----|:----|
| **核心机制** | Agent → 派生子Agent（独立上下文）→ 执行 → 结果回填 | ① |
| **工具共享** | 共享父Agent工具集，独立消息列表 | ② |
| **隔离方式** | 可选 worktree 目录隔离 | ① |
| **使用场景** | 复杂任务拆解、并行探索、独立文件操作 | 三者共识 |

```python
# src/agent_cli/subagent/manager.py

class SubagentManager:
    """
    子Agent管理器。
    
    子Agent = 独立消息列表的 Agent Loop 实例。
    继承父 Agent 的工具集，但拥有完全独立的上下文。
    
    Usage:
        sub = SubagentManager(parent_loop)
        result = sub.spawn("搜索项目中所有的 TODO 注释")
    """
    
    def spawn(self, task: str, context: dict | None = None) -> SubagentResult:
        """
        派发一个子Agent。
        
        流程:
        1. 创建独立的消息列表（从父Agent摘要继承上下文）
        2. 创建新的 Agent Loop 实例
        3. 执行任务
        4. 返回结构化结果
        """
```

---

### 4.8 Skill System（技能系统）

#### 设计决策

| 决策项 | 方案 | 来源 |
|:------|:-----|:----|
| **核心哲学** | *"用到时再加载，别全塞 prompt 里"* | ① |
| **触发方式** | 双模式：自动上下文匹配 + 手动 `/skill` 命令 | ①+② |
| **Skill 格式** | Markdown + YAML Frontmatter 描述 | ①+② |
| **加载机制** | Slot 匹配 → Skill 读取 → Prompt 注入 | ① |

```markdown
# .agent/skills/python-dev.md
---
name: python-dev
description: Python 开发最佳实践知识
triggers: ["python", "pip", "pytest", "django", "flask"]
---

当你被问到 Python 相关问题时，遵循以下准则：
- 推荐使用 Python 3.10+ 特性（match/case, 类型注解）
- 优先使用 uv 而非 pip
- 测试优先，使用 pytest
- ...
```

---

### 4.9 Hook System（钩子系统）

#### 设计决策

| 决策项 | 方案 | 来源 |
|:------|:-----|:----|
| **核心哲学** | *"挂在循环上，不写进循环里"* | ① |
| **Hook 点** | 4个：`pre_loop` / `pre_tool` / `post_tool` / `post_loop` | ①+② |
| **注册方式** | 事件名→回调函数 字典注册 | ① |
| **配置位置** | `.agent/hooks/` 目录下按名管理 | ② |

```python
# src/agent_cli/hooks/manager.py

class HookManager:
    """
    钩子管理器。
    
    Hook 点:
      pre_loop(messages) → messages   # 循环开始前，可修改消息
      pre_tool(block)    → block       # 工具执行前
      post_tool(block, result) → None  # 工具执行后
      post_loop(response) → response   # 循环结束后（文本回复）
    
    内置 Hook 示例:
      - 日志记录: 记录每次工具调用
      - 性能追踪: 计时工具执行耗时
      - 用户通知: 长时间操作时提醒用户
    """
    
    def on(self, event: str, handler: Callable):
        """注册 Hook 处理器。"""
    
    def trigger(self, event: str, *args, **kwargs):
        """触发 Hook 事件。"""
```

---

### 4.10 CLI / User Interaction（用户交互）

#### 设计决策

| 决策项 | 方案 | 来源 |
|:------|:-----|:----|
| **CLI 框架** | Typer | ② |
| **交互模式** | 命令行模式 + REPL 交互模式 | ② |
| **输出分级** | normal（简要）/ verbose（详细）/ json（结构化） | 三者融合 |
| **进度展示** | 工具调用时实时状态（spinner + 执行摘要） | ②+③ |

```python
# src/agent_cli/main.py

app = typer.Typer()

@app.command()
def run(
    prompt: str = typer.Argument(..., help="用户指令"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    resume: str | None = typer.Option(None, "--resume"),
):
    """执行一次 Agent 会话。"""
    ...

@app.command()
def repl(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """进入交互式 REPL 模式。"""
    ...

@app.command()
def init():
    """初始化当前目录的 .agent/ 配置。"""
    ...
```

---

### 4.11 MCP Integration（外部工具协议）

#### 设计决策

| 决策项 | 方案 | 来源 |
|:------|:-----|:----|
| **接口** | `MCPToolBridge` 桥接类 | ①+③ |
| **协议** | 标准 MCP Client（stdio/SSE 传输） | ① |
| **发现机制** | ToolSearch → 动态注册到 ToolRegistry | ② |
| **配置** | `.agent/mcp.json` | ② |

```json
// .agent/mcp.json
{
  "mcp_servers": [
    {
      "name": "filesystem",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
    },
    {
      "name": "github",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"]
    }
  ]
}
```

---

### 4.12 Multi-Agent Collaboration（多Agent协作）

#### 设计决策

| 决策项 | 方案 | 来源 |
|:------|:-----|:----|
| **架构模式** | **Coordinator 模式**：1 个协调 + N 个 Worker | ③ |
| **通信方式** | 协调器分发任务 → Worker 执行 → 结果汇总 | ①+③ |
| **隔离** | 每个 Worker 独立消息列表 + 可选 Worktree | ① |
| **实现时间** | 第一版即实现基础 Coordinator 模式（1+2） | 用户确认 |

```
Coordinator Agent
  │
  ├─ 任务: "搜索项目中的TODO和FIXME"
  ├─ 分解: [搜索TODO, 搜索FIXME]
  │
  ├─ Worker 1: 搜索 TODO ──→ 结果: ["file1.py:42", ...]
  ├─ Worker 2: 搜索 FIXME ─→ 结果: ["file2.py:15", ...]
  │
  └─ 汇总: "共找到3个TODO和1个FIXME"
       ├─ TODO: file1.py:42, ...
       └─ FIXME: file2.py:15
```

---

### 4.13 Error Handling（错误处理）

#### 设计决策

| 决策项 | 方案 | 来源 |
|:------|:-----|:----|
| **重试策略** | 自动重试3次，指数退避（1s→2s→4s） | ① |
| **降级策略** | 子Agent失败不影响其他子Agent | ② |
| **错误分级** | WARN（可继续）/ ERROR（需用户决策）/ FATAL（终止） | ③ |
| **日志记录** | 所有错误记录到 `.agent/logs/error.log` | ② |

```python
# 错误分级示例
class AgentError(Exception):
    """Agent 系统异常基类。"""

class ToolExecutionError(AgentError):
    """工具执行异常（WARN 级，可重试）。"""

class PermissionDeniedError(AgentError):
    """权限拒绝（ERROR 级，需用户决策）。"""

class ProviderUnavailableError(AgentError):
    """模型服务不可用（FATAL 级，终止会话）。"""
```

---

### 4.14 Session / Persistence（会话与持久化）

#### 设计决策

| 决策项 | 方案 | 来源 |
|:------|:-----|:----|
| **会话存储** | JSONL，`.agent/sessions/` | ② |
| **消息结构** | Anthropic Messages API 原生格式 | 三者共识 |
| **会话恢复** | `--resume <session_id>` | ② |
| **自动归档** | 超过 24h 的会话自动移至 `.agent/archives/` | ①+② |

```python
# src/agent_cli/session/store.py

class SessionStore:
    """
    会话存储。
    
    使用 JSONL（JSON Lines）格式存储消息。
    每行一个完整消息对象，追加写入，天然支持流式。
    
    文件结构:
      .agent/sessions/
      ├── 20260610_143022_abc123.jsonl  # 活跃会话
      └── archives/                     # 24h以上归档
          └── 20260609_091234_def456.jsonl
    
    Usage:
        store = SessionStore()
        store.append("session_1", message)
        messages = store.load("session_1")
    """
```

---

## 5. 接口规范

### 5.1 核心接口总览

| 接口名 | 方向 | 方法签名 | 说明 |
|:-------|:----|:---------|:-----|
| `IModelProvider` | Loop→Provider | `invoke(messages, tools) → Response` | 模型调用 |
| `IToolRegistry` | Loop→Tools | `register(spec) / execute(name, **kwargs) → Any` | 工具注册与执行 |
| `IHookManager` | Loop→Hooks | `trigger(event, *args) → None` | 事件触发 |
| `IMemoryManager` | Loop→Memory | `read(query) → list / write(note) → None` | 记忆读写 |
| `ISubagentManager` | Loop→Subagent | `spawn(task, context) → Result` | 子Agent派生 |
| `IPermissionEngine` | Session→Perm | `check(action, tool) → Decision` | 权限决策 |
| `ICompactPipeline` | Loop→Compact | `should_compact(messages) → bool / compress(messages) → list` | 上下文压缩 |
| `ISessionStore` | Session→Store | `append(sid, msg) / load(sid) → list` | 会话管理 |
| `ISkillLoader` | Loop→Skills | `load(context) → list[str] / get(name) → str` | 技能加载 |
| `IMCPBridge` | Tools→MCP | `discover() → list[ToolSpec] / execute(name, **kwargs) → Any` | MCP扩展 |

### 5.2 通用数据格式

#### 消息格式（Anthropic Messages API）

```python
# 用户消息
{"role": "user", "content": "你好，请帮我搜索项目中的bug"}

# 带工具结果的消息
{"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": "tu_123", "content": "file1.py:42: TODO: fix this"}
]}

# 助手消息（含工具调用）
{"role": "assistant", "content": [
    {"type": "text", "text": "我来搜索一下"},
    {"type": "tool_use", "id": "tu_123", "name": "grep", "input": {"pattern": "TODO", "path": "."}}
]}
```

#### 工具 Schema 格式

```python
# ToolRegistry.schemas() 输出，直接用于 LLM API
{
    "name": "bash",
    "description": "执行 bash 命令",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令"}
        },
        "required": ["command"]
    }
}
```

#### 决策返回值

```python
# PermissionEngine.check() 返回值
class PermissionDecision:
    Allow = "allow"         # 直接放行
    Deny = "deny"           # 拒绝
    Ask = "ask"             # 询问用户
    AlwaysAsk = "always_ask" # 必须询问
```

---

## 6. 数据流转

### 6.1 单次 Agent 循环数据流

```
用户输入: "帮我创建一个test.txt"
  │
  ▼
┌──────────────────────┐
│  1. CLI 层            │  Typer 解析命令 → 初始化 Session
│     SessionStore      │  加载/创建会话 → 恢复或新建消息列表
└──────────┬───────────┘
           │ messages = [{"role": "user", "content": "帮我创建一个test.txt"}]
           ▼
┌──────────────────────┐
│  2. Permission Engine │  检查初始操作权限
│     - 无工具调用      │  直接放行（尚未涉及工具）
└──────────┬───────────┘
           │ messages → invoke(messages, tools)
           ▼
┌──────────────────────┐
│  3. Agent Loop        │
│     Phase 1: 推理     │  Provider.invoke() → LLM 返回 tool_use
│     Phase 2: 判断     │  stop_reason == "tool_use" → 进入 Phase 3
│     Phase 3: 执行     │  
│       ① pre_tool hook │  日志: "调用 WriteTool"
│       ② Permission    │  WriteTool 安全等级 → allow/ask
│       ③ ToolRegistry  │  execute("write", path="test.txt", content="hello")
│       ④ post_tool hook│  日志: "WriteTool 执行成功"
│       ⑤ 结果追加消息   │  tool_result → messages.append
│     Phase 4: 压缩检测  │  Token 未超阈值，继续循环
└──────────┬───────────┘
           │ messages → 再次 invoke
           ▼
┌──────────────────────┐
│  4. Agent Loop (2次)  │  LLM 返回文本回复
│     stop_reason 非    │  "已创建 test.txt"
│     tool_use → 结束   │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  5. 输出              │  CLI 渲染器格式化输出
│     6. 记忆同步(后台)  │  MemoryManager 提取关键信息写入 .agent/memory/
│     7. 会话持久化      │  SessionStore 追加写入 JSONL
└──────────────────────┘
```

### 6.2 多轮/多Agent 数据流

```
┌──────────────────────────────────────────────────┐
│  Coordinator Agent                                │
│                                                   │
│  输入: "分析项目中的代码质量问题"                   │
│  分解: [子任务1: 搜索代码规范,                    │
│         子任务2: 搜索已知bug,                     │
│         子任务3: 分析依赖版本]                    │
│                                                   │
│  ┌─ Worker 1 ─┐  ┌─ Worker 2 ─┐  ┌─ Worker 3 ─┐│
│  │ 独立messages │  │ 独立messages │  │ 独立messages ││
│  │ 共享Tool集   │  │ 共享Tool集   │  │ 共享Tool集   ││
│  │ grep规范文档 │  │ grep FIXME  │  │ pip list    ││
│  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘│
│         └──────────┬────┴──────────┘           │
│                    ▼                            │
│              汇总结果                            │
│              "共发现3个潜在问题..."              │
└──────────────────────────────────────────────────┘
```

---

## 7. 质量保障体系

### 7.1 测试金字塔

```
        ╱╲
       ╱  ╲              E2E 测试（5个关键场景）
      ╱    ╲
     ╱────────╲          集成测试（6个组合场景）
    ╱  模块间   ╲
   ╱              ╲
  ╱──────────────────╲   单元测试（8个模块，85-95%覆盖率）
 ╱  MockProvider 驱动  ╲
╱────────────────────────╲
    所有测试层共享 MockProvider
```

### 7.2 测试覆盖目标

| 模块 | 覆盖率目标 | 关键测试场景 |
|:----|:---------:|:------------|
| Agent Loop | ≥90% | 循环终止、工具调用分支、文本回复分支 |
| ToolRegistry | ≥90% | 注册/反注册、Schema生成、执行调度 |
| Bash Tool | ≥85% | 命令执行、超时、安全过滤，cwd边界 |
| File Tools | ≥90% | 读写边界、路径安全、编码处理 |
| Permission | ≥95% | 四级决策、规则匹配、持久化 |
| Memory | ≥85% | 文件级读写、会话级JSONL、容量控制 |
| Compact | ≥85% | L1-L4各层压缩、Token计数 |
| Hooks | ≥90% | 触发时机、参数传递、取消机制 |

### 7.3 监控指标

| 分类 | 指标 | 采集方式 |
|:----|:-----|:---------|
| **模型调用** | 请求量 QPS、平均/TTP50/P95/P99延时、Token消耗（输入/输出）、错误率 | 日志统计 |
| **工具执行** | 调用量（分工具）、成功率（分工具）、平均耗时（分工具）、权限拒绝次数 | 日志统计 + Hook |
| **上下文** | 当前会话 Token 曲线、压缩触发次数、压缩率（压缩前后对比） | Loop 内采样 |
| **系统资源** | 内存占用、线程数、磁盘 IO | psutil 采集 |

### 7.4 日志规范

| 级别 | 记录内容 | 示例 |
|:----|:---------|:-----|
| DEBUG | 开发调试细节（默认关闭） | 消息体全文、中间变量值 |
| INFO | 正常运行事件 | 工具调用、循环迭代、会话创建 |
| WARN | 异常但不影响运行 | 重试(1/3)、超时降级、权限Ask |
| ERROR | 需要关注的问题 | API调用失败、工具异常、权限Deny |
| FATAL | 致命，需人工介入 | Provider 重试耗尽、无限循环检测 |

### 7.5 代码质量标准

| 标准 | 工具/规则 | 执行方式 |
|:----|:---------|:--------|
| **代码风格** | Ruff（替代 Flake8+isort+Black） | `ruff check .` + pre-commit |
| **类型检查** | mypy strict mode | `mypy src/` CI 门禁 |
| **格式化** | Ruff formatter | `ruff format .` pre-commit |
| **提交规范** | Conventional Commits | `feat:` / `fix:` / `docs:` / `test:` / `refactor:` / `chore:` |
| **分支策略** | GitHub Flow | `main` + `feature/*` + `fix/*` |

### 7.6 告警分级

| 级别 | 触发条件 | 响应 |
|:----|:---------|:-----|
| **P0 致命** | API连续失败5次 / 无限循环检测 | 终端闪红 + 提示，立即 |
| **P1 严重** | 错误率 > 5% / 内存 > 300MB | 终端警告，< 1min |
| **P2 警告** | 重试超2次 / 压缩率 < 20% | 日志 WARN，< 5min |
| **P3 通知** | 会话超1小时 / Token超额50% | 日志 INFO，不强制 |

---

## 8. 部署与交付

### 8.1 环境要求

| 依赖 | 版本 | 说明 |
|:----|:----|:-----|
| Python | ≥ 3.13 | 推荐使用 pyenv 或 uv 管理版本 |
| uv | ≥ 0.4 | 包管理与虚拟环境 |
| Anthropic API Key | — | 通过 `ANTHROPIC_API_KEY` 环境变量配置 |

### 8.2 安装与运行

```bash
# 1. 克隆项目
git clone https://github.com/your-username/agent-cli.git
cd agent-cli

# 2. 安装依赖
uv sync

# 3. 配置 API Key
export ANTHROPIC_API_KEY="sk-ant-..."

# 4. 初始化项目配置（可选）
uv run agent-cli init

# 5. 运行
# 命令行模式:
uv run agent-cli run "你好，请帮我搜索项目中的TODO注释"

# REPL 交互模式:
uv run agent-cli repl

# 详细输出模式:
uv run agent-cli run --verbose "分析代码质量"

# 恢复会话:
uv run agent-cli run --resume session_20260610_143022 "继续刚才的分析"
```

### 8.3 项目初始化

```bash
# agent-cli init 会创建:
# .agent/
# ├── memory/           # 记忆目录（空）
# ├── sessions/         # 会话目录（空）
# ├── logs/             # 日志目录（空）
# ├── permissions.json  # 默认权限规则
# ├── mcp.json          # MCP配置（模板）
# └── project.md        # 项目记忆（模板）
```

### 8.4 GitHub 配置

#### README 必备内容

```markdown
# Agent-CLI — 轻量级个人助手

[![Python 3.13+](https://img.shields.io/badge/Python-3.13%2B-blue)]()
[![Ruff](https://img.shields.io/badge/code%20style-ruff-000000)]()
[![License MIT](https://img.shields.io/badge/license-MIT-green)]()

> 集三大开源项目设计思想之大成的轻量级个人助手 Agent。

## ✨ 特性

- **极简核心**：~60行 Agent Loop + 14个功能模块的渐进式架构
- **多模型支持**：MockProvider(测试) / Anthropic(Claude) / Compatible(DeepSeek等)
- **四级权限**：Allow/Deny/Ask/Always 安全决策
- **三级记忆**：文件级 + 会话级 + 项目级
- **四层压缩**：L1-L4 渐进上下文管理（前三层零API成本）
- **多Agent协作**：Coordinator + Worker 编排模式
- **MCP扩展**：遵循 Model Context Protocol 的外部工具集成
- **零外部依赖**：一切持久化基于文件系统

## 🏗 架构一览

[架构图]

## 🚀 快速开始

...（安装步骤同上）

## 📚 详细文档

- [开发规范文档](DEVELOPMENT_SPECIFICATION.md)
- [架构详解](docs/architecture.md)
- [模块详解](docs/modules.md)

## 🙏 致谢

本项目的设计思想融合自以下优秀开源项目：

- [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)
- [bozhouDev/14days-build-claude-code-cli](https://github.com/bozhouDev/14days-build-claude-code-cli)
- [bcefghj/claude-code-complete-guide_v2](https://github.com/bcefghj/claude-code-complete-guide_v2)
```

#### .gitignore 文件

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/

# 运行时数据
.agent/sessions/
.agent/logs/
.agent/archives/
.agent/memory/*.md
.agent/project.md

# 环境变量
.env
.env.local

# IDE
.vscode/
.idea/

# 系统
.DS_Store
Thumbs.db
```

#### GitHub Actions CI

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run ruff check src/
      - run: uv run mypy src/
      - run: uv run pytest tests/ --cov=src/ --cov-report=term
```

---

## 9. 附录

### A. 三大项目融合对照表

| 功能模块 | 主要借鉴 | 辅助借鉴 | 独立设计 |
|:---------|:--------|:--------|:---------|
| Agent Loop | ① 循环结构 | ② Provider抽象 | Phase注释标记 |
| Tool System | ② ToolRegistry | ① Dispatch思想 | ToolSpec+SafetyLevel |
| Permission | ③ 四级决策 | ② 边界检查 | .agent/permissions.json |
| Memory | ① 三级架构 | ② JSONL格式 | YAML Frontmatter |
| Context | ① L1-L4 | ③ 阈值检测 | 70%/90%二级触发 |
| Task Planning | ② 审批闭环 | ① TodoWrite | 拓扑排序依赖 |
| Subagent | ① 独立上下文 | ② 结果回填 | — |
| Skill | ① 按需加载 | ② 双模式触发 | YAML triggers |
| Hook | ① 4个Hook点 | ② 配置管理 | — |
| CLI/UI | ② Typer | ③ 多级输出 | 双模式+分级 |
| MCP | ①+③ 桥接接口 | ② 发现机制 | .agent/mcp.json |
| Multi-Agent | ③ Coordinator | ① 独立上下文 | 第一版即实现 |
| Error Handling | ① 重试策略 | ② 日志记录 | 三级错误分级 |
| Session | ② JSONL | ① 文件总线 | 24h自动归档 |

### B. 设计决策索引

| 决策编号 | 模块 | 决策 | 确认时间 |
|:---------|:----|:-----|:--------|
| D01 | Agent Loop | 极简风格 + Provider抽象 | 2026-06-10 |
| D02 | Tool System | ToolRegistry + 8个核心工具 | 2026-06-10 |
| D03 | Permission | 四级决策链 + 文件持久化 | 2026-06-10 |
| D04 | Memory | 三级全量 + Token阈值摘要 | 2026-06-10 |
| D05 | Context | 四层全量 + 70%/90%触发 | 2026-06-10 |
| D06 | Task Planning | 审批闭环 + 依赖拓扑排序 | 2026-06-10 |
| D07 | Subagent | 共享工具 + 独立上下文 | 2026-06-10 |
| D08 | Skill | 双模式(自动+手动)触发 | 2026-06-10 |
| D09 | Hook | 4个核心Hook点 | 2026-06-10 |
| D10 | CLI | 命令行 + REPL 双模式 | 2026-06-10 |
| D11 | MCP | MCPToolBridge + .agent/mcp.json | 2026-06-10 |
| D12 | Multi-Agent | Coordinator模式，第一版实现 | 2026-06-10 |
| D13 | Error Handling | 重试3次 + 三级分级 | 2026-06-10 |
| D14 | Session | JSONL + --resume + 24h归档 | 2026-06-10 |

### C. 演进路线图

```
Phase 1 (MVP) — 基础单Agent
  ├─ Agent Loop + MockProvider
  ├─ ToolRegistry + 8核心工具
  ├─ Permission Engine（三级简化版）
  ├─ Session Store（JSONL）
  └─ CLI: run 命令

Phase 2 — 记忆与上下文
  ├─ 三级记忆系统
  ├─ L1-L4 上下文压缩管道
  ├─ Hook 系统（4点）
  └─ REPL 交互模式

Phase 3 — 规划与扩展
  ├─ Task Planning（审批闭环）
  ├─ Skill 系统（双模式）
  ├─ MCP Bridge
  └─ Subagent 系统

Phase 4 — 多Agent与完善
  ├─ Coordinator 多Agent协作
  ├─ 完整权限（四级）
  ├─ 会话恢复 --resume
  ├─ 持续监控与告警
  └─ 完整文档 + 示例
```

---

> **文档版本**: v1.0.0  
> **最后更新**: 2026-06-10  
> **作者**: 基于三大开源项目设计思想融合而成  
> **协议**: MIT
