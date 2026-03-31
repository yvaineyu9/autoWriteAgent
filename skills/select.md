# /select <目标描述>

从定稿池中推荐内容发布。

## 参数
- 目标描述: 发布需求描述（如"本周小红书需要发 2 篇占星内容"）

## 步骤

### Step 1 — 收集候选
  python3 tools/publish.py list --status final --format json
为空则告知用户无可发布内容。

### Step 2 — 调用 Selector
组装输入：agents/selector.md + 候选列表 + 目标描述。
  echo <input> | claude -p --tools "" > /tmp/autowrite/selection.json

### Step 3 — 展示推荐
展示推荐列表，用户逐条确认。

### Step 4 — 确认
对每条确认的内容：
  python3 tools/publish.py create --content-id <id> --persona <persona> --title "<title>"
