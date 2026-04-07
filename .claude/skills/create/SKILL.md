# /create <persona> <platform> [素材]

创建内容：检索知识 → 写作 → 校验评审 → 人工确认 → 归档。

## 参数
- persona: 人设 ID（personas/ 下的子目录名）
- platform: 平台 ID（platforms/ 下的文件名，不含 .md）
- 素材: 可选。URL / 文本 / 文件路径

## 步骤

### Step 1 — 初始化任务
  python3 tools/trace.py start <task_id> "create" "<persona> <platform>"

### Step 2 — 路由校验
读取 personas/<persona>/index.md。确认人设和平台存在。
失败则：python3 tools/trace.py fail <task_id> "人设或平台不存在"

### Step 3 — 加载平台上下文
读取 personas/<persona>/platforms/<platform>.md。

### Step 4 — 准备素材
4a. 从灵感库选题：
  从 ideas 表中检索与主题相关的灵感（按 tags 匹配），读取对应 file_path 的内容：
  ```sql
  SELECT id, title, tags, file_path FROM ideas
  WHERE status='pending' AND tags LIKE '%<关键词>%'
  ORDER BY created_at DESC
  ```
  读取匹配灵感的文件内容，从中提炼可用的选题角度、观点、素材。
  选定灵感后记录 idea_id，归档时传入 --source-idea。

4b. 处理用户输入：
  - 纯文本：直接使用
  - URL：用 WebFetch 获取
  - 文件路径：用 Read 读取
  - 音频 URL：python3 tools/transcribe/podcast_transcribe.py <url>

4c. 检索相关知识：
  python3 tools/knowledge.py search "<关键词>"
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
  python3 tools/validate_review.py /tmp/autowrite/<task_id>/review_raw.json

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
  python3 tools/archive.py --persona <persona> --platform <platform> --title "<标题>" --file /tmp/autowrite/<task_id>/draft.md [--review-json /tmp/.../review.json] [--source-idea <idea_id>]

检查 exit code（0/1/2/3），按 Tool 契约处理。

  python3 tools/trace.py end <task_id> "success" "content_id=<id>"
