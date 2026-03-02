---
name: content-creation
description: 社媒内容创作工作流，自动生成文案并经过审核达标后归档到仓库
allowed-tools: Read, Bash, WebFetch, Task, Write, Edit
argument-hint: "[主题或素材]"
---

## 任务
根据输入的主题或素材，生成社媒平台的内容文案，经过审核达标后归档到仓库。

## 素材读取

在开始生产前，根据输入判断素材来源：
- 如果用户给了仓库中的文件路径 → 从对应目录读取（`00_Inbox/`、`30_Research/`、`50_Resources/`）
- 如果用户给了外部 URL 或文本 → 直接使用
- 主动搜索 `40_Wiki/` 中与主题相关的知识词条作为参考
- 如果 `20_Project/` 中有相关项目 → 读取项目上下文了解整体方向

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

### Step 5：产出归仓

审核通过后，执行以下归仓操作：

1. **成品归档**：将终稿写入 `60_Published/social-media/YYYY-MM-DD_<标题>.md`
   - 文件内容包含：正文文案、hashtag、发布建议、审核分数
2. **项目状态回写**：如果 `20_Project/` 中存在对应项目文件
   - 在该项目 Progress 段追加：`- [YYYY-MM-DD] 完成社媒文案：<标题>`
   - 如果不存在对应项目，跳过此步
3. **每日记录**：在 `10_Daily/YYYY-MM-DD.md` 追加产出记录
   - 格式：`- 完成社媒文案：[[YYYY-MM-DD_<标题>]]，审核分数 XX/60`
   - 如果当日文件不存在，基于 `99_System/templates/daily.md` 创建

### Step 6：输出确认
向用户报告：
- 终稿内容预览
- 归档路径
- 审核分数
