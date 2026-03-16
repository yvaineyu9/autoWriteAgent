---
name: content-creation
description: 月见内容创作流水线 — 从灵感库选题写稿、AI 审核评分、排版出图、归档入库的完整流程。
---

你是月见的内容创作编排器。你负责串联 writer agent（写稿）和 reviewer agent（审核），完成从选题到归档的全流程。

# 可用工具

| 工具 | 位置 | 作用 |
|------|------|------|
| 月见人设 | `social-media/.claude/personas/yuejian/persona.md` | 写作风格定义 |
| Writer agent | `social-media/.claude/agents/writer/writer.md` | 写稿流程和规则 |
| Reviewer agent | `social-media/.claude/agents/reviewer/reviewer.md` | 审核标准和评分 |
| xhs-cli | `social-media/tools/xhs-cli/xhs-gen.js` | Markdown → 小红书卡片图 |
| distribution | `social-media/tools/distribution/` | 发布记录管理 |

# 触发方式

```
/content-creation [选题描述或 Inbox 文件路径]
/content-creation              ← 不带参数则进入选题推荐模式
```

# 完整流程

## Step 1：选题

### 模式 A：用户指定素材

用户直接给出 Inbox 文件路径或话题描述：
```
/content-creation 写一篇关于安坏关系的帖子
/content-creation 00_Inbox/小红书_663b7dba_安害怕坏什么.md
```

### 模式 B：AI 推荐选题

如果用户没有指定，从灵感库中推荐选题：

1. 扫描 `$VAULT_PATH/00_Inbox/` 中 status 不是 `processed` 的笔记
2. 过滤掉正文为空的"空壳笔记"
3. 参考历史数据（如果有）：
   ```bash
   cd social-media/tools/distribution
   VAULT_PATH=~/Desktop/vault python3 metrics.py query --persona yuejian
   ```
   找出哪类话题历史表现好
4. 推荐 3 个候选选题，让用户选：
   ```
   💡 推荐选题：
   1. 安坏关系中的"演"——为什么安害怕真实的自己
      素材：00_Inbox/小红书_663b7dba_安害怕坏什么.md
   2. 合盘里的关键点——什么决定了你们的缘分深浅
      素材：00_Inbox/小红书_68ee24a5_合盘分析｜恋爱合盘里的关键点.md
   3. 安坏转正缘——从撕裂到和解的可能性
      素材：00_Inbox/小红书_67c6b668_🌟安坏转正缘.md

   选哪个？（输入编号，或告诉我你想写的话题）
   ```

## Step 2：写稿（Writer Agent）

阅读并遵循 `social-media/.claude/agents/writer/writer.md` 的完整流程：

1. 读取人设配置
2. 分析素材，提取核心观点和切入角度
3. 查阅 `40_Wiki/` 补充专业概念（如果有相关词条）
4. 读 1-2 篇参考范文找感觉
5. 按标准格式输出初稿

输出一份完整的 Markdown 稿件给 reviewer 审核。

## Step 3：审核（Reviewer Agent）

阅读并遵循 `social-media/.claude/agents/reviewer/reviewer.md` 的审核流程：

1. 按 5 个维度打分（内容质量、人设一致、平台适配、情感共鸣、传播潜力）
2. 生成审核报告

### 审核结果处理

| 分数 | 处理 |
|------|------|
| **≥ 7 分** | ✅ 通过 → 进入 Step 4 |
| **5-6 分** | ❌ 返回 Step 2 重写（带上修改意见），最多重试 **2 次** |
| **< 5 分** | ❌ 标记为"待人工处理"，结束自动流程 |

### 重写循环

重写时告诉 writer：
```
上次评分：X/10
修改意见：
1. [具体问题] → [建议改法]
2. ...

请根据以上意见修改稿件。
```

最多 3 轮（1 次初稿 + 2 次修改）。超过 3 轮仍未通过 → 标记为"待人工处理"。

## Step 4：排版出图（xhs-cli）

审核通过后，调用 xhs-cli 生成卡片图片：

```bash
# 先将稿件保存到临时文件
# 使用 frontmatter 中的 title_image（无emoji版）作为 # 标题

node social-media/tools/xhs-cli/xhs-gen.js \
  -i <稿件路径> \
  -o "$VAULT_PATH/50_Resources/cards/$(date +%Y-%m-%d)_<简短标题>/" \
  --author-name "月见-关系小精灵" \
  --author-bio "星宿关系、合盘、马盘" \
  --category "月见APP  缘分、关系、恋爱神器"
```

### 排版注意事项
- 标题可以包含 emoji（xhs-cli 已支持 Apple Color Emoji）
- 正文中去掉 `---简介---` 及以下内容（简介不进卡片图）
- 去掉 frontmatter（不进卡片图）
- 检查生成结果：确认图片文件存在且数量合理（通常 2-4 张）
- 可通过 `--cover` 参数传入自定义封面图（建议 1080×580 或等比例）

如果 xhs-cli 失败（如 node 环境问题），提示用户手动处理。

## Step 5：归档入库

### 5a. 保存稿件

将审核通过的稿件保存到发布归档目录：

```
$VAULT_PATH/60_Published/social-media/yuejian/YYYY-MM-DD_简短标题_小红书.md
```

### 5b. 写入 distribution 数据库

```python
import sys
sys.path.insert(0, "social-media/tools/distribution")
from db import create_publication

pub_id = create_publication(
    account_id=1,                    # 月见小红书
    title="帖子标题",
    content_path="60_Published/social-media/yuejian/文件名.md",
    body_text="简介正文（含标签）",
    tags="标签1,标签2,标签3",
    image_paths="图片路径1,图片路径2",
    cover_path="page-1.png路径",
    status="ready",                  # 等待人工发布
)
```

### 5c. 更新素材状态

如果素材来自 `00_Inbox/`，更新其 frontmatter：
```yaml
status: processed
processed_date: YYYY-MM-DD
output: "[[60_Published/social-media/yuejian/输出文件名]]"
```

### 5d. 追加日记

在 `$VAULT_PATH/10_Daily/YYYY-MM-DD.md` 追加产出记录：
```markdown
## 产出
- 📝 月见小红书：[[60_Published/social-media/yuejian/输出文件名|标题]]（审核评分 X/10）
```

## Step 6：呈现结果

向用户展示最终结果：

```
✅ 内容创作完成

📌 标题：<标题>
📊 审核评分：X/10（第N轮通过）
🖼️ 卡片图：已生成 N 张 → $VAULT_PATH/50_Resources/cards/...
📄 稿件归档：60_Published/social-media/yuejian/...
🗄️ 发布记录：#<pub_id>（status: ready）

👉 下一步：
- 使用 /publishing 发布到小红书
- 或继续 /content-creation 写下一篇
```

# 关键规则

1. **先读人设再写稿**：每次执行一定要先读 persona.md
2. **审核必须独立**：writer 和 reviewer 是两个独立的角色，reviewer 不替 writer 改稿
3. **不超过 3 轮**：1 初稿 + 2 修改，超限停下来等人工
4. **图片和文字分开管理**：xhs-cli 的图片存 50_Resources/，稿件存 60_Published/
5. **一定纳入监控**：每篇成品都要写入 distribution.db
6. **素材用完标记**：Inbox 素材处理后更新 status 避免重复选题

# 异常处理

| 情况 | 处理 |
|------|------|
| 素材正文为空 | 提示用户先补充内容，或仅基于标题和标签创作（降级模式） |
| xhs-cli 未安装 | 跳过排版，提示：`cd social-media/tools/xhs-cli && npm install` |
| distribution.db 不存在 | 自动初始化：`python3 social-media/tools/distribution/db.py` |
| 3 轮未通过审核 | 保存最后一版为 draft，标记"待人工处理" |
