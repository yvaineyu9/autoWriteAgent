# /daily

每日规划：回顾昨日 → 交互提问 → 记录计划 → 新想法入库。

## 步骤

### Step 1 — 收集上下文
  python3 tools/daily.py read yesterday
  python3 tools/daily.py summary

### Step 2 — 交互提问
- Q1: 今天聚焦什么？
- Q2: 新想法？
- Q3: 有阻碍？

### Step 3 — 写入日记
  python3 tools/daily.py write --plan "<计划>"

### Step 4 — 新想法入库
  python3 tools/inbox.py --title "<title>" --content "<content>" --tags "daily"

### Step 5 — 展示摘要
