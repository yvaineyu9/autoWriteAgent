---
name: content-creation
description: 社媒内容创作工作流，自动生成文案并经过审核达标后输出
allowed-tools: Read, Bash, WebFetch, Task
argument-hint: "[主题或素材]"
---

## 任务
根据输入的主题或素材，生成社媒平台的内容文案，经过审核达标后输出。

## 流程

### Step 1：分析素材
- 理解输入内容的核心主题
- 确定目标平台（IG / 小红书 / 微博等）

### Step 2：生成初稿
调用 writer agent，传入素材和平台要求，生成文案。

### Step 3：审核
调用 reviewer agent，按 [standards.md](standards.md) 的标准审核。

### Step 4：循环改进
- 审核通过（≥48/60）→ 输出终稿
- 未通过 → 将审核意见发回 writer agent 修改
- 最多循环 3 轮

### Step 5：输出
输出终稿内容，包含：
- 正文文案
- 推荐的 hashtag
- 发布建议（时间、互动引导语）
