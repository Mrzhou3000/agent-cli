# Changelog

## [0.2.0] — 2026-06-11

### Added
- **集成测试**：首次引入 VCR 录制/回放集成测试，5 个 DeepSeek 真实模型测试用例（`tests/integration/`）
- **CLI E2E 测试**：补齐 `run` 命令 7 个 + `swarm` 命令 7 个 CliRunner 测试用例
- **多模型切换**：`--provider` / `--api-key` / `--base-url` CLI 参数，支持 auto / anthropic / compatible / mock 四种模式
- **兼容 API 支持**：`CompatibleProvider` 支持 DeepSeek、OpenAI 等兼容 API，含 SSE 流式输出
- **技能系统**：双模式触发（自动上下文匹配 + `/skill` 命令），技能文件按需注入系统消息
- **上下文压缩**：L1-L4 四层渐进式压缩，前三层零 API 成本
- **多 Agent 协作**：Coordinator 模式 — 顺序 / 并行 / 投票 / 辩论四种编排
- **子 Agent 系统**：独立上下文 + 共享工具集 + 结构化结果
- **Hook 系统**：PRE_LOOP / POST_LOOP / PRE_TOOL / POST_TOOL 四个生命周期点
- **监控告警**：P0-P3 四级告警 + 工具调用统计 + Token 追踪
- **MCP Bridge**：JSON-RPC over stdio 外部工具协议

### Changed
- 测试覆盖率从 46% → 90%（582 测试通过）
- README 更新为 v0.2.0 文档
- 完善架构详解（`docs/architecture.md`）和模块详解（`docs/modules.md`）

### Fixed
- pre-commit ruff 版本与 CI 同步（v0.5.0 → v0.15.16）
- 19 个测试文件的 import 排序问题
- CompactPipeline provider 参数传递

## [0.1.0] — 2026-06-10

### Added
- 完整项目框架初始提交
- CI/CD workflow 和 pre-commit 配置
- 核心 Agent Loop（~60 行）
- Provider 抽象层（Mock / Anthropic / Compatible）
- 8+ 内置工具（Bash / Read / Write / Edit / Glob / Grep / WebFetch / Agent）
- 四级权限管理（Allow / Deny / Ask / Always_Ask）
- 三级记忆架构（文件级 + 会话级 + 项目级）
- JSONL 会话持久化（`--resume` 恢复，关键词搜索，自动归档）
- REPL 交互模式（含 12+ 内置命令）
- 任务规划与审批闭环（TodoItem 状态机 + 拓扑排序依赖）
- 测试覆盖 46%（339 测试用例）
