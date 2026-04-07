# Vault 改造方案：只读 Obsidian 视图

> **原则**：`data/` 是唯一数据源，vault 是由 `tools/sync_vault.py` 从 DB + 文件系统**单向生成**的 Obsidian 只读视图。

---

## 一、数据流向

```
写入方向（唯一）：
  /create, /collect, /publish, /daily
      ↓
  tools/*.py（inbox.py, archive.py, publish.py, daily.py …）
      ↓
  data/autowrite.db  +  data/content/（文件）


读取方向（只读视图）：
  data/autowrite.db  +  data/content/
      ↓
  tools/sync_vault.py（单向同步脚本）
      ↓
  vault/（Obsidian 打开这个目录）
```

**绝对不能**：在 Obsidian 里编辑 vault 内的文件来影响数据——改了也会被下次 sync 覆盖。

---

## 二、新 Vault 目录结构

```
vault/
│
├── .obsidian/                             # Obsidian 配置（手动维护，sync 不碰）
│
├── 00_看板/                               # 自动生成的总览页面
│   ├── 内容总览.md                         #   所有成品按状态分组
│   ├── 灵感池.md                           #   所有灵感按状态/来源分组
│   ├── 发布追踪.md                         #   已发布内容 + metrics 数据
│   └── 每日回顾.md                         #   最近 7 天 daily 汇总
│
├── 10_灵感/                               # ← data/content/inbox/
│   ├── <idea_id_1>.md
│   ├── <idea_id_2>.md
│   └── ...
│
├── 20_内容/                               # ← data/content/<content_id>/
│   ├── yuejian/
│   │   ├── xiaohongshu/
│   │   │   ├── 20260312_吵架时变成陌生人的你/
│   │   │   │   ├── content.md              #   frontmatter(DB) + 正文(文件)
│   │   │   │   ├── page-1.jpg              #   附件原样复制
│   │   │   │   └── page-2.jpg
│   │   │   └── 20260318_3个信号判断他是不是在消耗你/
│   │   │       └── content.md
│   │   └── wechat/
│   │       └── ...
│   └── chongxiaoyu/
│       ├── xiaohongshu/
│       │   └── ...
│       ├── wechat/
│       ├── twitter/
│       └── podcast/
│
├── 30_知识库/                              # ← data/knowledge/
│   ├── wiki/
│   └── research/
│
└── 40_日记/                               # ← daily_logs 表
    ├── 2026-03-02.md
    ├── 2026-03-12.md
    └── ...
```

### 与旧 vault 的映射关系

| 旧 vault | 新 vault | 数据来源 |
|----------|---------|---------|
| `00_Inbox/` | `10_灵感/` | `ideas` 表 + `data/content/inbox/*.md` |
| `60_Published/social-media/<p>/<pl>/` | `20_内容/<p>/<pl>/` | `contents` 表 + `data/content/<content_id>/` |
| `30_Research/` | `30_知识库/research/` | `data/knowledge/research/` |
| `40_Wiki/` | `30_知识库/wiki/` | `data/knowledge/wiki/` |
| `10_Daily/` | `40_日记/` | `daily_logs` 表 |
| `内容健康看板.md` + `.base` | `00_看板/内容总览.md` | sync 脚本生成 |
| `月见发布看板.md` | `00_看板/发布追踪.md` | sync 脚本生成 |
| `20_Project/` | **不迁移** | 项目任务不属于内容数据 |
| `50_Resources/` | **不迁移** | 临时资源不属于内容数据 |
| `70_Distribution/distribution.db` | **废弃** | 数据迁入 `data/autowrite.db` |

### 删除的东西

| 旧文件 | 原因 |
|--------|------|
| `内容健康总览.base` | 被 `00_看板/内容总览.md` 中的 Markdown 表格替代 |
| `月见内容监控.base` | 同上 |
| `70_Distribution/distribution.db` | 数据迁入新 DB，不再需要 |
| `.secrets/` | 不应出现在内容仓库中 |

---

## 三、各区域文件格式规范

### 3.1 灵感文件（`10_灵感/<idea_id>.md`）

```markdown
---
id: "a1b2c3d4-5678-..."
title: "真正顶级的爱，不是拥有，是看见"
tags: ["关系", "心理学", "月见"]
source: "human"
status: "pending"                    # pending / used / archived
created_at: "2026-03-26 14:30:00"
---

（正文内容，从 data/content/inbox/<id>.md 复制）
```

- `id` 从 `ideas` 表取
- `status` 从 `ideas` 表取
- 正文从文件取
- Obsidian 可用 frontmatter 做筛选和排序

### 3.2 成品内容文件（`20_内容/<persona>/<platform>/<date_slug>/content.md`）

```markdown
---
content_id: "yuejian_xiaohongshu_20260312_chaojia"
title: "吵完架以后你最怕的那句话"
persona: "yuejian"
platform: "xiaohongshu"
status: "published"                  # draft / revising / final / publishing / published / archived
review_score: 85
source_idea: "a1b2c3d4-..."         # 关联灵感 ID（可为空）
created_at: "2026-03-12 10:00:00"
# --- 发布信息（仅 published 状态有） ---
post_url: "https://www.xiaohongshu.com/explore/..."
published_at: "2026-03-12 12:00:00"
# --- 最新 metrics（仅有采集数据时） ---
views: 321
likes: 28
collects: 9
comments: 4
shares: 2
metrics_captured_at: "2026-03-27 11:55:00"
---

（正文内容，从 data/content/<content_id>/content.md 复制）
```

- 元数据全部从 `contents` + `publications` + `metrics` 三张表 JOIN 取出
- 正文从文件复制
- 附件（jpg 等）原样复制到同目录

**vault 目录名规则**：`<YYYYMMDD>_<中文标题前20字>`
- 用中文标题而非 slug，因为 Obsidian 是给人看的
- 示例：`20260312_吵架时变成陌生人的你`
- sync 脚本通过 content_id 做映射，不依赖目录名反推

### 3.3 日记文件（`40_日记/YYYY-MM-DD.md`）

```markdown
---
date: "2026-03-27"
---

## 今日计划
（从 daily_logs.plan 取）

## 产出记录
（从 daily_logs.output 取）

## 随想
（从 daily_logs.notes 取）
```

### 3.4 知识库文件（`30_知识库/`）

直接从 `data/knowledge/` 原样复制，不做格式转换。

---

## 四、看板页面设计

### 4.1 内容总览（`00_看板/内容总览.md`）

sync 脚本读取 `contents` 表，按状态分组生成 Markdown 表格：

```markdown
# 内容总览

> 自动生成于 2026-04-01 10:00:00，请勿手动编辑

## 待发布（final）

| 内容 | 人设 | 平台 | 评分 | 创建日期 |
|------|------|------|------|---------|
| [[20_内容/yuejian/xiaohongshu/20260326_真正顶级的爱/content\|真正顶级的爱，不是拥有，是看见]] | yuejian | 小红书 | 88 | 2026-03-26 |

## 已发布（published）

| 内容 | 人设 | 平台 | 评分 | 发布日期 | 阅读 | 点赞 | 收藏 |
|------|------|------|------|---------|------|------|------|
| [[20_内容/yuejian/xiaohongshu/20260312_吵架时变成陌生人/content\|吵完架以后你最怕的那句话]] | yuejian | 小红书 | 85 | 03-12 | 321 | 28 | 9 |

## 草稿（draft / revising）

（同上格式）

## 统计
- 总计：XX 篇
- 已发布：XX 篇（yuejian XX / chongxiaoyu XX）
- 待发布：XX 篇
- 草稿中：XX 篇
```

### 4.2 灵感池（`00_看板/灵感池.md`）

```markdown
# 灵感池

> 自动生成于 2026-04-01 10:00:00

## 待使用（pending）

| 灵感 | 标签 | 来源 | 日期 |
|------|------|------|------|
| [[10_灵感/a1b2c3d4\|真正顶级的爱，不是拥有，是看见]] | 关系, 心理学 | human | 2026-03-26 |

## 已使用（used）

（同上）

## 统计
- 待使用：XX 条
- 已使用：XX 条
- 已归档：XX 条
```

### 4.3 发布追踪（`00_看板/发布追踪.md`）

```markdown
# 发布追踪

> 自动生成于 2026-04-01 10:00:00

## 待采集 metrics

| 内容 | 发布日期 | 距今 | 上次采集 | 状态 |
|------|---------|------|---------|------|
| [[...]] | 03-12 | 20天 | 未采集 | ⚠️ 需补采 |

## 最近发布

| 内容 | 平台 | 发布日期 | 阅读 | 点赞 | 收藏 | 评论 | 链接 |
|------|------|---------|------|------|------|------|------|
| ... | 小红书 | 03-20 | 321 | 28 | 9 | 4 | [链接](url) |

## 人设汇总

### yuejian
- 已发布：XX 篇
- 总阅读：XXX | 总点赞：XX | 总收藏：XX
- 平均阅读：XX

### chongxiaoyu
- ...
```

### 4.4 每日回顾（`00_看板/每日回顾.md`）

```markdown
# 每日回顾

> 最近 7 天的工作日记

## 2026-03-27
**计划**：清理月见内容监控积压记录 ...
**产出**：纯 agent 工作流已实际调用 1 次 ...

## 2026-03-26
...
```

---

## 五、sync_vault.py 设计

### 5.1 核心逻辑

```
sync_vault.py [--vault-path <path>] [--data-path <path>]

1. 清空 vault 中除 .obsidian/ 外的所有内容
2. 生成 10_灵感/     ← ideas 表 + data/content/inbox/
3. 生成 20_内容/     ← contents 表 + data/content/<content_id>/
   - JOIN publications 取发布信息
   - JOIN metrics 取最新一条 metrics
   - 按 persona/platform 建子目录
   - 复制正文 + 附件
4. 生成 30_知识库/   ← data/knowledge/ 直接复制
5. 生成 40_日记/     ← daily_logs 表
6. 生成 00_看板/     ← 汇总查询生成 Markdown
```

### 5.2 调用时机

| 场景 | 触发方式 |
|------|---------|
| 手动同步 | `python tools/sync_vault.py` |
| /create 完成后 | skill 最后一步自动调用 |
| /collect 完成后 | 同上 |
| /publish 状态变更后 | 同上 |
| /daily 保存后 | 同上 |

### 5.3 配置

在 `.env` 中增加：

```bash
VAULT_PATH=~/.openclaw/workspace/vault    # Obsidian vault 路径
```

### 5.4 幂等性

- 每次 sync 完整重建 vault（除 `.obsidian/`）
- 不做增量同步——文件量不大（<200 篇），全量重建更简单可靠
- 耗时预估 <1 秒

---

## 六、迁移步骤（一次性）

### 阶段 1：数据迁移（老 vault → data/）

```
1. 初始化 data/ 目录结构 + autowrite.db
2. 从 distribution.db 迁移：
   - personas → personas 表
   - accounts → accounts 表
   - publications → publications 表（重新关联 content_id）
   - metrics → metrics 表
   - content_status → contents 表（状态映射）
3. 从 60_Published/ 迁移成品文件：
   - 扫描每个 content.md，提取 frontmatter
   - 生成 content_id（persona_platform_YYYYMMDD_slug）
   - 复制到 data/content/<content_id>/
   - 写入 contents 表
4. 从 00_Inbox/ 迁移灵感：
   - 每个文件生成 UUID
   - 复制到 data/content/inbox/<uuid>.md（去 frontmatter）
   - 写入 ideas 表
5. 从 30_Research/ 迁移知识库：
   - 复制到 data/knowledge/research/
6. 从 10_Daily/ 迁移日记：
   - 解析文件内容 → 写入 daily_logs 表
```

### 阶段 2：验证

```
7. 运行 sync_vault.py 生成新 vault
8. 用 Obsidian 打开新 vault，检查：
   - 所有成品是否完整（数量、正文、图片）
   - 看板页面数据是否正确
   - frontmatter 字段是否可被 Obsidian 识别
9. 对比新旧 vault，确认无数据丢失
```

### 阶段 3：切换

```
10. 备份旧 vault（mv vault vault_backup_20260401）
11. 将 Obsidian 指向新 vault 路径
12. 旧 vault 保留 30 天后删除
```

---

## 七、注意事项

1. **`.obsidian/` 绝不碰** —— sync 脚本跳过此目录，用户的 Obsidian 主题、插件、工作区配置不受影响
2. **看板不依赖插件** —— 用纯 Markdown 表格 + `[[wikilink]]`，不依赖 Dataview/Database 插件，降低维护成本
3. **附件处理** —— jpg/png 等附件与 content.md 放同目录，Obsidian 可直接预览
4. **vault 内编辑的后果** —— 在 vault 里改的内容下次 sync 会被覆盖。如果需要快速编辑，应该通过 `/create` 修改 data/，再 sync
5. **content_id 是桥梁** —— vault 的目录名虽然用中文标题（好看），但 frontmatter 里的 `content_id` 才是与 data/ 对应的真正主键
