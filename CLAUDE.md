# Claude Workflows 项目规则

## 系统架构

本项目是**纯工厂（工具/代码）**仓库，通过 Git 管理。
数据仓库独立存放于 `$VAULT_PATH`（默认 `~/Desktop/vault/`），不纳入 Git。

### 数据仓库（$VAULT_PATH，独立于 Git）
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
| `99_System/` | 模板、配置、归档 |

> 仓库路径通过 `.env` 中的 `VAULT_PATH` 环境变量配置。
> 所有脚本和 skills 中提到的 `00_Inbox/`、`10_Daily/` 等目录，均位于 `$VAULT_PATH` 下。

### 工厂层（本 Git 仓库）
- `social-media/` — 社媒生产线（.claude/ + tools/）
- `podcast/` — 播客生产线（.claude/ + tools/）
- `writing/` — 写作生产线（预留）
- `data-analysis/` — 数据分析生产线（预留）
- `99_System/templates/` — 模板文件

---

## 核心规则

### 1. 工厂与仓库分离
- 本 Git 仓库**只放代码、工具、配置文件**
- 所有数据文件（灵感、日记、成品、数据库）**只存放在 $VAULT_PATH**
- 工厂是无状态的，不保存任何产出数据

### 2. 产出归仓规则
每次生产完成后，必须执行以下归仓操作（写入 $VAULT_PATH）：
- **成品终稿** → `60_Published/<生产线类型>/YYYY-MM-DD_标题.md`
- **有价值的中间产物** → `30_Research/` 或 `50_Resources/`
- **临时中间产物** → 不保存

### 3. 状态回写规则
- 如果 `20_Project/` 中存在对应的项目文件 → 在 Progress 段追加一条记录
- 如果不存在对应项目 → 跳过，不强制立项
- 每次生产完成 → 在 `10_Daily/YYYY-MM-DD.md` 追加产出记录
- 如果当日文件不存在 → 基于 `99_System/templates/daily.md` 创建

### 4. 素材读取规则
- 优先从 $VAULT_PATH 的仓库目录读取已有素材
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
- `.secrets/` 目录位于 $VAULT_PATH，不在 Git 仓库中

---

## 环境变量

在 `.env` 文件中配置（已加入 .gitignore）：

```
VAULT_PATH=~/Desktop/vault
```

---

## 小红书采集与发布

**唯一允许的工具：`social-media/tools/MediaCrawler/`**（基于 [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)）

### 为什么只用 MediaCrawler

- 通过 CDP 协议复用用户已登录的 Chrome，**不启动新浏览器、不启动无头浏览器**
- 通过浏览器 JS 环境获取签名参数，**不逆向 API、不直接构造请求**
- 内置频率控制、登录态缓存、反检测机制
- 支持关键词搜索（search）、指定笔记（detail）、创作者主页（creator）三种模式

### 启动前置条件

确保 Chrome 已带调试端口启动（MediaCrawler 配置中 `ENABLE_CDP_MODE = True`，`CDP_DEBUG_PORT = 9222`）：

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/chrome-xhs-debug"
```

- Profile 目录 `~/chrome-xhs-debug` 保留小红书登录态
- 首次使用需手动登录，后续启动自动保持
- 验证端口：`curl -s http://127.0.0.1:9222/json/version`

### 使用方式

```bash
cd social-media/tools/MediaCrawler

# 关键词搜索（修改 config/base_config.py 中的 KEYWORDS 和 CRAWLER_TYPE="search"）
python3 main.py

# 指定笔记采集（修改 config/xhs_config.py 中的 XHS_SPECIFIED_NOTE_URL_LIST，CRAWLER_TYPE="detail"）
python3 main.py

# 创作者主页（修改 config/xhs_config.py 中的 XHS_CREATOR_ID_LIST，CRAWLER_TYPE="creator"）
python3 main.py
```

采集结果默认保存为 JSONL 格式，需转换后存入 `$VAULT_PATH/00_Inbox/`。

### 严格禁止

- ❌ **禁止**自己编写 Playwright 脚本直接操作小红书页面
- ❌ **禁止**使用 Playwright MCP 工具导航小红书页面
- ❌ **禁止**直接调用小红书 API（curl/httpx/requests）
- ❌ **禁止**启动无头浏览器访问小红书
- ❌ **禁止**短时间内反复页面跳转（触发限流会导致封号）

所有小红书相关的采集、发布操作，**必须且只能**通过 MediaCrawler 进行。

---

## 浏览器环境（非小红书场景）

其他 skill（`/collect` 非小红书 URL、`/publishing` 等）可使用 Playwright MCP 连接已登录的 Chrome。

### Playwright MCP 配置

配置文件：`~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/playwright/.mcp.json`

```json
{
  "playwright": {
    "command": "npx",
    "args": [
      "@playwright/mcp@latest",
      "--cdp-endpoint", "http://127.0.0.1:9222"
    ]
  }
}
```

> **注意**：不要同时传 `--user-data-dir`，否则 MCP 会忽略 CDP 连接，转而启动新的无头浏览器。

### 使用规则

- **绝不启动新浏览器实例**，只连接用户已打开的 Chrome
- 遇到验证码立即停止，通知用户手动处理

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
