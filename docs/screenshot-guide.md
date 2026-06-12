# README 演示截图/GIF 制作指南

> **目标**：给 README 加一张「定妆照」，让面试官打开 GitHub 第一眼就看到项目在运行

---

## 方案一：截图（最简单，5 分钟）

1. **打开终端**，运行 Agent-CLI：
   ```bash
   agent-cli run "分析当前项目结构" --verbose
   ```
   或者更酷炫的：
   ```bash
   agent-cli run "请帮我分析项目中的 TODO 和 FIXME，并按优先级排序" --verbose
   ```
   （如果 `agent-cli` 没安装，用 `uv run agent-cli` 代替）

2. **截图**：按 `Win + Shift + S`，框选终端窗口

3. **保存**：把截图保存为 `docs/demo.png`

4. **效果**：README 里的图片链接会自动展示这张截图

---

## 方案二：VHS 动画 GIF（更酷，但需要装工具）

[VHS](https://github.com/charmbracelet/vhs) 是 Charmbracelet 出的终端录制工具，可以把录制的「剧本」转成 GIF。

### 安装 VHS

```bash
# 需要先安装 Go（https://go.dev/dl/）
go install github.com/charmbracelet/vhs@latest

# 或者从 GitHub Releases 下载 exe
# https://github.com/charmbracelet/vhs/releases
```

### 录制剧本

`docs/demo.tape` 文件已经帮你写好了，直接运行：

```bash
cd docs
vhs demo.tape
```

会生成 `docs/demo.gif`。如果效果不满意，调整 `demo.tape` 里的 Sleep 时间。

---

## README 图片链接

README 里的图片标签已经预留好了，你只需要把截图/GIF 放到 `docs/` 目录下，命名为 `demo.png` 或 `demo.gif` 即可。

默认用 PNG，如果你做了 GIF，把 README 里的 `demo.png` 改成 `demo.gif`。
