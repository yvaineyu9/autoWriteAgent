# /select <目标描述>

选文 + 生图 + 发布，一站式完成。

## 参数
- 目标描述: 发布需求描述（如"今天小红书发 2 篇星宿关系内容"）

## 步骤

### Step 1 — 收集已发布历史
  python3 tools/publish.py list --status published --format json
分析已发布内容的主题分布、人设占比、发布时间，用于避免主题重复和保持多样性。

### Step 2 — 收集候选
  python3 tools/publish.py list --status final --format json
为空则告知用户无可发布内容。

### Step 3 — 选文推荐
综合已发布历史和候选列表，结合目标描述进行推荐。选文原则：
- 避免与近期已发布内容主题重复
- 优先匹配账号高互动标签方向
- 同批推荐之间保持角度差异（如一痛一愈、一深一轻）
展示推荐列表（标题 + content_id + 推荐理由），等待用户确认。

### Step 4 — 生成图片
用户确认后，为每篇选中内容生成小红书卡片图片：
  node tools/xhs-cli/xhs-gen.js -i data/content/<content_id>/content.md -o data/content/<content_id>/
- v1 模板（xhs-gen.js）：纸质纹理背景、棕色标题
- v2 模板（xhs-gen-v2.js）：深色渐变封面、金色装饰
默认使用 v1，用户可指定版本。

### Step 5 — 交付发布
将每篇内容的文章简介（content.md 中 `---简介---` 之后的文本）和生成的图片路径汇总，交付给用户或下游发布渠道。

交付完成后，自动标记为已发布：
  python3 tools/publish.py create --content-id <id> --persona <persona> --title "<title>"
  python3 tools/publish.py done --id <pub_id> --url "pending"
内容状态从 final → publishing → published。
post_url 暂填 "pending"，后续通过 /publish sync-account 回填真实链接。
