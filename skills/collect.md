# /collect [素材源]

采集灵感：解析素材 → 提炼灵感 → 人工筛选 → 入库。

## 参数
- 素材源: URL / 文本 / 主题关键词（可选，不提供则交互式输入）

## 步骤

### Step 1 — 初始化
  python3 tools/trace.py start <task_id> "collect" "<素材源摘要>"

### Step 2 — 调用 Collector
组装输入：agents/collector.md + 素材源。
  echo <input> | claude -p --allowedTools "Read,WebFetch,WebSearch" > /tmp/autowrite/<task_id>/ideas.json

### Step 3 — 校验输出
检查 ideas.json 为合法 JSON 数组。格式错误则重试 1 次。

### Step 4 — 展示给用户
列出采集到的灵感，让用户确认哪些入库。

### Step 5 — 写入
对每条确认的灵感：
  python3 tools/inbox.py --title "<title>" --content "<content>" --tags "<tags>"

  python3 tools/trace.py end <task_id> "success" "入库 N 条"
