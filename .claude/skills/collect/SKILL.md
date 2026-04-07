# /collect [素材源]

采集灵感：解析素材 → 自动过滤 → 去重 → 直接入库。

## 参数
- 素材源: URL / 文本 / 主题关键词（可选，不提供则交互式输入）

## 入库规则
- **互动门槛**：点赞 + 收藏 ≥ 500 才入库（可通过 `--min-engagement` 调整）。
- **图片文字笔记**：如果笔记正文较短但图片多（图片文字笔记），必须确保 OCR 完整识别所有图片内容。OCR 结果存入 inbox 文件的「图片文字」章节。
- **内容去重**（三层）：
  1. `note_id` 精确匹配
  2. `source_url` 精确匹配
  3. 标题相似度比对（标准化后完全匹配或互相包含）
- 符合条件的笔记直接入库，不需要人工确认。采集结束后展示汇总报告。

## 小红书浏览器采集规则
- 如果输入是小红书 URL，优先走浏览器采集，不要先让 LLM 凭网页摘要瞎猜。
- 如果输入是账号主页或收藏页，先用 `tools/scrape.py account|favorites` 拿卡片摘要，再按需要逐条补抓详情。
- 如果输入是单篇笔记，优先使用带 `xsec_token` 的真实链接；不要主动把链接降级成裸 `explore/<note_id>`。
- 只有在页面里确认进入真实详情容器 `#noteContainer` 后，才允许相信标题、正文、点赞、收藏、评论。
- 如果没有进入 `#noteContainer`，这次采集应视为失败或不可用，不要把壳页/推荐页里的数字写进 ideas。
- 账号页卡片的主要用途是拿真实帖子链接、note_id、标题和粗略点赞；完整正文和真实互动数据必须回到详情页抓取。
- 采集结果不确定时，宁可少写，也不要编造或自动补全缺失字段。

## 步骤

### Step 1 — 初始化
  python3 tools/trace.py start <task_id> "collect" "<素材源摘要>"

### Step 2 — 采集
如果素材源是普通文本/主题关键词：
组装输入：agents/collector.md + 素材源。
  echo <input> | claude -p --allowedTools "Read,WebFetch,WebSearch" > /tmp/autowrite/<task_id>/ideas.json

如果素材源是小红书链接：
- 单篇笔记：
  python3 tools/scrape.py note "<url>"
- 收藏页（自动过滤+去重+入库）：
  python3 tools/scrape.py favorites --limit <N> --min-engagement 500
- 账号页（自动过滤+去重+入库）：
  python3 tools/scrape.py account "<url>" --limit <N> --min-engagement 500

### Step 3 — 校验输出
普通文本/主题关键词：检查 ideas.json 为合法 JSON 数组。格式错误则重试 1 次。

小红书浏览器采集：检查结果 JSON，确认无系统错误（exit code 3）。

### Step 4 — 写入与汇总
普通文本/关键词来源的灵感，逐条调用 inbox.py 入库：
  python3 tools/inbox.py --title "<title>" --content "<content>" --tags "<tags>"

小红书来源已在 Step 2 自动入库，无需重复写入。

展示汇总报告（入库 N 条 / 去重跳过 N 条 / 互动不足跳过 N 条 / 失败 N 条）。

  python3 tools/trace.py end <task_id> "success" "入库 N 条, 跳过 N 条"
