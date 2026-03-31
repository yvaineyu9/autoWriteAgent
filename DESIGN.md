# autoWriteAgent 架构重构设计文档

> **版本**：v2.0
> **日期**：2026-03-31
> **状态**：待评审

---

## 一、重构目标

将现有项目重构为 **单一职责、渐进式披露、自包含** 的 Agent 内容生产系统。

### 核心原则

| 原则 | 说明 |
|------|------|
| **单一职责** | 每个 Agent 只做一件事，每个文件只服务一个角色 |
| **渐进式披露** | 分 4 层加载，每层只回答一个问题并指向下一层 |
| **人设 × 平台 = 上下文单元** | 一个平台文件自包含该组合的全部上下文 |
| **AI 与确定性分离** | 需要判断力的用 Agent，规则确定的用 Tool 脚本 |
| **数据库索引 + 文件本体** | SQLite 管状态和元数据，文件存内容正文，两者通过 content_id 关联 |
| **仓库访问收口** | Agent 不直接读写 data/，所有数据 I/O 通过 tools/ |
| **相关上下文可检索** | 知识库内容可被稳定检索并按需注入，不因压缩上下文而削掉检索能力 |
| **Tool 契约化** | 每个 tool 有明确的 exit code、stdout 格式、幂等性和失败语义 |
| **可观测** | 每次任务有完整的执行痕迹，关键节点有人工接管点 |
| **自包含** | 整个系统在一个目录内完成，不依赖外部 $VAULT_PATH |

---

## 二、存储架构

### 2.1 双层存储模型

```
SQLite（autowrite.db）                     文件系统（data/content/）
═══════════════════                        ═══════════════════════
状态、元数据、关系、索引                      内容正文、附件

  ideas 表                                  data/content/inbox/<idea_id>.md
  contents 表          ── content_id ──→    data/content/<content_id>/content.md
  publications 表
  metrics 表
  traces 表
  daily_logs 表
```

### 2.2 各类数据的存储归属

| 数据 | 存储位置 | 原因 |
|------|---------|------|
| 灵感正文 | 文件 `data/content/inbox/<idea_id>.md` | 可能很长，人可直接打开 |
| 灵感元数据（标题/标签/状态/日期） | 数据库 `ideas` 表 | 需要查询筛选 |
| 成品正文 | 文件 `data/content/<content_id>/content.md` | 可能含附件（图片等） |
| 成品元数据（人设/平台/状态/评分） | 数据库 `contents` 表 | 需要生命周期管理 |
| 发布记录 | 数据库 `publications` 表 | 纯结构化数据 |
| 数据采集（阅读/点赞等） | 数据库 `metrics` 表 | 纯结构化数据 |
| 每日日记 | 数据库 `daily_logs` 表 | 短文本，按日期查询 |
| 执行痕迹 | 数据库 `traces` 表 | 结构化日志，需要按 task_id 查询 |
| 知识库（Wiki/Research） | 文件 `data/knowledge/` | 长文本，需要全文搜索 |
| 人设/Agent/Skill 定义 | Git 仓库文件 | 代码，不进 data/ |

### 2.3 数据库 Schema

```sql
-- 灵感
CREATE TABLE ideas (
    id            TEXT PRIMARY KEY,          -- UUID
    title         TEXT NOT NULL,
    tags          TEXT,                      -- JSON 数组 ["tag1","tag2"]
    source        TEXT DEFAULT 'human',      -- human / agent
    status        TEXT DEFAULT 'pending',    -- pending / used / archived
    file_path     TEXT NOT NULL,             -- 相对于 data/content/ 的路径
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 内容（生命周期主表）
CREATE TABLE contents (
    content_id    TEXT PRIMARY KEY,          -- <persona>_<platform>_<YYYYMMDD>_<slug>
    title         TEXT NOT NULL,
    persona_id    TEXT NOT NULL,
    platform      TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'draft',
                  -- draft: 初稿完成
                  -- revising: 修改中
                  -- final: 定稿（可被 /select 选中）
                  -- publishing: 已选稿待发布
                  -- published: 已发布
                  -- archived: 已归档
    file_path     TEXT NOT NULL,             -- 相对于 data/content/ 的路径
    review_score  INTEGER,                   -- 最近一次评审总分
    review_json   TEXT,                      -- 最近一次评审完整 JSON
    source_idea   TEXT,                      -- 关联的 idea.id（可为空）
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 状态变更日志
CREATE TABLE status_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id    TEXT NOT NULL,
    from_status   TEXT,
    to_status     TEXT NOT NULL,
    operator      TEXT NOT NULL,             -- 'human' 或 'agent:<skill_name>'
    note          TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (content_id) REFERENCES contents(content_id)
);

-- 发布记录
CREATE TABLE publications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id    TEXT NOT NULL,
    persona_id    TEXT NOT NULL,
    platform      TEXT NOT NULL,
    account_id    TEXT,
    status        TEXT DEFAULT 'draft',      -- draft / published / tracking / archived
    post_url      TEXT,
    published_at  TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (content_id) REFERENCES contents(content_id)
);

-- 数据采集
CREATE TABLE metrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id INTEGER NOT NULL,
    views         INTEGER DEFAULT 0,
    likes         INTEGER DEFAULT 0,
    collects      INTEGER DEFAULT 0,
    comments      INTEGER DEFAULT 0,
    shares        INTEGER DEFAULT 0,
    captured_at   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (publication_id) REFERENCES publications(id)
);

-- 人设
CREATE TABLE personas (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 平台账号
CREATE TABLE accounts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id    TEXT NOT NULL,
    platform      TEXT NOT NULL,
    account_name  TEXT NOT NULL,
    active        INTEGER DEFAULT 1,
    FOREIGN KEY (persona_id) REFERENCES personas(id)
);

-- 每日日记
CREATE TABLE daily_logs (
    date          TEXT PRIMARY KEY,          -- YYYY-MM-DD
    plan          TEXT,                      -- 今日计划
    output        TEXT,                      -- 产出记录（追加式）
    notes         TEXT,                      -- 随想
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 执行痕迹
CREATE TABLE traces (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       TEXT NOT NULL,
    event_type    TEXT NOT NULL,             -- start / log / fail / end
    message       TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_traces_task ON traces(task_id);
```

### 2.4 content_id 生成规则

格式：`<persona>_<platform>_<YYYYMMDD>_<slug>`

示例：`chongxiaoyu_xiaohongshu_20260331_shuini-qiusheng`

- `slug` 由标题生成（拼音或关键词，sanitize 后最长 30 字符）
- 同日同人设同平台有重复 slug 时追加 `_2`, `_3`
- content_id 一旦生成不可变更，是全生命周期的稳定主键

---

## 三、渐进式披露架构

### 3.1 四层加载模型

```
L0 ─ CLAUDE.md ──────────────── 索引：有哪些命令、东西在哪
                                 (~25 行，启动时加载)
     │
     │ 用户触发命令
     ▼
L1 ─ skills/xxx.md ──────────── 配方：分几步、每步调哪个 tool
                                 (~60 行，按需加载)
     │
     │ 按步骤指引
     ▼
L2 ─ personas/.../index.md ──── 路由：确认人设和平台存在
                                 (~20 行，轻量校验)
     │
     │ 拼接后注入 sub-agent
     ▼
L3 ─ personas/.../platform.md ─ 上下文：人设声音 + 格式 + 评审标准
     + agents/xxx.md ─────────── 角色：通用职责 + 输入输出契约
                                 (两者拼接，同层注入)
```

personas 的平台文件和 agents 是**同一层的两个维度**：
- `platform.md` = 为谁写（上下文）
- `agents/xxx.md` = 怎么写（角色）

它们被 skill 拼接后一起注入 sub-agent，不是上下级关系。

### 3.2 文件读取矩阵

| 文件 | 层级 | 读取者 | 读取时机 |
|------|------|--------|---------|
| `CLAUDE.md` | L0 | 主会话 | 启动时（自动） |
| `skills/xxx.md` | L1 | 主会话 | 用户触发命令时 |
| `personas/xxx/index.md` | L2 | 主会话 | skill 第一步（路由校验） |
| `personas/xxx/platforms/yyy.md` | L3 | sub-agent | 拼接注入 |
| `agents/xxx.md` | L3 | sub-agent | 拼接注入 |
| `tools/xxx` | — | 主会话 | skill 中调用（数据 I/O） |

---

## 四、目录结构

```
autoWriteAgent/
│
├── CLAUDE.md                              # L0 全局索引
│
├── skills/                                # L1 命令定义
│   ├── create.md                          #   /create — 内容创作
│   ├── collect.md                         #   /collect — 灵感采集
│   ├── select.md                          #   /select — 选文推荐
│   ├── publish.md                         #   /publish — 发布管理
│   └── daily.md                           #   /daily — 每日规划
│
├── agents/                                # L3 Agent 定义
│   ├── writer.md                          #   写手
│   ├── reviewer.md                        #   评审员
│   ├── collector.md                       #   灵感采集员
│   └── selector.md                        #   选文推荐员
│
├── personas/                              # L2 人设上下文
│   ├── chongxiaoyu/
│   │   ├── index.md                       #     路由索引
│   │   └── platforms/
│   │       ├── xiaohongshu.md             #     自包含完整上下文
│   │       ├── wechat.md
│   │       ├── twitter.md
│   │       └── podcast.md
│   └── yuejian/
│       ├── index.md
│       └── platforms/
│           ├── xiaohongshu.md
│           └── wechat.md
│
├── data/                                  # 数据层（不进 Git）
│   ├── autowrite.db                       #   SQLite 数据库
│   └── content/                           #   内容文件
│       ├── inbox/                         #     灵感正文
│       │   └── <idea_id>.md
│       ├── <content_id>/                  #     成品正文 + 附件
│       │   └── content.md
│       └── knowledge/                     #     知识库
│           ├── wiki/                      #       原子知识词条
│           └── research/                  #       研究笔记
│
├── tools/                                 # 确定性工具（数据 I/O 的唯一入口）
│   ├── db.py                              #   数据库连接 + migration
│   ├── archive.py                         #   成品归档（写文件 + 注册数据库）
│   ├── inbox.py                           #   灵感入库
│   ├── daily.py                           #   每日记录
│   ├── knowledge.py                       #   知识检索
│   ├── validate_review.py                 #   评审 JSON 校验
│   ├── trace.py                           #   执行痕迹
│   ├── publish.py                         #   发布记录管理
│   ├── metrics.py                         #   数据采集
│   ├── xhs-cli/                           #   小红书卡片生成
│   └── transcribe/                        #   音视频转录
│
├── templates/                             # 供 tools 内部使用
│   └── knowledge/
│       ├── wiki.md                        #   知识词条模板
│       └── research.md                    #   研究笔记模板
│
├── .env.example
├── .gitignore                             # data/ 加入 gitignore
└── requirements.txt
```

### 与现有结构的对比

| 现有 | 新结构 | 变化 |
|------|--------|------|
| `$VAULT_PATH/00_Inbox/` | `data/content/inbox/` + `ideas` 表 | 文件 + 数据库双层 |
| `$VAULT_PATH/10_Daily/` | `daily_logs` 表 | 短文本进数据库 |
| `$VAULT_PATH/20_Project/` | 不保留 | 项目管理不在本系统范围 |
| `$VAULT_PATH/30_Research/` | `data/content/knowledge/research/` | 迁入项目内 |
| `$VAULT_PATH/40_Wiki/` | `data/content/knowledge/wiki/` | 迁入项目内 |
| `$VAULT_PATH/50_Resources/` | 不保留 | 由知识库替代 |
| `$VAULT_PATH/60_Published/` | `data/content/<content_id>/` + `contents` 表 | 文件 + 数据库双层 |
| `$VAULT_PATH/70_Distribution/` | `autowrite.db` 中的表 | 合并到统一数据库 |
| `social-media/.claude/` | `agents/` + `personas/` + `skills/` | 提升到顶层 |
| `podcast/.claude/` | 并入 `personas/xxx/platforms/podcast.md` | 播客是人设的一个平台 |
| `web-ui/` | 移除 | 不在本次范围 |
| `.env` 中的 `VAULT_PATH` | 不再需要 | 自包含在项目目录 |

---

## 五、各层详细规格

### 5.1 Layer 0 — CLAUDE.md

```markdown
# autoWriteAgent

AI 内容生产系统。

## 命令
| 命令 | 说明 | 定义 |
|------|------|------|
| /create | 内容创作（写 + 审循环） | skills/create.md |
| /collect | 灵感采集 | skills/collect.md |
| /select | 选文推荐 | skills/select.md |
| /publish | 发布管理 | skills/publish.md |
| /daily | 每日规划 | skills/daily.md |

## 项目结构
- agents/    — Agent 定义（writer, reviewer, collector, selector）
- personas/  — 人设配置（每个子目录 = 一个账号）
- skills/    — 命令编排定义
- tools/     — 工具脚本（数据 I/O 的唯一入口）
- data/      — 数据库 + 内容文件（不进 Git）

## 规则
- 所有数据读写必须通过 tools/ 完成，不直接操作 data/
- 每次 tool 调用后检查 exit code（见 Tool 执行契约）
- 不将 .env、密钥、token 写入任何文件
```

---

### 5.2 Layer 1 — skills/

#### skills/create.md — 内容创作

```markdown
# /create <persona> <platform> [素材]

创建内容：检索知识 → 写作 → 校验评审 → 人工确认 → 归档。

## 参数
- persona: 人设 ID（personas/ 下的子目录名）
- platform: 平台 ID（platforms/ 下的文件名，不含 .md）
- 素材: 可选。URL / 文本 / 文件路径

## 步骤

### Step 1 — 初始化任务
  python tools/trace.py start <task_id> "create" "<persona> <platform>"

### Step 2 — 路由校验
读取 personas/<persona>/index.md。确认人设和平台存在。
失败则：python tools/trace.py fail <task_id> "人设或平台不存在"

### Step 3 — 加载平台上下文
读取 personas/<persona>/platforms/<platform>.md。

### Step 4 — 准备素材
4a. 处理用户输入：
  - 纯文本：直接使用
  - URL：用 WebFetch 获取
  - 文件路径：用 Read 读取
  - 音频 URL：python tools/transcribe/podcast_transcribe.py <url>

4b. 检索相关知识：
  python tools/knowledge.py search "<关键词>"
  将返回的知识片段追加到素材末尾。无匹配则跳过。

### Step 5 — 调用 Writer
组装 /tmp/autowrite/<task_id>/writer_input.md：
1. agents/writer.md
2. 平台上下文
3. 素材 + 知识片段
4. [改稿模式] 上一轮审核反馈

调用：
  cat writer_input.md | claude -p --allowedTools "Read,WebFetch" > /tmp/autowrite/<task_id>/draft.md

### Step 6 — 调用 Reviewer
组装 /tmp/autowrite/<task_id>/reviewer_input.md：
1. agents/reviewer.md
2. 平台上下文
3. draft.md

调用：
  cat reviewer_input.md | claude -p --tools "" > /tmp/autowrite/<task_id>/review_raw.json

### Step 7 — 校验评审结果
  python tools/validate_review.py /tmp/autowrite/<task_id>/review_raw.json

- exit 0 → 读取 stdout 获得校验后的 review.json
- exit 1 → 重新调用 Reviewer（最多重试 2 次）
- 2 次仍失败 → 跳过自动评审，进入 Step 9 由人工判断

### Step 8 — 迭代判断
- pass=true → Step 9
- pass=false 且轮次 < 3 → 将 feedback 加入素材，回到 Step 5
- 3 轮仍未通过 → Step 9，附带最终评分

### Step 9 — 人工确认
展示：最终稿预览 + 评审结果。等待用户：
- "确认" → Step 10
- "修改 <指令>" → 回到 Step 5
- "放弃" → trace.py fail，清理

### Step 10 — 归档
  python tools/archive.py --persona <persona> --platform <platform> --title "<标题>" --file /tmp/autowrite/<task_id>/draft.md [--review-json /tmp/.../review.json] [--source-idea <idea_id>]

检查 exit code（0/1/2/3），按 Tool 契约处理。

  python tools/trace.py end <task_id> "success" "content_id=<id>"
```

#### skills/collect.md — 灵感采集

```markdown
# /collect [素材源]

## 步骤

### Step 1 — 初始化
  python tools/trace.py start <task_id> "collect" "<素材源摘要>"

### Step 2 — 调用 Collector
组装输入：agents/collector.md + 素材源。
  echo <input> | claude -p --allowedTools "Read,WebFetch,WebSearch" > /tmp/autowrite/<task_id>/ideas.json

### Step 3 — 校验输出
检查 ideas.json 为合法 JSON 数组。格式错误则重试 1 次。

### Step 4 — 展示给用户
列出采集到的灵感，让用户确认哪些入库。

### Step 5 — 写入
对每条确认的灵感：
  python tools/inbox.py --title "<title>" --content "<content>" --tags "<tags>"

  python tools/trace.py end <task_id> "success" "入库 N 条"
```

#### skills/select.md — 选文推荐

```markdown
# /select <目标描述>

## 步骤

### Step 1 — 收集候选
  python tools/publish.py list --status final --format json
为空则告知用户无可发布内容。

### Step 2 — 调用 Selector
组装输入：agents/selector.md + 候选列表 + 目标描述。
  echo <input> | claude -p --tools "" > /tmp/autowrite/selection.json

### Step 3 — 展示推荐
展示推荐列表，用户逐条确认。

### Step 4 — 确认
对每条确认的内容：
  python tools/publish.py create --content-id <id> --persona <persona> --title "<title>"
```

#### skills/publish.md — 发布管理

```markdown
# /publish <子命令>

## /publish list [--status <status>]
  python tools/publish.py list [--status <status>]

## /publish done <pub_id> --url <url>
  python tools/publish.py done --id <pub_id> --url "<url>"

## /publish metrics <pub_id> --views N --likes N --collects N --comments N --shares N
  python tools/metrics.py record --pub-id <pub_id> --views N --likes N --collects N --comments N --shares N

## /publish remind
  python tools/metrics.py remind
```

#### skills/daily.md — 每日规划

```markdown
# /daily

## 步骤

### Step 1 — 收集上下文
  python tools/daily.py read yesterday
  python tools/daily.py summary   （返回活跃内容统计、待处理灵感数）

### Step 2 — 交互提问
- Q1: 今天聚焦什么？
- Q2: 新想法？
- Q3: 有阻碍？

### Step 3 — 写入日记
  python tools/daily.py write --plan "<计划>"

### Step 4 — 新想法入库
  python tools/inbox.py --title "<title>" --content "<content>" --tags "daily"

### Step 5 — 展示摘要
```

---

### 5.3 Layer 2 — personas/

#### 文件结构

```
personas/<persona_id>/
├── index.md                    # 路由索引（~20 行）
└── platforms/
    └── <platform_id>.md        # 自包含完整上下文（~200 行）
```

#### index.md 规格

```markdown
# <人设名称>

<一句话定位>

## 可用平台
- <platform_id> → platforms/<platform_id>.md
- ...

## 账号信息
| 平台 | 账号 ID | 说明 |
|------|---------|------|
| ... | ... | ... |
```

#### platforms/xxx.md 规格

Sub-agent 只需读这一个文件。**必须包含以下段落**：

```markdown
# <人设名> × <平台名>

## 人设声音
<!-- 性格、语气、口头禅、视角、禁忌词 — 针对此平台 -->

## 内容格式
<!-- 字数、结构、标题、标签、封面要求 -->

## 评审标准
<!-- 5 维度，每维度 0-2 分，≥7 通过 -->
| 维度 | 0 分 | 1 分 | 2 分 |
|------|------|------|------|
| ... | ... | ... | ... |

## 参考范文
<!-- 1-2 个好范文 -->
```

设计决策：
- 人设声音按平台内联（小红书犀利短句 vs 播客对话体）
- 评审标准按平台内联（小红书看 hook vs 播客看对话自然度）
- 参考范文内联（Writer 最有效的锚定物）

播客统一为人设的一个平台。`platforms/podcast.md` 额外包含节目信息、主持人配置、对话结构。

---

### 5.4 Layer 3 — agents/

#### 设计原则

- **极简**：20-30 行，只定义角色和输入输出契约
- **通用**：不含人设/平台细节，由调用方注入
- **隔离**：`claude -p` 独立进程，不触 data/

#### Agent 清单

| Agent | 职责 |
|-------|------|
| `writer.md` | 内容写作（初稿 + 改稿） |
| `reviewer.md` | 独立评审打分 |
| `collector.md` | 灵感采集、素材整理 |
| `selector.md` | 选文推荐 |

#### agents/writer.md

```markdown
# Writer Agent

你是内容写手。根据提供的人设 × 平台上下文和素材生成内容。

## 输入（由调用方按顺序拼接）
1. 本文件（角色定义）
2. 人设 × 平台上下文（声音规则、格式要求、参考范文）
3. 素材（主题/文本/URL 摘要）
4. 知识补充（来自知识库的相关词条，如有）
5. [可选] 上一轮审核反馈（改稿模式）

## 输出
直接输出成品内容，不加前后缀、解释或 meta 说明。

## 规则
- 严格遵守「人设声音」规则和禁忌词
- 严格遵守「内容格式」中的字数、结构、标签要求
- 参考「参考范文」的质量水准
- 有知识补充时自然融入，用 [[词条名]] 标注引用
- 改稿模式：针对反馈逐条修改，不推倒重写
- 素材不足时可用知识补充，但不编造事实
```

#### agents/reviewer.md

```markdown
# Reviewer Agent

你是内容评审员。独立评估内容质量，输出结构化评分。

## 输入（由调用方按顺序拼接）
1. 本文件（角色定义）
2. 人设 × 平台上下文（含「评审标准」段落）
3. 待评审的内容

## 输出
纯 JSON，不用 code block 包裹：

{
  "total": <0-10，必须等于 scores 各值之和>,
  "pass": <true 当 total >= 7>,
  "scores": {
    "<维度1>": <0-2>,
    "<维度2>": <0-2>,
    "<维度3>": <0-2>,
    "<维度4>": <0-2>,
    "<维度5>": <0-2>
  },
  "feedback": "<未通过时的修改建议，通过时 null>",
  "highlights": "<亮点简述>"
}

## 规则
- 按「评审标准」的维度和分值评分
- total 必须等于 scores 加总
- feedback 必须具体可执行
- 无工具可用，只分析提供的文本
```

#### agents/collector.md

```markdown
# Collector Agent

你是灵感采集员。从素材源中提炼结构化的内容灵感。

## 输入
1. 本文件
2. 素材源（URL 内容 / 文本 / 主题关键词）

## 输出
JSON 数组：

[
  {
    "title": "<灵感标题>",
    "summary": "<100 字以内摘要>",
    "tags": ["标签1", "标签2"],
    "angle": "<建议切入角度>",
    "source": "<素材来源描述>"
  }
]

## 规则
- 每条灵感可独立用于写作
- angle 要具体
- 素材丰富时提取多条不同角度
```

#### agents/selector.md

```markdown
# Selector Agent

你是选文编辑。根据发布目标从候选池中推荐内容。

## 输入
1. 本文件
2. 候选列表（content_id、标题、人设、平台、评分、日期、摘要）
3. 发布目标描述

## 输出
JSON：

{
  "recommendations": [
    { "content_id": "<id>", "reason": "<理由>", "priority": <N> }
  ],
  "schedule_suggestion": "<排期建议>",
  "notes": "<其他建议>"
}

## 规则
- 综合考虑目标匹配、时效性、多样性、评分
- 理由要具体
- 候选不足时明确说明缺口
```

---

### 5.5 tools/（数据 I/O 的唯一入口）

所有 tool 遵循第六章的统一执行契约。工具统一用 Python（与数据库交互方便），shell 包装按需提供。

#### tools/db.py — 数据库管理

```
功能: 数据库连接、schema migration、通用查询
被其他 tool 引用，不直接由 skill 调用。
启动时自动检查 schema 版本，执行必要的 migration。
```

#### tools/archive.py — 成品归档

```
用法: python tools/archive.py --persona <p> --platform <pl> --title "<t>" --file <f>
      [--review-json <path>] [--source-idea <idea_id>]

功能（按顺序）:
  1. 生成 content_id
  2. 创建 data/content/<content_id>/ 目录
  3. 复制文件到 data/content/<content_id>/content.md
  4. 在 contents 表插入记录（status=final）
  5. 在 status_log 表插入记录
  6. 在 daily_logs 表追加产出记录

幂等: content_id 已存在 → 更新文件和 review 数据，不重复插入

stdout (JSON): {"content_id":"...","file_path":"...","status":"final"}
```

#### tools/inbox.py — 灵感入库

```
用法: python tools/inbox.py --title "<t>" --content "<c>" --tags "<tags>"

功能:
  1. 生成 idea_id (UUID)
  2. 写入 data/content/inbox/<idea_id>.md
  3. 在 ideas 表插入记录

stdout (JSON): {"idea_id":"...","file_path":"..."}
```

#### tools/daily.py — 每日记录

```
用法: python tools/daily.py <子命令>

子命令:
  read [date|yesterday]   — stdout: 日记内容（JSON）
  write --plan "<text>"   — 创建/更新今日日记
  append "<message>"      — 追加产出记录
  summary                 — stdout: {"active_contents": N, "pending_ideas": N, "recent_outputs": [...]}
```

#### tools/knowledge.py — 知识检索

```
用法: python tools/knowledge.py search "<query>" [--scope wiki,research] [--limit 5]

功能:
  在 data/content/knowledge/ 下搜索。
  策略: 文件名匹配 + 全文搜索（grep），按相关度排序。

stdout: 匹配的知识片段（每条带文件路径和摘要）
无匹配: stdout 为空，exit 0
```

#### tools/validate_review.py — 评审校验

```
用法: python tools/validate_review.py <json_file>

校验:
  1. 合法 JSON（去除可能的 code block 包裹）
  2. 必需字段存在
  3. scores 恰好 5 个维度，每个 0-2
  4. total == sum(scores)
  5. pass == (total >= 7)
  6. pass=false 时 feedback 不为 null

stdout: 校验通过的 JSON
exit 1 时 stderr: 第一条不满足的规则
```

#### tools/trace.py — 执行痕迹

```
用法: python tools/trace.py <子命令> <task_id> [参数]

子命令:
  start <task_id> "<type>" "<summary>"
  log <task_id> "<message>"
  fail <task_id> "<reason>"
  end <task_id> "<status>" "<summary>"
  show <task_id>               — stdout: 该任务的完整痕迹

存储: traces 表

注意: trace 失败不阻塞主流程。skill 中调用时应 2>/dev/null || true
```

#### tools/publish.py — 发布管理

```
用法: python tools/publish.py <子命令>

子命令:
  list [--status <s>] [--format json]  — 查询发布记录或 final 内容
  create --content-id <id> --persona <p> --title "<t>"  — 创建发布任务
  done --id <pub_id> --url "<url>"  — 标记已发布
```

#### tools/metrics.py — 数据采集

```
用法: python tools/metrics.py <子命令>

子命令:
  record --pub-id <id> --views N --likes N --collects N --comments N --shares N
  remind  — 展示待采集提醒
```

---

## 六、Tool 执行契约

### 6.1 Exit Code

| Code | 语义 | 主会话应对 |
|------|------|-----------|
| 0 | 完全成功 | 解析 stdout，继续 |
| 1 | 参数/输入错误 | 不重试，检查参数或提示用户 |
| 2 | 部分成功 | stdout 有已完成部分，stderr 说明失败部分 |
| 3 | 系统错误 | 不重试，展示 stderr |

### 6.2 输出格式

| 通道 | 用途 | 格式 |
|------|------|------|
| stdout | 机器可读结果 | JSON 或结构化文本 |
| stderr | 人类可读信息 | 自由文本 |

### 6.3 幂等性

| Tool | 策略 |
|------|------|
| archive.py | content_id 存在 → 更新文件和 review，不重复插入 |
| inbox.py | 每次生成新 UUID，天然无冲突 |
| daily.py write | 已存在 → 合并更新 |
| daily.py append | 追加操作，天然幂等 |
| trace.py | 追加日志，天然幂等 |
| validate_review.py | 无状态 |

### 6.4 archive.py 失败恢复

| 已完成步骤 | 未完成 | exit code | 说明 |
|-----------|--------|-----------|------|
| 1-3（文件已写入） | 4-6（数据库未注册） | 2 | stdout 返回文件路径，stderr 说明数据库失败 |
| 1-4（数据库已注册） | 5-6（日志未追加） | 0 | 日志是 best-effort，不影响核心功能 |
| 1 失败 | 全部 | 3 | 无副作用 |

**原则：文件落盘是最重要的。文件成功就不算全失败。**

---

## 七、统一评审契约

### 7.1 框架

- **5 个维度**，每维度 0-2 分，总分 10
- **通过**：≥ 7 分
- **写作迭代**：最多 3 轮
- **Reviewer 重试**：最多 2 次（JSON 校验失败时）

### 7.2 JSON Schema

```json
{
  "type": "object",
  "required": ["total", "pass", "scores", "feedback", "highlights"],
  "properties": {
    "total": { "type": "integer", "minimum": 0, "maximum": 10 },
    "pass": { "type": "boolean" },
    "scores": {
      "type": "object",
      "minProperties": 5, "maxProperties": 5,
      "additionalProperties": { "type": "integer", "minimum": 0, "maximum": 2 }
    },
    "feedback": { "type": ["string", "null"] },
    "highlights": { "type": "string" }
  }
}
```

### 7.3 校验失败兜底

```
review_raw.json → validate_review.py
  ├─ exit 0 → 使用
  └─ exit 1 → 重试 Reviewer（最多 2 次）
                ├─ 成功 → 使用
                └─ 仍失败 → 跳过自动评审，展示稿件给用户自行判断
```

---

## 八、知识检索机制

### 8.1 存储

```
data/content/knowledge/
├── wiki/          # 原子知识词条（一概念一文件）
│   ├── 水逆.md
│   ├── 土星回归.md
│   └── INTJ.md
└── research/      # 研究笔记
    └── 2026年土星换座影响分析.md
```

### 8.2 检索流程

```
/create 的 Step 4b:
  素材关键词 → python tools/knowledge.py search "水逆 占星"
                    │
                    ▼ stdout: 匹配的知识片段
                    │
              追加到 writer 输入的素材段
```

### 8.3 设计原则

| 原则 | 说明 |
|------|------|
| 检索在主会话完成 | sub-agent 不接触 data/ |
| 无匹配时静默跳过 | 知识检索是增强，不是前置条件 |
| 结果追加到素材段 | 不单独成文件，减少 writer 输入复杂度 |

---

## 九、可观测性与人工接管

### 9.1 执行痕迹

存储在 `traces` 表，按 task_id 查询：

```
[2026-03-31 14:00:01] START create chongxiaoyu xiaohongshu
[2026-03-31 14:00:05] LOG   素材准备完成，知识检索返回 2 条
[2026-03-31 14:00:45] LOG   Writer 第 1 轮完成
[2026-03-31 14:01:10] LOG   Reviewer 第 1 轮: total=6, pass=false
[2026-03-31 14:01:50] LOG   Writer 第 2 轮完成（改稿）
[2026-03-31 14:02:15] LOG   Reviewer 第 2 轮: total=8, pass=true
[2026-03-31 14:02:16] LOG   用户确认: 归档
[2026-03-31 14:02:18] END   success content_id=chongxiaoyu_xiaohongshu_20260331_shuini
```

### 9.2 中间产物保留

`/tmp/autowrite/<task_id>/` 保留所有中间文件：

| 文件 | 内容 |
|------|------|
| writer_input.md | Writer 完整输入 |
| draft.md | 最终稿件 |
| draft_v1.md, draft_v2.md | 每轮草稿 |
| review_raw.json | Reviewer 原始输出 |
| review.json | 校验后的评审结果 |

清理时机：下次 /create 时清理上一次的临时目录。

### 9.3 人工接管点

| 节点 | 行为 | 可跳过 |
|------|------|--------|
| /create Step 9 | 必须等用户确认才归档 | 否 |
| /collect Step 4 | 用户选择哪些灵感入库 | 否 |
| /select Step 3 | 用户逐条确认推荐 | 否 |
| /publish done | 用户手动填入发布链接 | 天然人工 |
| Reviewer 校验失败 | 展示稿件，用户自行判断 | 自动触发 |
| archive.py exit 2 | 提示：文件已存但数据库未注册 | 自动触发 |

### 9.4 trace 不阻塞

trace.py 失败不阻塞主流程：
```bash
python tools/trace.py log <task_id> "message" 2>/dev/null || true
```

---

## 十、数据流全景

### 10.1 /create 完整流程

```
用户: /create chongxiaoyu xiaohongshu 水逆求生指南

  trace.py start ─────────────────────────────── 任务开始
      │
  CLAUDE.md → skills/create.md → personas/.../index.md
      │
  personas/.../platforms/xiaohongshu.md ──── 200 行上下文
      │
  knowledge.py search "水逆 占星" ──── 返回知识片段
      │
  ┌─ Writer sub-agent ───────────────┐
  │ writer.md + 上下文 + 素材 + 知识   │
  │ → /tmp/.../draft.md              │
  └──────────────────────────────────┘
      │
  ┌─ Reviewer sub-agent ─────────────┐
  │ reviewer.md + 上下文 + draft      │
  │ → /tmp/.../review_raw.json       │
  └──────────────────────────────────┘
      │
  validate_review.py ──── exit 0: 校验通过
      │
      ├─ pass=false, 轮次<3 → Writer 改稿
      └─ pass=true ↓
  ┌─ 人工确认 ─┐
  │ 展示稿件    │
  │ 等待确认    │
  └─────────────┘
      │ 确认
  ┌─ archive.py ─────────────────────────────────┐
  │ 1. 生成 content_id                            │
  │ 2. 写入 data/content/<id>/content.md（文件）   │
  │ 3. 插入 contents 表 status=final（数据库）      │
  │ 4. 插入 status_log                             │
  │ 5. 追加 daily_logs                             │
  └───────────────────────────────────────────────┘
      │
  trace.py end ───────────────────────────── 任务结束
```

### 10.2 数据桥梁：/create → /select → /publish

```
/create:
  archive.py → contents 表 (status=final, content_id=xxx)
                       │
                       │  publish.py list --status final
                       ▼
/select:
  候选列表 → Selector Agent → 用户确认
                       │
                       │  publish.py create --content-id xxx
                       ▼
  publications 表 (content_id=xxx, status=draft)
                       │
                       │  用户手动发布
                       ▼
/publish done:
  publications.status=published, post_url=...
                       │
                       ▼
/publish metrics:
  metrics 表 (views, likes, ...)
```

**content_id 是贯穿全生命周期的稳定主键。**

### 10.3 系统边界图

```
┌──────────────────────────────┐
│          Agent 世界           │
│                              │
│  主会话:                      │
│    读 skills/ personas/       │
│    调用 sub-agents            │
│    调用 tools（唯一出口）       │
│                              │
│  Sub-agents:                 │
│    读: 注入的上下文（内存）     │
│    写: /tmp/autowrite/（临时） │
│    不接触 data/               │
│                              │
└──────────────┬───────────────┘
               │ 调用 tools/
               ▼
┌──────────────────────────────┐
│        tools/（桥梁层）        │
│                              │
│  archive.py  → 文件 + DB     │
│  inbox.py    → 文件 + DB     │
│  daily.py    → DB            │
│  knowledge.py← 文件           │
│  publish.py  → DB            │
│  metrics.py  → DB            │
│  trace.py    → DB            │
│                              │
└──────────────┬───────────────┘
               │
      ┌────────┴────────┐
      ▼                 ▼
┌──────────┐    ┌──────────────┐
│ autowrite│    │ data/content/│
│   .db    │    │   (文件)      │
│ (索引)    │    │   (本体)      │
└──────────┘    └──────────────┘
```

---

## 十一、新增人设指南

4 步，不改任何现有代码：

1. `mkdir -p personas/<id>/platforms`
2. 编写 `index.md`（路由索引）
3. 编写 `platforms/<platform>.md`（人设声音 + 格式 + 评审标准 + 范文）
4. 注册账号：`python tools/publish.py add-persona --id <id> --name "<name>"`

---

## 十二、迁移计划

### Phase 1 — 创建新结构

1. 创建目录：`agents/`、`personas/`、`skills/`、`tools/`、`data/`、`templates/`
2. 编写 `tools/db.py` 和 schema migration
3. 初始化 `autowrite.db`

### Phase 2 — 内容迁移

4. 从现有人设文件整合 `personas/` 下的 index.md 和 platform.md
5. 从现有 agent 定义提取 `agents/` 下的通用模板
6. 重写 CLAUDE.md 为索引格式
7. 编写 skills（含 trace 和人工确认点）
8. 统一播客评审为 10 分制

### Phase 3 — 工具开发

9. 实现所有 tools/*.py（archive、inbox、daily、knowledge、validate_review、trace、publish、metrics）
10. 为每个 tool 编写 exit code 和 stdout 格式测试

### Phase 4 — 数据迁移

11. 从现有 $VAULT_PATH 导入知识库到 `data/content/knowledge/`
12. 从现有 distribution.db 导入数据到 `autowrite.db`
13. 从现有 60_Published/ 导入成品到 `data/content/`

### Phase 5 — 验证与清理

14. 集成测试：`/create` → 确认文件和数据库都有记录
15. 集成测试：`/select` → 确认能查到 /create 归档的内容
16. 集成测试：`/collect`、`/publish`、`/daily`
17. 删除旧目录：`social-media/`、`podcast/`、`99_System/`、`web-ui/`
18. 更新 `.gitignore`（加入 `data/`）和 `requirements.txt`

---

## 十三、设计决策记录

| # | 决策 | 理由 |
|---|------|------|
| D1 | Writer 和 Reviser 不拆分 | 改稿 = 写作 + 反馈，拆分导致 80% prompt 重复 |
| D2 | 归档/发布等做成 Tool 而非 Agent | 确定性逻辑不需要 AI |
| D3 | 播客统一为人设的一个 platform | 消除独立生产线，复用 agent 模板 |
| D4 | 评审统一 10 分制 | 消除社媒 10 分 vs 播客 60 分的割裂 |
| D5 | 平台文件自包含声音+格式+评审+范文 | sub-agent 只读 1 个文件 |
| D6 | CLAUDE.md 只做索引 | 渐进式披露 L0 |
| D7 | 每个文件只被一种角色在一个时机读取 | 消除多用途文件的维护歧义 |
| D8 | 不引入额外编排层 | Claude Code 的 skill 本身就是编排器 |
| D9 | 所有数据 I/O 通过 tools/ 收口 | Agent 不需要知道存储内部结构 |
| D10 | archive.py 同时注册数据库 | 桥接 /create 产出与 /select 候选池 |
| D11 | knowledge.py 提供知识检索 | 保持知识库可被稳定检索注入 |
| D12 | validate_review.py 做机器校验 | LLM 输出不可靠，必须结构化校验 |
| D13 | trace.py 记录执行痕迹，失败不阻塞 | 需要审计但不能影响主流程 |
| D14 | /create 归档前必须人工确认 | 内容发布后无法撤回 |
| D15 | Tool 统一 exit code 规范 | 主会话机器化判断成功/失败/部分成功 |
| D16 | Sub-agent 只写 /tmp/ | 隔离写入风险 |
| D17 | SQLite 索引 + 文件本体 | 数据库管状态查询，文件保证内容永久本地留存 |
| D18 | 自包含在项目目录，去掉 $VAULT_PATH | 不依赖外部目录，clone 即可用 |
| D19 | tools 统一用 Python | 与数据库交互方便，类型安全 |
| D20 | Web UI 不在本次范围 | 聚焦 Agent 架构 |
