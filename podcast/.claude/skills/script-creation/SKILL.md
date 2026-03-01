---
name: script-creation
description: 乐乎玄学馆播客稿件创作工作流，自动生成并审核至达标
allowed-tools: Read, Bash, WebFetch, Task
argument-hint: "[URL or text]"
---

## 任务
将输入内容扩展为5000-8000字的「乐乎玄学馆」深度播客对话稿，经审核达标后输出。

## 流程

### Step 1：准备素材
- 如果 `$ARGUMENTS` 是 URL → 调用 transcription skill 转录
- 如果是文本 → 直接使用

### Step 2：生成初稿
调用 writer agent，传入素材，要求按以下架构生成：

1. **Hook（黄金3分钟）**：尖锐痛点或反直觉真相，承诺认知升级
2. **现象层**：用占星符号+心理学术语描述常见困境
3. **根因层**：古典占星（土星回归、南北交点、宫位）+ 心理学（原生家庭、阴影、投射）
4. **翻转与升华**：将"厄运"重构为发展阶段，从"命运"升华到"灵魂进化"
5. **行动建议**：3-5条具体可执行的建议 + 下期预告钩子

### Step 3：审核
调用 reviewer agent，按 [standards.md](standards.md) 审核。

### Step 4：循环改进
- 审核通过（≥48/60）→ 输出终稿
- 未通过 → 将审核意见发回 writer agent 修改
- 最多循环 3 轮

### Step 5：输出格式
```
# 乐乎玄学馆 EP[XX]: [标题]
BGM: (建议)

**小狗仔**: ...
**小刀**: ...
```
