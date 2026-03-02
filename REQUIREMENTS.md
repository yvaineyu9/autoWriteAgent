# Claude Workflows 升级需求文档

## 一、项目定位

将现有 `claude-workflows` 项目升级为 **内容管理 + 内容生产** 一体化系统，整合 OrbitOS 的知识管理能力与现有的 AI 生产线工作流。

核心原则：**生产与存储分离**
- 仓库（OrbitOS 目录）：负责所有数据的存储、归档、检索
- 工厂（生产线目录）：负责内容生产，不存储任何数据，产出物写入仓库

---

## 二、系统架构

```
claude-workflows/
│
│  ═══ 仓库层（数据）═══
├── 00_Inbox/                    # 灵感收集箱
├── 10_Daily/                    # 每日记录
├── 20_Project/                  # 项目跟踪 & 内容日历
├── 30_Research/                 # 深度研究笔记
├── 40_Wiki/                     # 原子级知识词条
├── 50_Resources/                # 参考资料 & 精选内容
├── 60_Published/                # 成品归档
│   ├── social-media/            #   社媒发布内容存底
│   ├── podcast/                 #   播客稿件存底
│   └── writing/                 #   其他写作成品存底
├── 99_System/                   # 系统配置（模板、Prompt 模板）
│
│  ═══ 工厂层（工具）═══
├── social-media/                # 社媒生产线
│   └── .claude/
│       ├── skills/              #   工作流定义
│       └── agents/              #   执行者定义
├── podcast/                     # 播客生产线
│   └── .claude/
│       ├── skills/
│       └── agents/
├── data-analysis/               # 数据分析生产线（预留）
│   └── .claude/
│       ├── skills/
│       └── agents/
├── writing/                     # 写作生产线（预留）
│   └── .claude/
│       ├── skills/
│       └── agents/
│
│  ═══ 全局配置 ═══
├── .claude/
│   └── skills/
│       └── save-and-push/       # 通用：自动保存推送
├── CLAUDE.md                    # 项目规则（Claude 自动读取）
├── .gitignore
└── .env.example
```

---

## 三、仓库层详细定义

### 00_Inbox/ — 灵感收集箱
- **用途**：随时记录灵感、热点、想法，不需要整理
- **规则**：先捕获再处理，每条一个 md 文件或统一写在日记中
- **流向**：定期处理，分流到 Research / Project / 直接进生产线
- **谁写入**：用户手动 / OrbitOS 的 `/start-my-day`
- **谁读取**：所有生产线（作为素材来源之一）

### 10_Daily/ — 每日记录
- **用途**：日记，作为知识图谱的锚点
- **格式**：`YYYY-MM-DD.md`
- **内容**：当日任务、产出记录、Inbox 处理记录、项目进展
- **谁写入**：OrbitOS 的 `/start-my-day` / 生产线完成任务后自动追加记录
- **谁读取**：OrbitOS skills（回顾、规划）

### 20_Project/ — 项目跟踪
- **用途**：管理所有进行中的内容项目（系列内容、大型选题）
- **结构**：每个项目一个 md 文件，采用 C.A.P. 格式
  - **Context**：项目目标、成功标准
  - **Actions**：分阶段任务清单
  - **Progress**：带时间戳的进度更新
- **示例**：`20_Project/小红书占星系列.md`、`20_Project/播客第三季.md`
- **谁写入**：OrbitOS 的 `/kickoff` 创建 / 生产线完成后回写进度
- **谁读取**：生产线（了解项目上下文）/ OrbitOS（项目管理）
- **注意**：不是所有内容都需要立项，小内容可以跳过此步直接进生产线

### 30_Research/ — 研究笔记
- **用途**：深度研究的沉淀
- **规则**：用 wikilink 关联到 Wiki 词条和 Project
- **示例**：`30_Research/2026年土星换座影响分析.md`
- **谁写入**：OrbitOS 的 `/research` / 生产线的转录等中间产物（有沉淀价值的）
- **谁读取**：生产线（作为素材来源之一）

### 40_Wiki/ — 知识词条
- **用途**：原子级概念，可被多个项目和内容复用
- **规则**：每个概念一个文件，简短精确
- **示例**：`40_Wiki/土星回归.md`、`40_Wiki/INTJ.md`、`40_Wiki/依附理论.md`
- **谁写入**：OrbitOS 的 `/research` 自动提取 / 用户手动
- **谁读取**：生产线 writer agent（引用专业概念时查阅）

### 50_Resources/ — 参考资料
- **用途**：外部精选内容、参考链接、截图、下载的素材
- **规则**：标注来源，简要摘要
- **谁写入**：生产线的中间产物（如 IG 关键帧、下载的参考资料）/ 用户手动
- **谁读取**：生产线（作为素材来源之一）

### 60_Published/ — 成品归档
- **用途**：所有审核通过的内容终稿存底
- **结构**：按生产线类型分目录
  ```
  60_Published/
  ├── social-media/
  │   └── 2026-03-02_水逆生存指南.md
  ├── podcast/
  │   └── EP15_土星回归深度解析.md
  └── writing/
  ```
- **规则**：由生产线 skill 自动写入，文件名格式 `日期_标题.md`
- **谁写入**：生产线 skill（审核通过后自动归档）
- **谁读取**：用户回顾 / OrbitOS `/archive` 清理

### 99_System/ — 系统配置
- **用途**：模板文件、通用 Prompt 模板
- **内容**：日记模板、项目模板、Research 模板等
- **谁写入**：用户 / 系统初始化
- **谁读取**：OrbitOS skills（创建新文件时引用模板）

---

## 四、工厂层详细定义

### 核心原则
1. **无状态**：生产线目录下不存储任何产出文件
2. **产出归仓**：所有成品自动写入 `60_Published/` 对应子目录
3. **中间产物分流**：有沉淀价值的写入 `30_Research/` 或 `50_Resources/`，临时的不保存
4. **状态回写**：如果存在对应 Project 文件，生产完成后更新其进度
5. **日志追加**：生产完成后在当日 `10_Daily/` 文件中追加一条产出记录

### social-media/ 社媒生产线

#### Skills（工作流）
| Skill | 功能 | 输入 | 输出位置 |
|-------|------|------|----------|
| content-creation | 文案创作（写+审循环） | 主题/素材 | 60_Published/social-media/ |
| video-editing | 视频剪辑方案 + 执行 | 视频文件/描述 | 60_Published/social-media/ |
| ig-processor | IG 视频下载+关键帧提取 | URL | 50_Resources/ |
| publishing | 发布排期管理 | 指令 | 20_Project/ |

#### Agents（执行者）
| Agent | 角色 | 能力 |
|-------|------|------|
| writer | 社媒写手 | 根据素材+平台要求生成文案 |
| reviewer | 审核员 | 按 standards.md 独立评分审核 |
| video-editor | 剪辑师 | ffmpeg 分析+剪辑执行 |

### podcast/ 播客生产线

#### Skills（工作流）
| Skill | 功能 | 输入 | 输出位置 |
|-------|------|------|----------|
| script-creation | 播客稿件创作（写+审循环） | URL/文本素材 | 60_Published/podcast/ |
| transcription | 音视频转录 | URL/文件路径 | 30_Research/（有价值时）或临时使用不保存 |
| show-notes | 节目简介生成 | 稿件内容 | 60_Published/podcast/ |

#### Agents（执行者）
| Agent | 角色 | 能力 |
|-------|------|------|
| writer | 播客写手 | 小狗仔+小刀双主持人风格对话稿 |
| reviewer | 审核员 | 按 standards.md 独立评分审核 |

---

## 五、仓库与工厂的数据流关系

### 5.1 总览：谁读谁、谁写谁

```
                    ┌──────────────────────────────┐
                    │         仓库层（数据）         │
                    │                              │
                    │  00_Inbox ──┐                │
                    │  30_Research ┼─ 素材来源 ──────┼──→ 工厂读取
                    │  40_Wiki ───┤                │
                    │  50_Resources┘                │
                    │                              │
                    │  60_Published ←───────────────┼── 工厂写入（成品）
                    │  50_Resources ←───────────────┼── 工厂写入（有价值的中间产物）
                    │  30_Research  ←───────────────┼── 工厂写入（有价值的中间产物）
                    │  20_Project   ←───────────────┼── 工厂写入（状态回写）
                    │  10_Daily     ←───────────────┼── 工厂写入（产出日志）
                    │                              │
                    └──────────────────────────────┘
```

### 5.2 素材读取规则

生产线可以从以下仓库目录**读取**素材，不限于单一来源：

| 素材来源 | 场景举例 |
|---------|---------|
| `00_Inbox/` | 用户速记了一个灵感，直接丢给生产线写成帖子 |
| `30_Research/` | 之前做过的深度研究，拿来写播客稿 |
| `40_Wiki/` | 写稿时引用某个专业概念的定义 |
| `50_Resources/` | 用之前下载的 IG 关键帧做视频剪辑 |
| `20_Project/` | 读取项目上下文，了解系列内容的整体方向 |
| 外部输入 | 用户直接传入 URL 或文本，不经过仓库 |

**规则**：生产线 skill 在接受任务时，根据用户输入判断素材来源。如果用户给了具体文件路径或仓库中的文件名，从对应目录读取；如果给了外部 URL 或直接文本，直接使用。

### 5.3 产出写入规则

生产线的产出根据类型写入不同的仓库目录：

| 产出类型 | 写入目录 | 触发条件 | 文件命名 |
|---------|---------|---------|---------|
| **成品终稿** | `60_Published/<生产线>/` | 审核通过 | `YYYY-MM-DD_标题.md` |
| **有价值的中间产物** | `30_Research/` 或 `50_Resources/` | skill 判断有沉淀价值 | 按内容命名 |
| **项目状态更新** | `20_Project/对应项目.md` | 存在对应 Project 文件时 | 在 Progress 段追加记录 |
| **每日产出记录** | `10_Daily/YYYY-MM-DD.md` | 每次生产完成 | 在当日文件追加一行 |

**判断中间产物是否值得保存的规则**：
- **保存**：转录了一段完整的访谈内容、下载了有参考价值的素材、提取了可复用的关键帧
- **不保存**：临时的格式转换文件、调试过程中的中间版本、已被最终成品包含的草稿

### 5.4 具体数据流：社媒内容创作

```
用户输入：/content-creation 写一篇关于水逆的帖子

读取 ← 40_Wiki/水逆.md（如果存在，获取专业定义）
读取 ← 30_Research/（如果有相关研究笔记）
       │
       ▼
   writer agent → 生成初稿
       │
       ▼
   reviewer agent → 审核（读取 standards.md）
       │
       ├─ 未通过 → 审核意见回 writer → 重新生成（最多3轮）
       │
       └─ 通过 ↓
              │
写入 → 60_Published/social-media/2026-03-02_水逆生存指南.md（成品归档）
写入 → 20_Project/小红书占星系列.md（追加进度，如果存在）
写入 → 10_Daily/2026-03-02.md（追加产出记录）
```

### 5.5 具体数据流：播客稿件创作

```
用户输入：/script-creation https://某个音频链接

Step 1：转录
       │
       ├─ 转录结果有沉淀价值？
       │   ├─ 是 → 写入 30_Research/转录_某某访谈.md
       │   └─ 否 → 仅在内存中传递给下一步
       │
       ▼
Step 2：writer agent → 基于转录内容生成播客稿
       │
       ▼
Step 3：reviewer agent → 审核
       │
       ├─ 未通过 → 审核意见回 writer → 重新生成（最多3轮）
       │
       └─ 通过 ↓
              │
写入 → 60_Published/podcast/EP15_土星回归深度解析.md（成品归档）
写入 → 20_Project/播客第三季.md（追加进度，如果存在该项目）
写入 → 10_Daily/2026-03-02.md（追加产出记录）
```

### 5.6 具体数据流：IG 视频处理

```
用户输入：/ig-processor https://instagram.com/xxx

Step 1：下载视频 + 提取关键帧
       │
写入 → 50_Resources/ig_xxx_关键帧/（关键帧图片，有参考价值）
写入 → 10_Daily/2026-03-02.md（追加记录）
```

### 5.7 具体数据流：灵感直接进生产线（跳过立项）

```
用户：我刚看到一个热点，直接帮我写一篇小红书帖子
（不经过 Inbox、不立项、直接开干）

用户直接输入文本素材
       │
       ▼
   writer agent → 生成初稿
       │
       ▼
   reviewer agent → 审核 → 通过
       │
写入 → 60_Published/social-media/2026-03-02_热点话题.md
写入 → 10_Daily/2026-03-02.md（追加产出记录）
       （没有 Project 文件，不做状态回写）
```

---

## 六、仓库内部流转规则

仓库内部的数据也有流转关系，由 OrbitOS 的 skills 驱动：

```
00_Inbox（灵感速记）
    │
    ├─ 值得深入？→ 30_Research（深度研究）→ 40_Wiki（提取概念）
    │
    ├─ 可以直接做？→ 生产线（直接生产）
    │
    └─ 是个大方向？→ 20_Project（立项跟踪）
```

| 流转路径 | 触发方式 | 谁执行 |
|---------|---------|--------|
| Inbox → Research | `/research <inbox中的选题>` | OrbitOS skill |
| Inbox → Project | `/kickoff <inbox中的想法>` | OrbitOS skill |
| Inbox → 生产线 | 直接将 Inbox 内容作为素材传给生产线 skill | 用户手动指定 |
| Research → Wiki | `/research` 过程中自动提取原子概念 | OrbitOS skill |
| Research → 生产线 | 将研究笔记作为素材传给生产线 skill | 用户手动指定 |
| Project → 生产线 | 按项目计划执行具体内容生产 | 用户手动触发 |
| 已处理的 Inbox 条目 | 标记为已处理或移动到对应目录 | OrbitOS `/start-my-day` |

---

## 七、OrbitOS 集成计划

### 引入的 OrbitOS 功能（作为仓库层的管理 skills）
| OrbitOS 命令 | 对应用途 | 读取 | 写入 | 适配改动 |
|-------------|---------|------|------|---------|
| /start-my-day | 每日规划，处理 Inbox，回顾项目 | 00_Inbox, 20_Project, 10_Daily | 10_Daily | 保持原样 |
| /kickoff | 将想法转化为项目 | 00_Inbox | 20_Project | 保持原样 |
| /research | 深度研究并建档 | 外部来源 / 00_Inbox | 30_Research, 40_Wiki | 保持原样 |
| /parse-knowledge | 非结构化文本入库 | 外部输入 | 30_Research / 40_Wiki | 保持原样 |
| /archive | 清理已完成项目 | 20_Project, 60_Published | 99_System/archive/ | 适配 60_Published 目录 |

### 不引入的部分
- OrbitOS 的 Obsidian 插件配置（.obsidian/）—— 按需手动配置
- OrbitOS 的示例数据 —— 不需要

---

## 八、CLAUDE.md 更新要求

升级后的 CLAUDE.md 需要包含以下规则：

### 8.1 自动保存推送（已有）
每次修改完自动 git add → commit → push。

### 8.2 生产与存储分离原则
- 工厂层目录（social-media/, podcast/, writing/, data-analysis/）**只放 .claude/ 配置文件**
- 所有产出文件、数据文件**只能存放在仓库层目录**（00-99）

### 8.3 产出归仓规则
- 成品终稿 → `60_Published/<生产线类型>/YYYY-MM-DD_标题.md`
- 有价值的中间产物 → `30_Research/` 或 `50_Resources/`
- 临时中间产物 → 不保存

### 8.4 状态回写规则
- 如果 `20_Project/` 中存在对应的项目文件 → 在 Progress 段追加一条记录
- 如果不存在对应项目 → 跳过，不强制立项
- 每次生产完成 → 在 `10_Daily/YYYY-MM-DD.md` 追加产出记录

### 8.5 素材读取规则
- 优先从仓库目录读取已有素材
- 用户直接提供的外部 URL 或文本可以跳过仓库直接使用
- 引用 Wiki 词条和 Research 笔记时使用 wikilink 格式

### 8.6 目录结构约定
- 仓库层：00_Inbox, 10_Daily, 20_Project, 30_Research, 40_Wiki, 50_Resources, 60_Published, 99_System
- 工厂层：social-media, podcast, writing, data-analysis
- 工厂目录下只允许存在 .claude/ 子目录

### 8.7 安全规则（已有）
- 绝对不要将 .env、密钥、token 写入任何文件
- 敏感信息只通过环境变量引用

---

## 九、实施步骤

1. 创建仓库层目录结构（00_Inbox 至 99_System，含子目录）
2. 创建 99_System/ 模板文件（日记模板、项目模板、Research 模板）
3. 引入 OrbitOS 的 skills（start-my-day、kickoff、research、parse-knowledge、archive）
4. 修改现有生产线 skills，增加产出归仓和状态回写逻辑
5. 更新 CLAUDE.md 项目规则
6. 更新 .gitignore（排除大文件、敏感信息）
7. 提交推送到 GitHub
