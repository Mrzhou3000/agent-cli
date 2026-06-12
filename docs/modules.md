# 模块详解

> **版本**: v0.2.1 | **最后更新**: 2026-06-12

---

本文档详细描述 Agent-CLI 的 14 个功能模块，涵盖每个模块的职责、数据结构、关键接口和设计决策。

---

## 目录

1. [Agent Loop 核心循环](#1-agent-loop-核心循环)
2. [Tool System 工具系统](#2-tool-system-工具系统)
3. [Permission System 权限体系](#3-permission-system-权限体系)
4. [Memory System 记忆系统](#4-memory-system-记忆系统)
5. [Context Management 上下文管理](#5-context-management-上下文管理)
6. [Task Planning 任务规划](#6-task-planning-任务规划)
7. [Subagent System 子Agent系统](#7-subagent-system-子agent系统)
8. [Skill System 技能系统](#8-skill-system-技能系统)
9. [Hook System 钩子系统](#9-hook-system-钩子系统)
10. [CLI / User Interaction 用户交互](#10-cli--user-interaction-用户交互)
11. [MCP Integration 外部工具协议](#11-mcp-integration-外部工具协议)
12. [Multi-Agent Collaboration 多Agent协作](#12-multi-agent-collaboration-多agent协作)
13. [Error Handling 错误处理](#13-error-handling-错误处理)
14. [Session / Persistence 会话与持久化](#14-session--persistence-会话与持久化)

---

## 1. Agent Loop 核心循环

**文件**: [`src/agent_cli/core/loop.py`](src/agent_cli/core/loop.py)

### 职责

Agent Loop 是系统的**心脏**，负责：
- 管理对话循环（用户输入 → LLM → 工具调用 → LLM → 输出）
- 协调 Provider、工具系统和各挂载机制的协作
- 提供 max_iterations 防止无限循环

### 核心接口

```python
class AgentLoop:
    def __init__(
        self,
        provider: IModelProvider,
        tools: ToolRegistry,
        session_store: SessionStore | None = None,
        memory: MemoryManager | None = None,
        compact: CompactPipeline | None = None,
        max_iterations: int = 20,
    )
    def run(self, prompt: str, messages=None, session_id=None) -> ModelResponse
    def run_messages(self, messages: list) -> ModelResponse  # 用于 Swarm/Subagent
```

### 设计决策

| 决策 | 理由 |
|:-----|:------|
| 循环本身 ~60 行 | 保持核心稳定，所有机制通过 Hook 挂载 |
| `max_iterations` 默认 20 | 大多数任务 3-8 轮完成，20 是安全上限 |
| 非阻塞式工具调用 | 串行执行，保持实现简单 |
| 异常安全 | `PRE_TOOL` 拒绝不会炸掉循环，单步异常可跳过 |

### 数据流

```python
# 用户输入 → loop.run()
while iteration < max_iterations:
    hooks.fire(PRE_LOOP, messages)     # 技能注入 + 记忆检索
    response = provider.chat(messages)  # LLM API 调用
    if not response.tool_calls:
        break                          # 无工具调用 → 返回
    for call in response.tool_calls:
        hooks.fire(PRE_TOOL, call)     # 权限检查
        result = tools.execute(call)   # 执行工具
        hooks.fire(POST_TOOL, result)  # 监控指标
    hooks.fire(POST_LOOP, messages)    # 压缩 + 记忆更新
```

---

## 2. Tool System 工具系统

**文件**: [`src/agent_cli/tools/`](src/agent_cli/tools/)

### 职责

- 提供统一的工具注册、发现和执行机制
- 将外部能力（文件操作、命令执行、网络请求等）包装为标准接口
- 通过 `ToolRegistry` 集中管理所有工具

### 架构

```
ToolRegistry (注册中心)
  ├── register(BaseTool)    # 注册工具
  ├── execute(name, args)   # 执行工具
  ├── list_tools() → specs  # 列出所有工具规范
  └── get_tool(name)        # 获取工具实例

BaseTool (抽象基类)
  ├── spec() → ToolSpec     # 工具元数据
  └── execute(**kwargs)     # 执行逻辑
```

### 内置工具一览

| 工具 | 文件 | 安全等级 | 功能 |
|:-----|:-----|:---------|:-----|
| `bash` | [`tools/bash.py`](src/agent_cli/tools/bash.py) | SENSITIVE | 执行 shell 命令 |
| `read` | [`tools/file.py`](src/agent_cli/tools/file.py) | SAFE | 读取文件 |
| `write` | [`tools/file.py`](src/agent_cli/tools/file.py) | SENSITIVE | 写入文件 |
| `edit` | [`tools/file.py`](src/agent_cli/tools/file.py) | SENSITIVE | 编辑文件（精确替换） |
| `glob` | [`tools/file.py`](src/agent_cli/tools/file.py) | SAFE | 文件模式匹配 |
| `grep` | [`tools/file.py`](src/agent_cli/tools/file.py) | SAFE | 文件内容搜索 |
| `web_fetch` | [`tools/web.py`](src/agent_cli/tools/web.py) | ALWAYS_ASK | 获取网页内容 |
| `agent` | [`tools/agent_tool.py`](src/agent_cli/tools/agent_tool.py) | ALWAYS_ASK | 启动子Agent |

### 工具规范 (ToolSpec)

```python
@dataclass
class ToolSpec:
    name: str              # 工具名（唯一标识）
    description: str       # 描述（LLM 选择工具的依据）
    parameters: dict       # JSON Schema 参数定义
    safety: SafetyLevel    # 安全等级
    extra: dict | None     # 扩展信息（如 MCP server 名）
```

### 扩展方式

```python
# 1. 继承 BaseTool
class MyTool(BaseTool):
    def spec(self) -> ToolSpec: ...
    def execute(self, **kwargs) -> Any: ...

# 2. 注册
registry.register(MyTool())
```

---

## 3. Permission System 权限体系

**文件**: [`src/agent_cli/permissions/`](src/agent_cli/permissions/)

### 职责

- 四级权限决策链：Allow / Deny / Ask / Always_Ask
- 提供持久化规则存储（permissions.json）
- 通过 PermissionHook 集成到 Agent Loop

### 架构

```
PermissionEngine (决策引擎)
  ├── check(tool_name, safety) → decision
  ├── allow(name) / deny(name) / always_ask(name)
  ├── revoke(name) / clear()
  └── get_rules() / get_stats()

PermissionHook (Hook 适配器)
  ├── check_tool(tool_call) → str | None
  └── PRE_TOOL 事件点集成
```

### 决策链

```
1. 自定义规则 (permissions.json)
   ├── allow       → ✅ 直接放行
   ├── deny        → ❌ 直接拒绝
   └── always_ask  → ⚠️ 强制询问
2. 工具安全等级（内置分类）
   ├── SAFE        → ✅ 放行
   ├── SENSITIVE   → ❓ 询问
   ├── DANGEROUS   → ❌ 拒绝
   └── ALWAYS_ASK  → ⚠️ 强制询问
3. 默认策略       → ❓ 询问
```

### CLI 接口

```bash
agent-cli permission --allow bash        # 永久允许
agent-cli permission --deny write        # 永久拒绝
agent-cli permission --always-ask agent  # 强制询问
agent-cli permission --list              # 查看规则
agent-cli permission --show bash         # 查看决策
agent-cli permission --status            # 查看引擎状态
```

---

## 4. Memory System 记忆系统

**文件**: [`src/agent_cli/memory/`](src/agent_cli/memory/)

### 职责

三级记忆架构，提供从短期到长期的递进式记忆能力。

```
MemoryManager (统一入口)
  ├── search(query) → 跨层检索
  ├── append(content) → 写入会话记忆
  └── write_note(name, content) → 写入文件记忆

层级:
├── FileMemory (文件级)
│   ├── 存储: .agent/memory/*.md (YAML frontmatter)
│   ├── 类型: user / feedback / project / reference
│   ├── 持久: 长期保存，可手动编辑
│   └── 能力: 创建 / 读取 / 搜索 / 更新 / 删除
│
├── SessionMemory (会话级)
│   ├── 存储: 运行时内存
│   ├── 持久: 会话期间
│   ├── 能力: 自动摘要、关键信息提取
│   └── 用途: 当前会话的工作上下文
│
└── ProjectMemory (项目级)
    ├── 存储: .agent/project.md
    ├── 持久: 长期
    ├── 能力: 全局项目知识管理
    └── 用途: 项目概况、技术决策记录
```

### 文件级记忆格式

```markdown
---
name: api-design-decision
description: RESTful API 设计决策记录
metadata:
  type: project
---

# API 设计决策

决定使用 Typer 作为 CLI 框架，理由：
1. 类型安全
2. 自动生成 --help
3. 14days-build 项目已验证

参考: [[provider-architecture]]
```

---

## 5. Context Management 上下文管理

**文件**: [`src/agent_cli/compact/pipeline.py`](src/agent_cli/compact/pipeline.py)

### 职责

在 Token 超限前自动压缩上下文，减少 API 消耗。L1-L3 零 API 成本，L4 使用 LLM。

### 四层压缩策略

```
Token 比率监控
        │
        ▼
┌─────────────────────────────────────┐
│  L1: 丢弃层                          │
│  - 截断 >2000 字符的 tool_result     │
│  - 跳过空的 tool_result 块           │
│  触发阈值: 70%                       │
└──────────┬──────────────────────────┘
           │ 仍 > 70%
           ▼
┌─────────────────────────────────────┐
│  L2: 合并层                          │
│  - 合并连续的 tool_result 消息       │
│  - 合并连续的 assistant text 消息    │
│  触发阈值: 90%                       │
└──────────┬──────────────────────────┘
           │ 仍 > 90%
           ▼
┌─────────────────────────────────────┐
│  L3: 摘要层                          │
│  - 保留最近 6 条消息                │
│  - 早期消息 → 结构化摘要            │
│  触发阈值: 90%                       │
└──────────┬──────────────────────────┘
           │ 仍 > 90% 且有 LLM
           ▼
┌─────────────────────────────────────┐
│  L4: 重写层（需 LLM Provider）       │
│  - 调用模型智能重写                  │
│  - 保持语义完整性                    │
│  触发阈值: 90%                       │
└─────────────────────────────────────┘
```

### 关键指标

```python
pipeline.get_stats()
# → {
#     "compression_count": 3,
#     "last_ratio": 0.85,
#     "max_tokens": 100000,
#     "compact_ratio": 0.7,
#     "critical_ratio": 0.9,
# }
```

---

## 6. Task Planning 任务规划

**文件**: [`src/agent_cli/planning/`](src/agent_cli/planning/)

### 职责

- 从自然语言或 JSON 创建任务计划
- 任务状态机管理（pending → approved → in_progress → completed/failed）
- 拓扑排序依赖管理
- JSON 持久化

### 数据结构

```python
@dataclass
class TodoItem:
    id: str                   # 任务 ID（如 "t1", "t2"）
    title: str                # 任务标题
    description: str          # 详细描述
    status: TaskStatus        # pending / approved / in_progress / completed / failed
    dependencies: list[str]   # 依赖的任务 ID 列表
    assignee: str | None      # 负责人
    created_at: str           # 创建时间
    completed_at: str | None  # 完成时间
```

### CLI 接口

```bash
# 创建计划
agent-cli plan "分析项目结构\n编写测试用例\n运行测试"

# 审批
agent-cli plan --approve

# 查看下一个任务
agent-cli plan --next

# 查看总结
agent-cli plan --summary

# 列出所有计划
agent-cli plan --list
```

---

## 7. Subagent System 子Agent系统

**文件**: [`src/agent_cli/subagent/manager.py`](src/agent_cli/subagent/manager.py)

### 职责

- 在独立上下文中运行子 Agent
- 共享宿主 Agent 的工具集
- 返回结构化结果

### 使用方式

```python
sub_mgr = SubagentManager(loop)
result = sub_mgr.spawn(
    prompt="搜索项目中所有的 TODO 注释",
    context={"focus": "代码"},
    tools=["read", "grep", "glob"],  # 限制子Agent可用的工具
)
print(result.text)
```

### 内部流程

```
1. 创建独立消息列表（复制系统消息）
2. 在隔离的 AgentLoop 中运行
3. 继承宿主工具集（可限制工具范围）
4. 返回完整结果（文本 + 工具调用记录）
```

---

## 8. Skill System 技能系统

**文件**: [`src/agent_cli/skills/`](src/agent_cli/skills/)

### 职责

- 按需加载专业技能文件
- 双模式触发：自动上下文匹配 + 手动命令
- 在 `PRE_LOOP` 阶段自动注入匹配的技能

### 技能文件格式

`.agent/skills/code-review.md`:

```markdown
---
name: code-review
description: 代码审查专家技能
triggers:
  - review
  - 审查
  - code review
---

# 代码审查技能

作为高级代码审查专家，你应该：
1. 先理解整体架构
2. 检查代码规范和风格
3. 寻找潜在 bug 和安全问题
4. 给出可操作的改进建议
...
```

### 匹配逻辑

```python
loader = SkillLoader(base_dir=".agent")
skills = loader.load_all()
matched = loader.find_matching("请审查这段代码")
# → 匹配 "code-review"（命中 triggers 中的 "审查"）
```

### CLI 接口

```bash
agent-cli skill --list                  # 列出所有技能
agent-cli skill --show code-review       # 查看技能内容
agent-cli skill --name "my-skill" \     # 创建技能
  --desc "..." --triggers "kw1,kw2" \
  --content "# 技能内容..."
agent-cli skill --delete my-skill       # 删除技能
```

---

## 9. Hook System 钩子系统

**文件**: [`src/agent_cli/hooks/manager.py`](src/agent_cli/hooks/manager.py)

### 职责

提供四个生命周期点，实现机制与核心循环的解耦。

### 生命周期点

```python
PRE_LOOP   # LLM 调用前：技能注入、记忆检索
POST_LOOP  # 单次循环后：上下文压缩、记忆更新
PRE_TOOL   # 工具执行前：权限检查
POST_TOOL  # 工具执行后：监控指标采集
```

### 接口

```python
hooks = HookManager()

# 注册 handler
hooks.on(PRE_LOOP, my_handler)

# 触发
hooks.fire(PRE_TOOL, tool_call)

# handler 签名
def my_handler(arg: Any) -> str | None:
    """返回 None 表示继续，返回字符串表示中断。"""
```

### 注册的默认 Hooks

| Hook | Handler | 来源 |
|:-----|:--------|:-----|
| `PRE_LOOP` | 技能注入 | `main.py:515` |
| `PRE_LOOP` | 监控指标 | `main.py:258` |
| `PRE_TOOL` | 权限检查 | `main.py:264` |
| `POST_TOOL` | 监控指标 | `main.py:259` |
| `POST_LOOP` | 监控指标 | `main.py:260` |

---

## 10. CLI / User Interaction 用户交互

**文件**: [`src/agent_cli/main.py`](src/agent_cli/main.py) + [`src/agent_cli/ui/`](src/agent_cli/ui/)

### 职责

- CLI 参数解析与分发（Typer）
- 输出格式化（normal / verbose / json）
- REPL 交互模式

### 命令结构

```
agent-cli
├── run        # 单次执行
├── repl       # 交互模式
├── init       # 初始化 .agent/
├── plan       # 任务规划
├── skill      # 技能管理
├── mcp        # MCP 工具
├── sessions   # 会话管理
├── memory     # 记忆管理
├── permission # 权限管理
└── swarm      # 多Agent协作
```

### 全局参数

| 参数 | 作用 |
|:-----|:------|
| `--version`, `-V` | 显示版本 |
| `--help` | 显示帮助 |

### 输出模式

| 模式 | 触发 | 说明 |
|:-----|:------|:------|
| normal | 默认 | 简洁输出 |
| verbose | `--verbose`, `-v` | 显示迭代次数、工具调用详情 |
| json | `--json`, `-j` | 结构化 JSON 输出 |

### REPL 命令

```
/exit, /quit              退出
/help, /?                 帮助
/save                     保存会话
/clear                    清空历史
/stats                    统计信息
/memory                   列出记忆
/sessions                 列出会话
/resume <id>              恢复会话
/metrics                  工具调用指标
/alerts                   告警记录
```

---

## 11. MCP Integration 外部工具协议

**文件**: [`src/agent_cli/mcp/`](src/agent_cli/mcp/)

### 职责

- 实现标准 MCP Client（stdio 传输）
- 动态发现并注册外部工具
- 外部工具与内置工具完全对等

### 架构

```
MCPToolBridge (桥接器)
  ├── load_config() → 从 .agent/mcp.json 加载
  ├── connect_all() → 建立所有连接
  ├── discover_tools() → 发现工具
  ├── register_tools(registry) → 注册到工具系统
  └── call_mcp_tool(name, kwargs) → 调用工具

MCPConnection (单连接管理)
  ├── connect() → 启动子进程 + initialize 握手
  ├── disconnect() → 发送 exit + terminate
  ├── list_tools() → tools/list 请求
  └── call_tool(name, args) → tools/call 请求

_MCPToolWrapper (适配器)
  ├── 将 MCP 工具包装为 BaseTool
  └── 注册到 ToolRegistry 后与其他工具无差别
```

### 配置示例

```json
{
  "mcp_servers": [
    {
      "name": "github",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "ghp_xxx"
      }
    }
  ]
}
```

### 协议

- JSON-RPC 2.0 over stdio
- 初始化版本: `2024-11-05`
- 方法: `initialize` / `tools/list` / `tools/call` / `exit`

---

## 12. Multi-Agent Collaboration 多Agent协作

**文件**: [`src/agent_cli/swarm/coordinator.py`](src/agent_cli/swarm/coordinator.py)

### 职责

提供四种多 Agent 编排模式，通过 SubagentManager 创建子 Agent。

### 四种模式

```
顺序执行 (Sequential)
  [任务A] → [任务B] → [任务C]
  结果依次传递，每个任务接收前一个的输出

并行执行 (Parallel)
  [任务A]
  [任务B]  同时执行，各自返回结果
  [任务C]

投票模式 (Vote)
  [投票1]  [投票2]  [投票3]
  同一问题，多个 Agent 独立回答
  统计共识: agreement / disagreement / consensus

辩论模式 (Debate)
  正方R1 → 反方R1
     ↓        ↓
  正方R2 → 反方R2
     ↓        ↓
      最终总结
```

### Coordinator 接口

```python
coord = Coordinator(sub_mgr)

# 顺序执行
result = coord.sequential(["任务1", "任务2", "任务3"])

# 并行执行
result = coord.parallel(["搜索TODO", "搜索FIXME", "搜索BUG"])

# 投票
result = coord.vote("这个方案可靠吗？", voters=5)

# 辩论
result = coord.debate("微服务还是单体？", rounds=3)
```

---

## 13. Error Handling 错误处理

### 设计原则

1. **永不静默失败** — 所有异常至少记录日志
2. **用户可见的错误格式化输出** — 不裸抛 traceback
3. **Graceful Degradation** — 单个工具失败不影响整个循环

### 异常处理层次

```
CLI 层 (main.py)
├── try/except 包裹 loop.run()
├── KeyboardInterrupt → 干净退出 (exit 130)
└── Exception → 格式化错误信息 + stderr

Agent Loop 层 (loop.py)
├── 单步异常 → 记录日志，跳过该步
├── 权限拒绝 → 返回提示信息，不崩溃
└── max_iterations → 返回部分结果

工具层
├── BaseTool.execute() 异常 → 返回 ToolResult.error
└── 网络/文件异常 → 向上传递
```

### 错误消息格式

```python
# 正常错误
print(format_result(f"运行失败: {e}"), file=sys.stderr)

# 用户中断
print("\n\n[interrupt] 用户中断")

# 权限拒绝
return "❌ 权限拒绝: 工具 'bash' 已被禁止使用。"
```

---

## 14. Session / Persistence 会话与持久化

**文件**: [`src/agent_cli/session/store.py`](src/agent_cli/session/store.py)

### 职责

- 会话的创建、保存、加载、删除、归档
- JSONL 格式持久化（每行一条消息）
- 会话搜索与恢复

### 数据结构

```jsonl
{"role": "system", "content": "你是 Agent-CLI，一个轻量级个人助手...", "timestamp": "2026-06-11T10:00:00"}
{"role": "user", "content": "分析项目结构", "timestamp": "2026-06-11T10:00:05"}
{"role": "assistant", "content": "我来分析项目结构...", "tool_calls": [...], "timestamp": "2026-06-11T10:00:10"}
```

### SessionStore 接口

```python
store = SessionStore(base_dir=".agent")

store.create()                          # 创建新会话 → session_id
store.save(session_id, messages)        # 保存（追加）
store.load(session_id) → list          # 加载完整会话
store.delete(session_id) → bool        # 删除
store.archive(session_id) → bool       # 归档（移到 archives/）
store.list_sessions() → list[dict]     # 列出所有会话
store.search(keyword) → list           # 关键词搜索
```

### 会话生命周期

```
创建 create()
  │
  ▼
活跃 (save/load)
  │
  ├── 删除 delete() ──→ 🗑 移除
  │
  └── >24h 或手动归档 archive() ──→ 📦 archives/
```

### CLI 接口

```bash
agent-cli sessions --list              # 列出所有会话
agent-cli sessions --show <id>         # 查看会话内容
agent-cli sessions --delete <id>       # 删除会话
agent-cli sessions --archive <id>      # 归档会话

# 使用 --resume 恢复
agent-cli run --resume <id> "继续"
agent-cli repl --resume <id>
```
