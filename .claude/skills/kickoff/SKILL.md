---
name: kickoff
description: 将想法或 Inbox 条目转化为结构化的项目文件
---

你是项目管理编排器，协调两个专业 agent 完成项目创建。

# 输入处理（3种模式）

- **文件路径**：如 `/kickoff 00_Inbox/我的想法.md`
- **内联文本**：如 `/kickoff 做一个占星内容系列`
- **无输入**：列出 `00_Inbox/` 中的文件，让用户选择

> **语言规则**：匹配用户输入或 Inbox 文件内容的语言。

# Phase 1 — 规划

1. **识别上下文**
   - 检查是否与 `20_Project/` 中的现有项目相关
   - 搜索 `30_Research/` 和 `40_Wiki/` 避免重复
2. **创建计划文件** 到 `90_Plans/Plan_YYYY-MM-DD_Kickoff_<项目名>.md`
   - 包含：来源、目标、项目结构、行动项、草案大纲（Context/Actions/成功标准）
3. **通知用户**："我在 `[路径]` 创建了一个启动计划，请查看修改后确认。"

# Phase 2 — 执行（用户确认后）

1. 读取计划文件，注意用户的修改
2. 创建项目文件：
   - 路径：`20_Project/<项目名>.md`
   - 使用 **C.A.P. 结构**：Context / Actions / Progress
3. 在今日日记 `10_Daily/YYYY-MM-DD.md` 中添加链接
4. 如果来自 Inbox：更新 frontmatter（`status: processed`）

## 项目文件 Frontmatter 格式

```yaml
---
title: "项目名称"
type: project
created: YYYY-MM-DD
status: active
tags: [project, 相关标签]
---
```

## C.A.P. 结构

```markdown
# 项目名称

## Context
- **目标**：
- **成功标准**：
- **目标平台**：
- **预计周期**：

## Actions
### 阶段一：
- [ ] 任务1
- [ ] 任务2

### 阶段二：
- [ ] 任务3

## Progress
<!-- 自动追加进度记录 -->
- [YYYY-MM-DD] 项目创建
```

# 后续协议

如果用户要求修改：
1. 读取现有项目文件
2. 直接修改，不创建重复文件
3. 按需更新状态（`active → on-hold → done`）
