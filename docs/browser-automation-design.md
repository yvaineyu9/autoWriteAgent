# 浏览器自动化采集设计

> 一个引擎，两个场景：灵感采集 + 数据监控

---

## 一、技术选型

| 决策项 | 选型 | 说明 |
|--------|------|------|
| 浏览器引擎 | Playwright | 复用已有 Chrome profile，有头模式 |
| 登录态 | 系统 Chrome profile | 直接连接用户已登录的 Chrome，无需单独管理 cookie |
| 图片 OCR | Apple Vision（macOS 系统级） | Swift 小工具调用系统 OCR，中文准确率高，零成本 |
| 运行模式 | headed | 有头模式，规避反爬检测 |
| 调度方式 | 第一阶段 CLI，后续 OpenClaw 机器人下发 |

---

## 二、目录结构

```
tools/
├── browser/                      # 浏览器自动化模块
│   ├── __init__.py
│   ├── engine.py                 # Playwright 引擎封装
│   │   · connect_chrome()        #   连接已有 Chrome 实例
│   │   · new_page()              #   新建标签页
│   │   · safe_goto(url)          #   带重试和延迟的导航
│   │   · random_delay()          #   随机等待（反检测）
│   │
│   ├── xhs.py                    # 小红书页面解析器
│   │   · scrape_note(url)        #   单篇笔记完整采集
│   │   · scrape_metrics(url)     #   仅采集互动数据
│   │   · scrape_favorites()      #   收藏页批量采集
│   │   · scrape_account(url)     #   账号主页笔记列表
│   │
│   ├── ocr.py                    # Apple Vision OCR（Python 封装）
│   │   · ocr_image(path) → str
│   │   · ocr_bytes(bytes) → str
│   │   · ocr_screenshot(page, selector) → str
│   │
│   └── ocr_vision.swift          # Apple Vision 识别（编译为本地二进制）
│
├── scrape.py                     # CLI 入口：灵感采集
│   用法:
│     python tools/scrape.py note <url>           # 单篇采集
│     python tools/scrape.py favorites [--limit N] # 收藏页采集
│     python tools/scrape.py account <url> [--limit N]
│   输出:
│     → data/content/inbox/<uuid>.md + ideas 表
│
├── monitor.py                    # CLI 入口：数据监控
│   用法:
│     python tools/monitor.py run [--pub-id N]    # 单篇/全量巡检
│     python tools/monitor.py remind              # 待采提醒
│   输出:
│     → metrics 表 + publications.platform_status 更新
│
├── metrics.py                    # 已有，保留手动录入能力
├── inbox.py                      # 已有，被 scrape.py 调用
└── ...
```

---

## 三、浏览器引擎（engine.py）

### 连接方式

通过 Playwright 的 `connect_over_cdp` 连接用户已运行的 Chrome：

```python
# 用户需先以 remote-debugging 模式启动 Chrome：
# /Applications/Google Chrome.app/.../Google Chrome --remote-debugging-port=9222

async def connect_chrome(port=9222):
    playwright = await async_playwright().start()
    browser = await playwright.chromium.connect_over_cdp(f"http://localhost:{port}")
    context = browser.contexts[0]  # 复用已有的 context（含登录态）
    return context
```

### 反检测措施

- **固定 profile**：复用用户真实 Chrome，指纹天然真实
- **随机延迟**：每次操作间隔 1-3 秒随机等待
- **有头模式**：不使用 headless
- **不修改 navigator**：不注入 stealth 脚本（因为是真实 Chrome）

---

## 四、小红书解析器（xhs.py）

### 4.0 关键原则

小红书浏览器采集最关键的不是“页面能打开”，而是“确认已经进入真实帖子详情页”。

强规则：
- 优先从账号页卡片提取真实帖子链接，优先级为 `a.cover` > `a[href*="/explore/"]` > 其他链接。
- 账号页真实可用链接通常是 `/user/profile/<uid>/<note_id>?xsec_token=...&xsec_source=pc_user`。
- 不要主动把真实链接降级成裸 `https://www.xiaohongshu.com/explore/<note_id>`；裸链接在登录态浏览器里也可能落到壳页、推荐页或异常页。
- 详情页采集前必须确认 `#noteContainer` 存在；如果不存在，本次采集结果不可信。
- 点赞、收藏、评论必须限定在 `#noteContainer` 内提取，不能从整页随便找数字。
- 账号页卡片上的点赞只能当摘要参考，不可直接当最终 metrics 回填。
- 如果链接打不开详情页或未命中 `#noteContainer`，应返回 `platform_status=inaccessible`，不要写入假 metrics。
- 对账号同步来说，宁可把记录标成 `missing_from_profile`，也不要强行把线上内容映射到错误的库记录。

### 4.1 单篇笔记采集 `scrape_note(url)`

```
输入: 真实帖子详情链接，优先使用
  https://www.xiaohongshu.com/user/profile/<uid>/<note_id>?xsec_token=...
其次才是
  https://www.xiaohongshu.com/explore/<note_id>?xsec_token=...
输出: NoteData
```

**采集字段：**

| 字段 | 选择器/方式 | 必采 |
|------|-----------|------|
| note_id | 从 URL 提取 | ✅ |
| title | `#detail-title` 或 `.title` | ✅ |
| content_text | `.note-text` / `#detail-desc` | ✅ |
| author | `.author-wrapper .username` | ✅ |
| published_at | `.date` / 页面文字匹配 | ✅ |
| images[] | `.swiper-slide img` | ✅ |
| image_ocr[] | 每张图截图 → Claude Vision | ✅ |
| likes | `.like-wrapper .count` | ✅ |
| collects | `.collect-wrapper .count` | ✅ |
| comments | `.chat-wrapper .count` | ✅ |
| shares | 页面提取（可能不可见） | 尽量 |
| views | 页面提取（作者视角才有） | 尽量 |
| tags | `#detail-tags a` | 尽量 |
| source_url | 传入的 URL | ✅ |
| captured_at | 当前时间 | ✅ |

**容错规则：**
- 如果页面未进入 `#noteContainer`，整篇采集失败，不写假数据。
- 正文折叠 → 自动点击"展开"
- 轮播图 → 按顺序滑动并逐张截图 OCR
- 单张 OCR 失败 → 标记 `ocr_status: partial`，继续下一张
- 某字段抓不到 → 该字段置空，不放弃整篇

### 4.2 仅采互动数据 `scrape_metrics(url)`

轻量版，只提取数字：

```python
@dataclass
class MetricsData:
    likes: int
    collects: int
    comments: int
    shares: int | None
    views: int | None       # 仅作者视角可见
    platform_status: str    # normal / deleted / inaccessible / reviewing
    captured_at: str
```

**页面状态判断逻辑：**
- 正常加载且有内容 → `normal`
- 页面 404 或"内容已删除" → `deleted`
- "审核中"提示 → `reviewing`
- 加载超时或异常 → `inaccessible`
- 可见但互动数据异常低/隐藏 → `limited`

**注意：**
- `normal` 的前提不是“URL 打开了”，而是“进入了 `#noteContainer` 且互动区来自详情页容器内部”。
- 旧的裸 `explore/<note_id>` 链接可能把脚本带到错误页面，因此 `platform_status` 的判断必须基于 DOM，而不是仅基于 URL。

### 4.3 收藏页采集 `scrape_favorites(limit)`

```
入口: 用户收藏页（需登录态）
输出: list[NoteSummary]  # 每条含 note_id, title, author, cover_url, source_url
```

- 滚动加载更多，直到达到 limit 或无更多内容
- 每条只采摘要级信息
- 需要完整内容时再对单条调用 `scrape_note(url)`

### 4.4 账号主页 `scrape_account(url, limit)`

类似收藏页，采集指定账号的笔记列表。

**账号页卡片采集规则：**
- 优先读取 `a.cover` 的 href，这里通常带真实 `xsec_token`。
- `note_id` 需要支持从 `/user/profile/<uid>/<note_id>` 形式中提取。
- 卡片阶段只采：标题、作者、note_id、真实 `post_url`、封面图、卡片点赞。
- 详情正文、标签、收藏、评论不能在卡片阶段脑补。

---

## 五、OCR 模块（ocr.py + ocr_vision.swift）

使用 macOS 系统自带的 Apple Vision 框架，通过一个 Swift 小工具实现。

- `ocr_vision.swift` 编译为本地二进制（首次运行自动编译）
- `ocr.py` 封装 Python 调用接口（subprocess）
- 支持文件路径和 stdin 字节流两种输入
- 支持中文简繁体 + 英文，准确率高
- 零额外依赖，零 API 成本

```python
from browser.ocr import ocr_image, ocr_bytes, ocr_screenshot

text = ocr_image("path/to/image.png")
text = ocr_bytes(screenshot_bytes)
text = ocr_screenshot(playwright_page, selector=".image")
```

---

## 六、CLI 入口

### 6.1 scrape.py（灵感采集）

```bash
# 单篇采集
python3 tools/scrape.py note "https://www.xiaohongshu.com/explore/xxx"
# → 采集完整内容 → 写入 inbox + ideas 表
# → stdout: {"idea_id": "uuid", "title": "...", "file_path": "inbox/uuid.md"}

# 收藏页采集
python3 tools/scrape.py favorites --limit 20
# → 采集收藏页前 20 条 → 逐条完整采集 → 批量写入
# → stdout: {"count": 20, "ideas": [...]}

# 账号页采集
python3 tools/scrape.py account "https://www.xiaohongshu.com/user/profile/xxx" --limit 10
# → 采集账号最近 10 条笔记
```

**输出文件格式（inbox/<uuid>.md）：**

```markdown
# 标题

**作者**: xxx
**来源**: [小红书原文](url)
**发布时间**: 2026-03-20
**互动数据**: 👍 234 ⭐ 45 💬 12

## 正文

（原始正文内容）

## 图片文字

### 图1
（OCR 提取的文字）

### 图2
（OCR 提取的文字）

## 标签
#标签1 #标签2 #标签3
```

### 6.2 monitor.py（数据监控）

```bash
# 单篇监控
python3 tools/monitor.py run --pub-id 13
# → 打开 post_url → 采集互动数据 → 写入 metrics 表
# → stdout: {"publication_id": 13, "views": 500, "likes": 45, ...}

# 全量巡检（所有 published 且有 post_url 的记录）
python3 tools/monitor.py run
# → 逐条打开 → 采集 → 写入
# → stdout: {"checked": 5, "success": 4, "failed": 1, "results": [...]}

# 待采提醒（复用 metrics.py remind 逻辑）
python3 tools/monitor.py remind

# 账号全量对齐
python3 tools/monitor.py sync-account --persona yuejian --platform xiaohongshu --limit 30
# → 先按账号页当前可见内容回填真实 post_url / 平台状态，再决定哪些记录可继续 monitor
```

**写入规则：**
- `metrics` 表追加一条快照（不覆盖历史）
- `publications.platform_status` 更新为当前状态
- 采集失败时写 `publications.platform_failure_reason`
- 当前账号页未匹配到的已发布记录，可标记为 `platform_status=missing_from_profile`

---

## 七、与现有系统的集成

### 7.1 Skill 层面

| 现有 Skill | 新增能力 |
|-----------|---------|
| `/collect` | 识别小红书 URL → 调用 `scrape.py note` 代替纯文本采集 |
| `/publish` | 新增 `monitor` 子命令 → 调用 `monitor.py run` |

### 7.2 Vault 同步

`sync_vault.py` 已支持：
- 灵感文件同步到 `10_灵感/`
- Metrics 数据展示在 `00_看板/发布追踪.md`
- 采集后跑一次 sync 即可在 Obsidian 看到新内容

### 7.3 后续 OpenClaw 对接

OpenClaw 机器人下发任务时，本质就是远程调用这些 CLI 命令：

```
OpenClaw → SSH/API → python3 tools/scrape.py note <url>
OpenClaw → SSH/API → python3 tools/monitor.py run
```

CLI 接口设计好了，机器人对接只是调度层的事。

---

## 八、依赖与启动

### 依赖

```
# requirements.txt 新增
playwright>=1.40.0
```

OCR 使用 macOS 系统自带的 Apple Vision，无额外依赖。

### 环境初始化（一次性）

```bash
cd autoWriteAgent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Chrome debug 模式启动

```bash
# macOS
open -a "Google Chrome" --args --remote-debugging-port=9222
```

每次使用采集/监控功能前，确保 Chrome 以此方式启动。

---

## 九、实现顺序

| 阶段 | 内容 | 产出 |
|------|------|------|
| **P0** | browser/engine.py + 连接 Chrome | 能打开页面、复用登录态 |
| **P1** | browser/xhs.py scrape_note | 单篇笔记完整采集（含 OCR） |
| **P2** | scrape.py CLI + inbox 写入 | `/collect <url>` 端到端可用 |
| **P3** | browser/xhs.py scrape_metrics + monitor.py | 数据监控端到端可用 |
| **P4** | 收藏页 / 账号页批量采集 | 批量场景 |
| **P5** | Skill 集成 + sync_vault | 完整闭环 |
