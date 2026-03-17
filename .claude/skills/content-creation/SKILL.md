---
name: content-creation
description: 多人设内容创作流水线 — 选题 → 写稿 → AI审核 → 排版出图 → 归档入库。支持任意人设和平台。
---

你是内容创作编排器。你根据指定的**人设**和**平台**，串联 writer agent 和 reviewer agent，完成从选题到归档的全流程。

# 参数

```
/content-creation --persona <persona_id> [--platform <platform>] [选题描述或Inbox文件路径]
```

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--persona` | ✅ | — | 人设标识：`yuejian`、`chongxiaoyu` 等 |
| `--platform` | ❌ | `xiaohongshu` | 目标平台 |
| 选题 | ❌ | AI 推荐 | Inbox 文件路径或话题描述 |

# 配置文件位置

所有配置都在 `social-media/.claude/personas/{persona_id}/` 下：

| 文件 | 作用 |
|------|------|
| `persona.md` | 核心人设（风格/受众/价值观） |
| `platforms/{platform}.md` | 平台排版规则和模板 |
| `xhs-cli.json` | xhs-cli 参数预设 |

# 完整流程

## Step 1：参数校验

1. 检查 `social-media/.claude/personas/{persona_id}/` 目录是否存在
2. 检查 `platforms/{platform}.md` 是否存在
3. 如果缺失，提示用户：可以从 `_template/` 复制创建

## Step 2：选题

### 模式 A：用户指定素材
```
/content-creation --persona yuejian 00_Inbox/小红书_663b7dba_安害怕坏什么.md
```

### 模式 B：AI 推荐
扫描 `$VAULT_PATH/00_Inbox/` 中未处理的笔记，推荐 3 个候选，让用户选。

可参考历史数据优化推荐：
```bash
cd social-media/tools/distribution
VAULT_PATH=~/Desktop/vault python3 metrics.py query --persona {persona_id}
```

## Step 3：写稿（Writer Agent）

遵循 `social-media/.claude/agents/writer/writer.md`，传入：
- `persona_id` → 读取对应 persona.md
- `platform` → 读取对应 platforms/{platform}.md
- 素材内容
- 可查阅 `$VAULT_PATH/60_Published/{persona_id}/{platform}/` 下的参考范文

## Step 4：审核（Reviewer Agent）

遵循 `social-media/.claude/agents/reviewer/reviewer.md`，传入同样的 `persona_id` 和 `platform`。

| 分数 | 处理 |
|------|------|
| ≥ 7 | ✅ 通过 → Step 5 |
| 5-6 | ❌ 返回 Step 3 重写（最多重试 2 次） |
| < 5 | ❌ 标记"待人工处理" |

## Step 5：排版出图

### 小红书平台（xhs-cli）

从 `social-media/.claude/personas/{persona_id}/xhs-cli.json` 读取参数预设：

```bash
# 读取预设
XHS_PRESET=$(cat social-media/.claude/personas/{persona_id}/xhs-cli.json)

node social-media/tools/xhs-cli/xhs-gen.js \
  -i <稿件路径> \
  -o "$VAULT_PATH/60_Published/{persona_id}/{platform}/YYYY-MM-DD_标题/" \
  --author-name "$(echo $XHS_PRESET | jq -r '.["author-name"]')" \
  --author-bio "$(echo $XHS_PRESET | jq -r '.["author-bio"]')" \
  --category-left "$(echo $XHS_PRESET | jq -r '.["category-left"]')" \
  --category-slogan "$(echo $XHS_PRESET | jq -r '.["category-slogan"]')"
```

### 其他平台
跳过排版步骤，直接归档稿件。

## Step 6：归档入库

### 6a. 保存稿件

```
$VAULT_PATH/60_Published/{persona_id}/{platform}/YYYY-MM-DD_标题/content.md
```

图片和稿件放在同一个目录下（一帖一文件夹）。

### 6b. 写入 distribution 数据库

```python
import sys, json
sys.path.insert(0, "social-media/tools/distribution")
from db import get_conn, create_publication

# 查找该人设对应的 account_id
conn = get_conn()
account = conn.execute(
    "SELECT a.id FROM accounts a WHERE a.persona_id = ? AND a.platform = ?",
    (persona_id, platform)
).fetchone()

pub_id = create_publication(
    account_id=account["id"],
    title="标题",
    content_path=f"60_Published/{persona_id}/{platform}/YYYY-MM-DD_标题/content.md",
    status="ready",
    # ... 其他字段
)
```

### 6c. 更新素材 status + 追加日记

同原有逻辑。

## Step 7：呈现结果

```
✅ 内容创作完成

👤 人设：{persona_id}
📌 标题：<标题>
📊 审核评分：X/10
🖼️ 卡片图：N 张 → 60_Published/{persona_id}/{platform}/YYYY-MM-DD_标题/
🗄️ 发布记录：#{pub_id}（status: ready）

👉 下一步：/publishing --persona {persona_id}
```

# 关键规则

1. **先校验参数再执行**：persona_id 和 platform 目录不存在直接报错
2. **人设切换要彻底**：不同人设的审美、语调完全不同
3. **一帖一文件夹**：稿件和图片放在同一目录
4. **DB 按 persona_id + platform 查 account_id**：不写死数字
5. **最多 3 轮**：1 初稿 + 2 修改

# 异常处理

| 情况 | 处理 |
|------|------|
| persona 目录不存在 | 提示：`cp -r _template/ personas/新人设/` |
| platform 配置不存在 | 提示缺少平台配置文件 |
| DB 中无对应账号 | 提示注册：`python3 db.py` 手动添加 |
| xhs-cli 未安装 | `cd social-media/tools/xhs-cli && npm install` |
