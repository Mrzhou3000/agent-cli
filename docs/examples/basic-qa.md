# 基础使用示例

## 1. 命令行模式

```bash
# 简单问答
uv run agent-cli run "你好，请介绍一下自己"

# 执行 Bash 命令
uv run agent-cli run "查看当前目录的文件结构"

# 读写文件
uv run agent-cli run "创建一个 test.txt，写入 Hello World"

# 搜索代码
uv run agent-cli run "搜索项目中所有的 FIXME 注释"

# 获取网页内容
uv run agent-cli run "获取 https://example.com 的内容"
```

## 2. 详细/JSON 输出

```bash
# 详细模式（显示迭代次数和工具调用
uv run agent-cli run --verbose "列出当前目录的文件"

# JSON 模式（结构化输出
uv run agent-cli run --json "查看系统时间"
```

## 3. 会话恢复

```bash
# 先运行一次（记录会话 ID
uv run agent-cli run "分析项目结构"

# 列出所有会话
uv run agent-cli sessions --list

# 恢复指定会话继续对话
uv run agent-cli run --resume sess_20260610_143022_abc123 "继续刚才的分析"
```

## 4. REPL 交互模式

```bash
# 启动 REPL
uv run agent-cli repl

# 带记忆启动
uv run agent-cli repl --memory

# 恢复会话
uv run agent-cli repl --resume sess_20260610_143022_abc123

# REPL 内命令:
# >>> 直接输入文本与 Agent 对话
# >>> /stats    查看统计
# >>> /sessions 列出会话
# >>> /resume <id> 恢复会话
# >>> /metrics  查看工具调用指标
# >>> /exit     退出
```

## 5. 权限管理

```bash
# 查看当前权限规则
uv run agent-cli permission --list

# 永久允许 bash 工具
uv run agent-cli permission --allow bash

# 永久拒绝 write 工具
uv run agent-cli permission --deny write

# 设置 web_fetch 为总是询问
uv run agent-cli permission --always-ask web_fetch

# 查看权限引擎状态
uv run agent-cli permission --status

# 撤销规则
uv run agent-cli permission --revoke bash
```

## 6. 任务规划

```bash
# 从自然语言创建计划
uv run agent-cli plan "分析项目结构\n编写测试用例\n运行测试"

# 审批通过
uv run agent-cli plan --approve

# 查看下一个可执行任务
uv run agent-cli plan --next

# 查看执行总结
uv run agent-cli plan --summary

# 列出所有计划
uv run agent-cli plan --list
```
