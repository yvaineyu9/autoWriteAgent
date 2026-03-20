---
name: content-creation
description: 社媒内容全流程创作（多平台自动改写），通过独立 CLI 子代理实现写作与审核分离
allowed-tools: Read, Bash, WebFetch, Write, Edit
argument-hint: "[主题/素材/URL] [--platform 小红书,公众号,twitter] [--account 人设名] [--mode 润色]"
---

## 任务
根据输入的主题、素材或URL，自动判断任务类型，以指定人设（默认虫小宇）生成多平台社媒内容，经独立审核达标后归档到仓库。

统一约定见 [../../CONVENTIONS.md](../../CONVENTIONS.md)。

## 参数解析

在处理用户输入之前，先检查是否包含以下参数：

### 平台选择 `--platform`
- 格式：`--platform 小红书`、`--platform 公众号`、`--platform twitter`、`--platform 小红书,公众号`
- 支持的平台名：`小红书` / `xiaohongshu`、`公众号` / `wechat`、`Twitter` / `twitter`、`播客` / `podcast_script`
- 多个平台用逗号分隔
- 如果未指定 `--platform`，默认生成三个图文平台（小红书 + 公众号 + Twitter），不含播客逐字稿
- 播客逐字稿必须通过 `--platform 播客` 显式指定
- 解析后将 `--platform xxx` 从输入文本中移除，剩余部分作为实际内容输入

### 人设选择 `--account`
- 格式：`--account chongxiaoyu`、`--account yuejian`
- 支持的人设名对应 `social-media/.claude/personas/` 下的子目录名
- 如果未指定 `--account`，默认使用 `chongxiaoyu`
- 解析后将 `--account xxx` 从输入文本中移除
- 当前可用人设：
  - `chongxiaoyu`：虫小宇（占星 × AI，个人成长方向）
  - `yuejian`：月见（关系占星 × 星宿学，恋爱关系方向）

### 批量处理
- 如果用户输入包含多个小宇宙链接（用空格或换行分隔），依次处理每个链接
- 如果用户输入包含多段用 `---` 分隔的内容，每段作为独立任务处理

## 任务判断规则

解析参数后，根据剩余内容自动判断走哪条路径：

| 输入特征 | 任务类型 | 处理流程 |
|---------|---------|---------|
| 包含 `xiaoyuzhoufm.com` 链接 | 播客转录 | 运行转录脚本 → 阅读转录文本 → 总结 → 按目标平台改写 → 归仓 |
| 一段短想法/灵感/观点 | 灵感扩写 | 扩写为完整文章 → 按目标平台改写 → 归仓 |
| 指向已有文件路径 | 文章改写 | 读取文件 → 按目标平台改写 → 归仓 |
| 明确说"润色" | 单纯润色 | 直接润色 → 归仓 |

## 素材读取

在开始生产前，根据输入判断素材来源：
- 如果用户给了仓库中的文件路径 → 从对应目录读取（`00_Inbox/`、`30_Research/`、`50_Resources/`）
- 如果用户给了外部 URL 或文本 → 直接使用
- 如果用户给了小宇宙链接 → 调用转录脚本：
  ```bash
  python3 scripts/podcast_transcribe.py "<链接>" -m medium
  ```
- 主动搜索 `40_Wiki/` 中与主题相关的知识词条作为参考
- 如果 `20_Project/` 中有相关项目 → 读取项目上下文了解整体方向

## 核心架构：CLI 子代理编排

本 skill 采用**主会话编排 + CLI 子代理执行**的架构。主会话（你）负责流程控制和归仓，内容生成和审核由独立的 `claude -p` 子进程完成。

### 为什么用 CLI 子代理
- **上下文隔离**：reviewer 完全看不到生成过程，审核更客观
- **模型分配**：所有子代理使用 `claude -p` 默认模型
- **多平台并行**：多个 writer 可以后台同时运行
- **稳定可靠**：不依赖 Task API，直接走 CLI

### 路径约定
- 项目根目录：由主会话通过 `pwd` 或已知路径确定
- 临时文件目录：`/tmp/content_creation/`
- Writer agent 定义：`social-media/.claude/agents/writer/writer.md`
- Reviewer agent 定义：`social-media/.claude/agents/reviewer/reviewer.md`
- 人设文件：`social-media/.claude/personas/<account>/persona.md`
- 平台风格文件：`social-media/.claude/personas/<account>/platforms/<platform>.md`

## 流程

### Step 0：准备工作
1. 创建临时目录：`mkdir -p /tmp/content_creation`
2. 解析 `--account` 参数，确定人设名（默认 `chongxiaoyu`）
3. 读取人设文件 `social-media/.claude/personas/<account>/persona.md`
4. 确定目标平台列表

### Step 1：确定目标平台
- 如果用户通过 `--platform` 指定了平台，按指定的来
- 如果没有指定，默认生成小红书 + 公众号 + Twitter 三个版本

### Step 2：准备 writer prompt 输入
对每个目标平台，读取对应的风格指令文件，将以下内容拼装写入 `/tmp/content_creation/writer_input_<platform>.md`：
```
## 人设档案
<persona.md 的内容>

## 平台风格指令
<对应平台 prompt 的内容>

## 素材
<用户提供的素材/主题>

## 任务
请以人设档案中定义的人格，按照上述平台风格指令，为<平台名>生成一篇完整的内容文案。
直接输出成品，不要加任何说明性文字。用 markdown 格式。
```

### Step 3：调用 Writer 子代理（可并行）
对每个平台，通过 CLI 调用独立的 writer 子进程：

```bash
cat /tmp/content_creation/writer_input_<platform>.md | \
claude -p \
  \
  --allowedTools "Read,WebFetch" \
  --add-dir "$(pwd)" \
  2>/dev/null > /tmp/content_creation/draft_<platform>.md
```

**多平台并行优化**：如果有多个平台，可以用 `&` 让多个 writer 同时运行：
```bash
cat /tmp/content_creation/writer_input_xiaohongshu.md | claude -p --allowedTools "Read,WebFetch" --add-dir "$(pwd)" 2>/dev/null > /tmp/content_creation/draft_xiaohongshu.md &
cat /tmp/content_creation/writer_input_wechat.md | claude -p --allowedTools "Read,WebFetch" --add-dir "$(pwd)" 2>/dev/null > /tmp/content_creation/draft_wechat.md &
cat /tmp/content_creation/writer_input_twitter.md | claude -p --allowedTools "Read,WebFetch" --add-dir "$(pwd)" 2>/dev/null > /tmp/content_creation/draft_twitter.md &
wait
```

### Step 3.5：协作模式（当用户提供零散素材时）
如果用户给的不是完整文章，而是零散的语音转录、笔记碎片或口述内容：
1. 主会话先整理核心观点，展示给用户确认
2. 将确认后的观点作为素材传给 writer 子代理
3. 后续流程不变

### Step 4：调用 Reviewer 子代理
对每篇生成的草稿，调用独立的 reviewer 子进程进行审核：

```bash
cat /tmp/content_creation/draft_<platform>.md | \
claude -p \
  \
  --tools "" \
  --append-system-prompt "你是一个严格独立的内容审核员。输出纯 JSON，不要代码块，不要额外说明。评分维度共 5 项：内容质量、人设一致性、平台适配、情感共鸣、传播潜力。每项 0-2 分，总分 10 分，>=7 分通过。严格使用以下字段名：{\"total\":数字,\"pass\":true/false,\"scores\":{\"内容质量\":数字,\"人设一致性\":数字,\"平台适配\":数字,\"情感共鸣\":数字,\"传播潜力\":数字},\"feedback\":\"修改建议或null\",\"highlights\":\"亮点\"}。" \
  "请审核以上<平台名>平台的社媒内容" \
  2>/dev/null > /tmp/content_creation/review_<platform>.json
```

**注意**：
- reviewer 使用 `--tools ""` 禁用所有工具，只做纯文本审核，确保完全独立
- 如果输出被 ` ```json ``` ` 代码块包裹，解析时先 strip 掉代码块标记再提取 JSON

### Step 5：循环改进
主会话读取 reviewer 的 JSON 输出，判断是否通过：

```
读取 review_<platform>.json
  → total ≥ 7 → 通过 → 进入归仓
  → total < 7 → 将 feedback 追加到 writer_input，重新调用 writer
  → 最多循环 3 轮
  → 3 轮后仍未通过 → 输出最后一版 + 审核结果，由用户决定
```

重新调用 writer 时，在输入文件末尾追加：
```
## 修改要求（第N轮）
上一轮审核未通过（XX/10分），请按以下意见修改：
<reviewer 的 feedback>

严格按修改意见调整，直接输出修改后的完整文案。
```

### Step 6：产出归仓

审核通过后，执行以下归仓操作：

1. **成品归档**：每个平台的终稿归档到 `$VAULT_PATH/60_Published/social-media/<account>/<platform>/YYYY-MM-DD_<title>/content.md`
   - 历史路径 `60_Published/<account>/<platform>/...` 仅作为旧数据存在，不再作为正式输出目标
   - **文件夹名必须和文章标题一致**（`YYYY-MM-DD_文章实际标题`），标题变更时文件夹名同步修改
   - 文件头部包含元信息：平台、审核分数、生成日期
   - 文件内容：正文文案、简介、hashtag
2. **项目状态回写**：如果 `20_Project/` 中存在对应项目文件
   - 在该项目 Progress 段追加：`- [YYYY-MM-DD] 完成社媒文案：<标题>（<平台列表>）`
   - 如果不存在对应项目，跳过此步
3. **每日记录**：在 `10_Daily/YYYY-MM-DD.md` 追加产出记录
   - 格式：`- 完成社媒文案：<标题>，平台：<平台列表>，审核分数 XX/10`
   - 如果当日文件不存在，基于 `99_System/templates/daily.md` 创建
4. **清理临时文件**：`rm -rf /tmp/content_creation/`

### Step 7：输出展示

在终端中，按以下格式展示每个平台的生成内容：

```
--- 小红书 ---
[生成的小红书内容]

--- 公众号 ---
[生成的公众号内容]

--- Twitter ---
[生成的Twitter内容]
```

如果用户只指定了部分平台，只展示对应平台的内容。

向用户报告：
- 终稿内容预览
- 各平台审核分数 + 亮点
- 归档路径
- 循环轮次（如有）

## 注意事项

- 所有内容用中文输出（Twitter 可以中英混合）
- 不要自己编造事实，忠实于原始输入内容
- 扩写时可以补充合理的论据和案例，但核心观点必须来自用户输入
- **扩写和改写时，必须以当前 `--account` 指定人设的语言风格输出**，不能写成通用的AI生成内容
- CLI 子代理调用失败时（如 claude 命令不可用），回退到主会话内直接生成
- 如果 `--output-format json` 的输出不是合法 JSON，尝试从文本中提取分数信息
