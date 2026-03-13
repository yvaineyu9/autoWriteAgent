# Claude Workflows 项目规则

## 系统架构

本项目分为**仓库层（数据）**和**工厂层（工具）**两层，生产与存储严格分离。

### 仓库层（00-99 目录）
| 目录 | 用途 |
|------|------|
| `00_Inbox/` | 灵感速记，先捕获再处理 |
| `10_Daily/` | 每日记录，YYYY-MM-DD.md 格式 |
| `20_Project/` | 项目跟踪，C.A.P. 格式（Context/Actions/Progress） |
| `30_Research/` | 深度研究笔记 |
| `40_Wiki/` | 原子级知识词条 |
| `50_Resources/` | 参考资料、下载素材 |
| `60_Published/` | 成品归档（按平台分子目录） |
| `70_Distribution/` | 分发数据中心（SQLite 数据库，存储发布记录和平台数据） |
| `90_Plans/` | 临时计划文件（research/kickoff 生成，用户确认后执行） |
| `99_System/` | 模板、配置、归档 |

### 工厂层（生产线目录）
- `social-media/` — 社媒生产线
- `podcast/` — 播客生产线
- `writing/` — 写作生产线（预留）
- `data-analysis/` — 数据分析生产线（预留）

---

## 核心规则

### 1. 生产与存储分离
- 工厂层目录（social-media/, podcast/, writing/, data-analysis/）**只放 .claude/ 配置文件和 tools/ 无状态工具**
- 所有产出文件、数据文件**只能存放在仓库层目录**（00-99）
- 生产线是无状态的，不保存任何产出

### 2. 产出归仓规则
每次生产完成后，必须执行以下归仓操作：
- **成品终稿** → `60_Published/<生产线类型>/YYYY-MM-DD_标题.md`
- **有价值的中间产物** → `30_Research/` 或 `50_Resources/`（判断标准：完整访谈/重要素材保存，临时格式转换不保存）
- **临时中间产物** → 不保存

### 3. 状态回写规则
- 如果 `20_Project/` 中存在对应的项目文件 → 在 Progress 段追加一条记录
- 如果不存在对应项目 → 跳过，不强制立项
- 每次生产完成 → 在 `10_Daily/YYYY-MM-DD.md` 追加产出记录
- 如果当日文件不存在 → 基于 `99_System/templates/daily.md` 创建

### 4. 素材读取规则
- 优先从仓库目录读取已有素材（Inbox、Research、Wiki、Resources）
- 用户直接提供的外部 URL 或文本可以跳过仓库直接使用
- 写作时主动搜索 `40_Wiki/` 中的相关知识词条
- 引用知识笔记时使用 wikilink 格式 `[[笔记名]]`

### 5. 自动保存与推送
每当完成对本项目文件的修改（包括新增、编辑、删除），在任务结束前必须：
1. `git add .`
2. 根据修改内容自动生成简洁的中文提交说明
3. `git commit` 并 `git push`

不需要用户提醒，自己判断时机，改完就提交。

### 6. 安全规则
- 绝对不要将 .env、密钥、token 写入任何文件
- 敏感信息只通过环境变量引用

---

## 可用命令

### 仓库管理（全局）
| 命令 | 用途 |
|------|------|
| `/start-my-day` | 每日规划，回顾 Inbox 和项目 |
| `/kickoff` | 将想法转化为项目 |
| `/research` | 深度研究并建档 |
| `/ask` | 快速问答 |
| `/brainstorm` | 头脑风暴 |
| `/parse-knowledge` | 非结构化文本入库 |
| `/archive` | 归档已完成项目 |
| `/collect` | 内容收集（URL/文本 → Inbox，支持浏览器抓取） |
| `/save-and-push` | 保存并推送到 GitHub |

### 社媒生产线（cd social-media/）
| 命令 | 用途 |
|------|------|
| `/content-creation` | 文案创作（写+审循环） |
| `/video-editing` | 视频剪辑 |
| `/ig-processor` | IG 视频下载处理 |
| `/publishing` | 多账号发布管理、数据采集（基于 distribution 工具） |

### 播客生产线（cd podcast/）
| 命令 | 用途 |
|------|------|
| `/script-creation` | 播客稿件创作（写+审循环） |
| `/transcription` | 音视频转录 |
| `/show-notes` | 节目简介生成 |
