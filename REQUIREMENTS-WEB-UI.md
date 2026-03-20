# Claude Workflows Web UI 需求文档

## 一、项目背景

现有 `claude-workflows` 是一个 AI 驱动的内容生产系统，所有操作通过 Claude CLI skills 触发，只有熟悉命令行的人才能使用。本次改造的目标是：**为现有 Agent 工作流加一层 Web UI 前端**，让不懂技术的普通人也能完成内容生产的全部流程。

### 核心原则

1. **Web UI 是应用层封装**：不重写现有内容生产逻辑，但允许新增稳定的后端包装脚本 / API，对 UI 屏蔽原始 Claude CLI 调用细节
2. **人 + Agent 双重身份**：每个流程都支持人工操作和 Agent 自动执行，数据统一
3. **仅本机访问**：Web 应用运行在本机，绑定 `localhost`，不暴露到外网
4. **数据统一**：人工录入和 Agent 采集的数据存在同一个仓库（$VAULT_PATH），同一套格式

---

## 二、用户角色

| 角色 | 描述 | 操作方式 |
|------|------|----------|
| **人工用户** | 不懂技术的内容创作者 | 通过浏览器 UI 操作 |
| **Agent** | Claude CLI 子进程 | 被 UI 后端调用，执行现有 skills |

两种角色产生的数据写入同一个仓库，状态记录表中标注操作者身份（人/Agent）。

---

## 三、系统架构

```
┌──────────────────────────────────────────────┐
│                 浏览器（localhost）              │
│                                              │
│   灵感池  │  写作台  │  编辑台  │  发布台  │  看板   │
└────────────────────┬─────────────────────────┘
                     │ HTTP API
┌────────────────────┴─────────────────────────┐
│              Web 后端（本机运行）                │
│                                              │
│   REST API 层                                │
│     ├── 灵感 CRUD                             │
│     ├── 内容 CRUD                             │
│     ├── 选稿/发布管理                           │
│     ├── 状态记录查询                            │
│     └── Agent 任务调度                         │
│                                              │
│   数据层                                      │
│     ├── Vault 文件读写（Markdown）              │
│     └── SQLite 读写（distribution.db）         │
│                                              │
│   Agent 调度层                                │
│     ├── 调用后端包装脚本 / 任务 API              │
│     ├── 包装脚本内部再调 Claude CLI skills       │
│     ├── 管理子进程生命周期                       │
│     └── 实时输出推送（SSE）                     │
└──────────────────────────────────────────────┘
          │                    │
          ▼                    ▼
   $VAULT_PATH            claude-workflows/
   （数据仓库）             （工厂代码 + skills）
```

### 技术约束

- **绑定地址**：`127.0.0.1` 或 `localhost`，禁止 `0.0.0.0`
- **数据存储**：复用现有 $VAULT_PATH 目录结构和 SQLite 数据库，不引入新的数据库
- **Agent 调度**：由 Web 后端调用稳定的包装脚本 / API，再由包装层调用 `claude -p` 和现有 skills；前端不直接依赖 Claude CLI 参数细节

---

## 四、数据模型扩展

### 4.1 现有数据结构（保持不变）

**Vault 文件系统**：
- `00_Inbox/*.md` — 灵感文件（YAML frontmatter + Markdown 正文）
- `60_Published/<persona>/<platform>/YYYY-MM-DD_<title>/content.md` — 成品内容
- `10_Daily/YYYY-MM-DD.md` — 每日记录
- `20_Project/*.md` — 项目文件（C.A.P. 格式）

**SQLite 数据库**（`70_Distribution/distribution.db`）：
- `personas` — 人设表
- `accounts` — 平台账号表
- `publications` — 发布记录表
- `metrics` — 数据采集表

### 4.2 需要新增的数据结构

#### 4.2.1 内容状态表（SQLite 新表：`content_status`）

跟踪每条内容从灵感到发布的完整生命周期。

```sql
CREATE TABLE content_status (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id      TEXT NOT NULL UNIQUE,      -- 唯一标识，UUID 或稳定 slug，不依赖路径
    title           TEXT NOT NULL,
    content_type    TEXT NOT NULL DEFAULT 'social-media',  -- social-media / podcast / writing
    persona_id      TEXT,                      -- 关联人设
    platform        TEXT,                      -- 平台；首期为一平台一内容，因此为必填业务字段
    status          TEXT NOT NULL DEFAULT 'idea',
                    -- idea: 灵感
                    -- selected: 已选题
                    -- drafting: 写作中（Agent 正在生成）
                    -- draft: 初稿完成
                    -- revising: 修改中
                    -- final: 定稿
                    -- publishing: 发布中
                    -- published: 已发布
                    -- archived: 已归档
    source_path     TEXT,                      -- Vault 中的源文件路径（相对于 $VAULT_PATH）
    output_path     TEXT,                      -- 成品文件路径（相对于 $VAULT_PATH）
    review_score    INTEGER,                   -- reviewer 总分，可为空
    operator_type   TEXT,                      -- 最近一次操作者：human / agent
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
```

#### 4.2.2 状态变更日志表（SQLite 新表：`status_log`）

每次状态变更都记录，包含操作者身份。

```sql
CREATE TABLE status_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id      TEXT NOT NULL,              -- 关联 content_status.content_id
    from_status     TEXT,                       -- 变更前状态（首次创建时为 NULL）
    to_status       TEXT NOT NULL,              -- 变更后状态
    operator        TEXT NOT NULL,              -- 'human' 或 'agent:<skill_name>'
    note            TEXT,                       -- 操作备注
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (content_id) REFERENCES content_status(content_id)
);
```

#### 4.2.3 灵感 Frontmatter 扩展

现有 `00_Inbox/*.md` 文件的 YAML frontmatter 增加以下可选字段（向后兼容，不破坏现有文件）：

```yaml
---
title: 水逆生存指南
source: human          # human / agent:采集skill名
persona: chongxiaoyu   # 可选，指定人设
platform: xiaohongshu  # 可选，指定平台
tags: [占星, 水逆]      # 可选
created: 2026-03-20
---
```

**重要约束**：
- `content_status.status` 是系统内唯一的业务状态真源
- Inbox/frontmatter 中不再维护业务状态字段；如历史文件存在 `status` 字段，UI 只做兼容读取，不以其作为判断依据
- frontmatter 只承担展示、检索和初始录入元数据的职责

#### 4.2.4 发布记录表扩展（SQLite 迁移：`publications` 新增 `content_id`）

为建立 `content_status` 与 `publications` 的稳定关联，给现有 `publications` 表新增 `content_id` 字段：

```sql
ALTER TABLE publications ADD COLUMN content_id TEXT;
CREATE INDEX IF NOT EXISTS idx_publications_content_id ON publications(content_id);
```

说明：
- `content_id` 是内容级稳定主键，是 `content_status` 与 `publications` 的正式关联键
- `content_path` 继续保留，用于定位具体成品文件
- 不再依赖 `content_path` 作为跨生命周期关联键，因为标题变化会导致目录和路径变化

---

## 五、核心页面与功能

### 5.1 灵感池（Inspiration Pool）

灵感的统一入口，人工录入和 Agent 采集的灵感都在这里。

#### 页面布局

- **顶部**：筛选栏（按状态 / 人设 / 标签 / 来源）+ 新建灵感按钮
- **主区域**：灵感卡片列表（支持列表视图和看板视图切换）
  - 每张卡片显示：标题、摘要（前100字）、来源标签（人工/Agent）、状态、创建时间
  - 卡片操作：查看详情、编辑、删除、标记状态

#### 功能清单

| 功能 | 操作者 | 描述 |
|------|--------|------|
| **录入灵感** | 人工 | 表单填写：标题、正文（富文本/Markdown）、标签、关联人设。保存为 `00_Inbox/<date>_<title>.md` |
| **浏览灵感** | 人工 | 查看 `00_Inbox/` 下所有 `.md` 文件，解析 frontmatter + 正文展示 |
| **编辑灵感** | 人工 | 直接修改灵感内容和 frontmatter 字段 |
| **删除灵感** | 人工 | 删除对应 `.md` 文件 |
| **筛选灵感** | 人工 | 按状态、人设、标签、来源（人工/Agent）筛选 |
| **Agent 采集入库** | Agent | Agent 采集后直接写入 `00_Inbox/`，格式与人工录入一致 |
| **标记选题** | 人工 | 为灵感创建或更新 `content_status` 记录，将状态置为 `selected` |

#### 数据流

```
人工录入 ──┐
            ├──→ 00_Inbox/<date>_<title>.md ──→ 灵感池页面展示
Agent 采集 ─┘                                      │
                                                   ▼
                                      创建/更新 content_status
                                                   │
                                                   └──→ status_log 表
```

---

### 5.2 写作台（Writing Desk）

发起写作任务、查看 Agent 写作过程、接收成品。

#### 页面布局

- **左侧**：任务列表（进行中 / 已完成）
- **右侧**：当前任务详情
  - 新建任务表单：选择灵感素材、人设、平台、附加指令
  - Agent 执行中：实时显示 Agent 输出（Writer 初稿 → Reviewer 评分 → 迭代过程）
  - 完成后：展示最终成品、Reviewer 评分

#### 功能清单

| 功能 | 操作者 | 描述 |
|------|--------|------|
| **发起写作** | 人工 | 从灵感池选择素材（或自由输入），选人设+平台，提交给 Agent |
| **查看进度** | 人工 | 实时查看 Agent 的 Writer→Reviewer 循环过程（最多3轮） |
| **查看成品** | 人工 | Agent 完成后展示最终内容、评分详情 |
| **执行写作** | Agent | 后端调用 `content-creation` skill，参数来自 UI 表单 |

#### 与现有 skill 的对接

UI 后端不直接拼装原始 Claude CLI 参数，而是调用稳定的后端任务包装层，例如：

```bash
# 由 Web 后端调用包装脚本 / API
python run_content_task.py \
  --content-id <content_id> \
  --persona <persona_id> \
  --platform <platform> \
  --input "<素材内容或引用路径>"
```

包装层负责：
- 组装对现有 `content-creation` skill 的调用
- 规范 stdout/stderr 输出格式
- 回传任务生命周期事件
- 在任务成功后更新 `content_status.output_path`、`review_score`、`status`

后端捕获包装层 stdout/stderr，通过 SSE 实时推送到前端。

#### 数据流

```
用户选择灵感 + 人设 + 平台
        │
        ▼
  content_status: idea/selected → drafting（status_log 记录）
        │
        ▼
  后端调用包装脚本 / 任务 API
        │
        ├── stdout → SSE → 前端实时展示
        │
        ▼
  skill 完成：成品写入 60_Published/
        │
        ▼
  content_status: drafting → draft（status_log 记录）
```

---

### 5.3 编辑台（Editing Desk）

人工修改内容、或指示 Agent 修改，二者结合。

#### 页面布局

- **左侧**：待编辑内容列表（状态为 `draft` 或 `revising` 的内容）
- **右侧**：编辑区
  - 上方：Markdown 编辑器（所见即所得 / 源码切换）
  - 下方：操作栏
    - 「保存」按钮 — 人工保存修改
    - 「让 Agent 修改」输入框 — 输入修改指令，Agent 根据指令调整内容
    - 「定稿」按钮 — 标记为 `final` 状态

#### 功能清单

| 功能 | 操作者 | 描述 |
|------|--------|------|
| **人工编辑** | 人工 | 直接在编辑器中修改 Markdown 内容，保存回文件 |
| **Agent 修改** | 人工发起 → Agent 执行 | 输入修改指令（如"标题改短一点""加一个案例"），Agent 修改后回显到编辑器 |
| **对比查看** | 人工 | 修改前后的 diff 对比 |
| **定稿** | 人工 | 确认内容 OK，状态改为 `final` |
| **退回重写** | 人工 | 对内容不满意，退回到写作台重新生成 |

#### Agent 修改的实现

```bash
# 后端将当前内容 + 修改指令交给包装层
python run_revision_task.py \
  --content-id <content_id> \
  --instruction "<用户输入的修改指令>" \
  --input-file "<当前 content.md 路径>"
```

包装层内部可调用 Claude CLI 完成修改，返回修改后的完整内容。UI 展示 diff，用户确认后保存。

#### 数据流

```
用户打开 draft 内容
        │
  ┌─────┴──────┐
  │            │
人工编辑    Agent修改
  │            │
  └─────┬──────┘
        │
  保存到 60_Published/ 对应文件（直接覆盖 content.md）
        │
  content_status: draft/final → revising → final
  status_log: 每次操作记录（人工/Agent）
```

---

### 5.4 选稿台（Selection Desk）

根据每次不同的目标，从定稿池中选出要发布的内容。

#### 页面布局

- **顶部**：目标输入区 — 本次选稿的目标描述（自由文本，如"本周发3篇小红书，2篇占星1篇AI"）
- **左侧**：候选内容列表（状态为 `final` 的内容，按人设/平台分组）
  - 每条显示：标题、人设、平台、创建日期、Reviewer 评分
- **右侧**：选稿结果
  - Agent 推荐区：Agent 根据目标推荐的内容列表 + 推荐理由
  - 人工确认区：勾选最终要发布的内容

#### 功能清单

| 功能 | 操作者 | 描述 |
|------|--------|------|
| **输入选稿目标** | 人工 | 描述本次发布需求（频率、主题分布、时效性等） |
| **Agent 推荐** | Agent | 根据目标 + 候选池，输出推荐列表及理由 |
| **人工选择** | 人工 | 浏览候选和推荐，勾选最终发布内容 |
| **确认选稿** | 人工 | 确认后，选中内容状态改为 `publishing`，写入状态记录 |
| **预览内容** | 人工 | 点击候选条目可预览完整内容 |

#### 选稿 Agent 的实现

后端将候选内容列表 + 用户目标传给包装层，再由包装层调用 Claude：

```
你是选稿编辑。以下是候选稿件池和本次发布目标，请推荐最合适的内容。

## 发布目标
<用户输入的目标描述>

## 候选稿件
1. [标题] | 人设: xxx | 平台: xxx | 评分: x/10 | 日期: xxxx-xx-xx
   摘要: ...
2. ...

请输出：
- 推荐列表（编号 + 推荐理由）
- 排期建议（如果目标涉及时间安排）
```

#### 数据流

```
用户输入目标
      │
      ▼
后端读取所有 status=final 的内容
      │
      ├──→ Agent 推荐（Claude 调用）
      │
      ▼
用户确认选稿
      │
      ▼
content_status: final → publishing（status_log 记录）
publications 表: 以 `content_id` + `content_path` 创建 draft 记录（复用现有 publish.py/create_publication 逻辑）
```

---

### 5.5 发布台（Publishing Dashboard）

管理内容发布和数据追踪，是现有 `publishing` skill + `metrics.py` 的 UI 化。

#### 页面布局

- **看板视图**：按状态分列（待发布 / 已发布 / 追踪中 / 已归档）
- **每张卡片**：标题、人设、平台、账号、发布时间、最新数据摘要
- **详情面板**：点击卡片展开，显示完整数据历史、发布链接

#### 功能清单

| 功能 | 操作者 | 描述 |
|------|--------|------|
| **查看发布任务** | 人工 | 看板展示所有发布记录，按状态分组 |
| **标记已发布** | 人工 | 填入发布链接，标记为 published |
| **录入数据** | 人工 | 填入阅读/点赞/收藏/评论/分享数据 |
| **查看数据趋势** | 人工 | 图表展示某条内容的数据变化（1/3/7天） |
| **待采集提醒** | 系统 | 高亮显示到期需要采集数据的内容 |

#### 与现有工具的对接

直接读写 `70_Distribution/distribution.db`，复用 `db.py` 中的函数：
- `create_publication()` — 创建发布记录
- `list_publications()` — 查询发布列表
- 直接 SQL 更新 status、post_url、published_at
- `metrics` 表的 INSERT — 录入数据快照

发布完成后的状态规则：
- 当某条 publication 被人工标记为已发布时，对应 `content_status` 进入 `published`
- 数据追踪属于发布层行为，主要体现在 `publications` 和 `metrics`，不额外引入 `content_status=tracking`

---

## 六、状态流转全景图

```
                    灵感池                写作台              编辑台           选稿台          发布台
                    ─────                ─────              ─────           ─────          ─────

                   ┌──────┐
  人工录入 ────→   │ idea │
  Agent采集 ───→   │      │
                   └──┬───┘
                      │ 标记选题
                      ▼
                   ┌──────────┐
                   │ selected │
                   └──┬───────┘
                      │ 发起写作
                      ▼
                   ┌──────────┐         ┌─────────┐
                   │ drafting │ ──────→ │  draft   │
                   │(Agent中) │  完成    │         │
                   └──────────┘         └──┬──────┘
                                           │ 编辑
                                           ▼
                                        ┌──────────┐
                                        │ revising │ ←─ 可反复编辑
                                        └──┬───────┘
                                           │ 定稿
                                           ▼
                                        ┌────────┐
                                        │ final  │
                                        └──┬─────┘
                                           │ 选稿确认 / 直接发布
                                           ▼
                                                        ┌────────────┐
                                                        │ publishing │
                                                        └──┬─────────┘
                                                           │ 标记已发布
                                                           ▼
                                                                       ┌───────────┐
                                                                       │ published │
                                                                       └──┬────────┘
                                                                          │ 手动归档 / 生命周期结束
                                                                          ▼
                                                                       ┌──────────┐
                                                                       │ archived │
                                                                       └──────────┘
```

**每次状态变更都写入 `status_log` 表**，记录：
- 变更前后状态
- 操作者（`human` 或 `agent:<skill_name>`）
- 时间戳
- 备注

说明：
- `tracking` 不再作为 `content_status` 的主状态
- 发布后的数据监控由 `publications` + `metrics` 负责，UI 可展示“监控中”，但不额外引入内容级状态

---

## 七、状态记录表与 publications 表的关系

```
content_status（内容全生命周期）
    │
    │ 当 status 变为 publishing 时
    │
    ▼
publications（发布阶段细化管理）
    │
    │ 一条 content 可能对应多条 publication
    │ （同一平台内容发到多个账号）
    │
    ▼
metrics（每条 publication 的数据采集）
```

- `content_status` 管理内容从灵感到发布的**宏观生命周期**
- `publications` 管理**具体到每个账号的发布记录**（一对多关系）
- 两张表通过 `content_status.content_id` 和 `publications.content_id` 正式关联
- `content_path` 仅用于回到具体成品文件，不作为稳定主键

---

## 八、非功能需求

### 8.1 性能
- 灵感池、内容列表在常规单机规模下目标加载 < 1秒
- 首期默认按“数千级文件 + 单用户”规模设计；如后续文件量显著增长，再补缓存或索引层
- Agent 写作任务：实时流式输出，不等整个 skill 执行完再返回

### 8.2 兼容性
- 不破坏现有 Vault 文件结构，新增的 frontmatter 字段向后兼容
- 不破坏现有 SQLite schema；允许通过 migration 为现有表新增字段（如 `publications.content_id`）
- 现有 Claude CLI skills 仍然可以独立使用（不依赖 Web UI）
- Agent 直接写入 `00_Inbox/` 的文件，UI 能正确解析和展示

### 8.3 安全
- 绑定 `127.0.0.1`，不接受外部连接
- 不在前端暴露 $VAULT_PATH 的绝对路径
- 不在前端暴露 .env 中的敏感信息

### 8.4 并发与一致性
- 同一条内容同一时间只允许一个活动任务（写作 / 修改 / 发布准备）
- 编辑台保存时校验 `content_status.updated_at`；如果内容已被其他任务更新，前端提示刷新后重试
- 不实现复杂自动 merge；冲突发生时以显式提示为准
- Agent 任务失败时必须写入 `status_log`，并保留原状态或回退到可继续操作的状态

### 8.5 任务模型
- 后端统一维护任务表或内存任务注册表，最少包含：`task_id`、`content_id`、`task_type`、`status`、`started_at`、`ended_at`
- 任务状态最少包含：`queued`、`running`、`succeeded`、`failed`、`cancelled`
- SSE 事件至少包含：`task.started`、`task.output`、`task.progress`、`task.completed`、`task.failed`
- 前端所有长任务页面均基于 `task_id` 订阅进度，不直接依赖底层 Claude 子进程 PID

---

## 九、跳过状态的场景

不是所有内容都走完整流程。以下场景允许跳过中间状态：

| 场景 | 流程 |
|------|------|
| 灵感直接写作 | idea → drafting → draft（跳过 selected） |
| 自由输入写作（不从灵感池选） | 直接创建 drafting 状态的记录 |
| 人工直接写稿（不用 Agent） | 在编辑台直接创建内容 → draft |
| 定稿直接发布（不经过选稿台） | final → publishing（跳过 Agent 推荐） |
| Agent 全自动（从采集到发布） | 理论上支持，但发布前**必须**人工确认 |

---

## 十、技术决策

| 项目 | 决策 | 说明 |
|------|------|------|
| **后端框架** | Python FastAPI | 与现有 distribution 工具同语言，复用 db.py |
| **前端框架** | React | SPA 单页应用 |
| **Agent 进度推送** | SSE（Server-Sent Events） | 单机单用户场景，SSE 比 WebSocket 简单，无需维护双向连接；FastAPI 原生支持 StreamingResponse |
| **Markdown 编辑器** | 实施时评估选定 | 需支持所见即所得 + 源码切换 |
| **用户认证** | 不需要 | 仅本机访问，单用户 |
| **后端调度接口** | 包装脚本 / 内部 API | 由 Web 后端调用稳定接口，再转调 Claude CLI 和现有 skills |
| **首期范围** | 仅社媒生产线，且包含选稿台 | 播客生产线后续迭代 |
| **移动端适配** | 不需要 | 灵感录入通过 OpenClaw 调用 Agent 完成 |

### 10.1 首期交付范围（MVP）

首期必须包含以下模块：
- 灵感池：录入、浏览、编辑、筛选、标记选题
- 写作台：发起写作、查看实时进度、查看成品
- 编辑台：人工修改、Agent 修改、diff 对比、定稿
- 选稿台：输入发布目标、Agent 推荐、人工勾选确认
- 发布台：查看发布任务、标记已发布、录入数据、查看趋势

首期明确不做：
- 播客生产线 UI
- 多用户认证与权限
- 复杂版本合并
- 外网部署

### 10.2 推荐的最小后端 API

为降低前后端耦合，建议首期按以下最小接口集实施：

- `GET /api/inspirations`
- `POST /api/inspirations`
- `PUT /api/inspirations/{id}`
- `DELETE /api/inspirations/{id}`
- `POST /api/contents/{content_id}/draft`
- `POST /api/contents/{content_id}/revise`
- `POST /api/contents/{content_id}/finalize`
- `POST /api/selection/recommend`
- `POST /api/selection/confirm`
- `GET /api/publications`
- `POST /api/publications/{id}/publish`
- `POST /api/publications/{id}/metrics`
- `GET /api/tasks/{task_id}/events`（SSE）
