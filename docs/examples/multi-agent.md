# 多Agent协作示例

## 1. 顺序执行

任务依次执行，前一个结果传递给下一个：

```bash
# 分步分析
uv run agent-cli swarm --sequential "分析项目结构\n列出所有依赖\n生成架构报告"

# 需要详细结果
uv run agent-cli swarm --sequential "搜索 FIXME\n分析严重程度\n给出修复建议" --verbose
```

## 2. 并行执行

所有任务同时执行，适合独立探索：

```bash
# 同时搜索多种模式
uv run agent-cli swarm --parallel "搜索 TODO\n搜索 FIXME\n搜索 HACK\n搜索 XXX"

# 多角度分析
uv run agent-cli swarm --parallel "分析代码复杂度\n检查安全漏洞\n审查依赖版本"
```

## 3. 投票模式

多个 Agent 独立回答同一问题：

```bash
# 代码审查投票
uv run agent-cli swarm --vote "当前代码质量是否达到发布标准？"

# 自定义投票者数量
uv run agent-cli swarm --vote "应该重构这个模块吗？" --voters 5

# 架构决策
uv run agent-cli swarm --vote "微服务架构适合这个项目吗？" --voters 3
```

## 4. 辩论模式

正反双方多轮辩论：

```bash
# 基本辩论（2轮）
uv run agent-cli swarm --debate "我们应该用 Python 还是 Rust？"

# 自定义轮数
uv run agent-cli swarm --debate "AI 会取代程序员吗？" --rounds 3

# 技术选型辩论
uv run agent-cli swarm --debate "PostgreSQL 还是 MongoDB？" --rounds 2
```

## 5. Python SDK 调用

```python
"""多Agent协作示例脚本。"""
from agent_cli.core.loop import AgentLoop
from agent_cli.core.provider import MockProvider
from agent_cli.subagent.manager import SubagentManager
from agent_cli.swarm.coordinator import Coordinator
from agent_cli.tools.registry import ToolRegistry

# 初始化
provider = MockProvider()
tools = ToolRegistry()
loop = AgentLoop(provider=provider, tools=tools)
sub_mgr = SubagentManager(loop)
coord = Coordinator(sub_mgr)

# 顺序执行
result = coord.sequential([
    "收集项目信息",
    "分析代码质量",
    "生成改进建议",
])
print(f"完成: {result.success_count}/{len(result.results)}")

# 并行探索
result = coord.parallel([
    "搜索安全问题",
    "搜索性能问题",
    "搜索代码异味",
])
for r in result.results:
    if r.success:
        print(r.task[:30], "→", r.output[:100])

# 投票
vote = coord.vote("这个方案可行吗？", voters=3)
print(f"投票结果: {vote.agreement} 同意 / {vote.disagreement} 反对")
```
