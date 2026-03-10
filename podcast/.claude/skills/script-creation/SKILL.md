---
name: script-creation
description: 乐乎玄学馆播客稿件全流程创作，通过独立 CLI 子代理实现写作与审核分离
allowed-tools: Read, Bash, WebFetch, Write, Edit
argument-hint: "[URL/文本/文件路径]"
---

## 任务
将输入内容扩展为5000-8000字的「乐乎玄学馆」深度播客对话稿，经独立审核达标后归档到仓库。

## 参数解析

在处理用户输入之前，先检查是否包含以下参数：

### 目标时长 `--duration`
- 格式：`--duration 30`、`--duration 45`、`--duration 60`
- 支持值：30、45、60（分钟）
- 如果未指定，默认 30 分钟（5000-6000字）
- 字数参考：30分钟=5000-6000字，45分钟=7000-8500字，60分钟=9000-11000字
- 解析后将 `--duration xx` 从输入文本中移除

## 任务判断规则

解析参数后，根据剩余内容自动判断走哪条路径：

| 输入特征 | 任务类型 | 处理流程 |
|---------|---------|---------|
| 包含 `xiaoyuzhoufm.com` 链接 | 播客转录 | 运行转录脚本 → 阅读转录文本 → 生成播客稿 → 归仓 |
| 指向已有文件路径 | 素材改写 | 读取文件 → 生成播客稿 → 归仓 |
| 一段文本/主题/灵感 | 原创创作 | 直接生成播客稿 → 归仓 |

## 素材读取

在开始生产前，根据输入判断素材来源：
- 如果用户给了仓库中的文件路径 → 从对应目录读取（`00_Inbox/`、`30_Research/`、`50_Resources/`）
- 如果用户给了外部 URL 或文本 → 直接使用
- 如果用户给了小宇宙链接 → 调用转录脚本：
  ```bash
  python3 scripts/podcast_transcribe.py "<链接>" -m medium
  ```
  - 转录结果判断是否有沉淀价值
  - **有价值**（完整访谈、重要内容）→ 存入 `30_Research/转录_<主题>.md`
  - **临时性**（仅用于本次生产）→ 仅在临时文件中传递
- 主动搜索 `40_Wiki/` 中与主题相关的占星/心理学知识词条作为参考
- 如果 `20_Project/` 中有相关项目 → 读取项目上下文了解整体方向

## 核心架构：CLI 子代理编排

本 skill 采用**主会话编排 + CLI 子代理执行**的架构。主会话（你）负责流程控制和归仓，内容生成和审核由独立的 `claude -p` 子进程完成。

### 为什么用 CLI 子代理
- **上下文隔离**：reviewer 完全看不到生成过程，审核更客观
- **模型分配**：所有子代理使用 `claude -p` 默认模型
- **稳定可靠**：不依赖 Task API，直接走 CLI

### 路径约定
- 项目根目录：由主会话通过 `pwd` 或已知路径确定
- 临时文件目录：`/tmp/script_creation/`
- Writer system prompt：`podcast/.claude/agents/writer.md`（去掉 frontmatter 后使用）
- Reviewer system prompt：`podcast/.claude/agents/reviewer.md`（去掉 frontmatter 后使用）
- 人设文件：`social-media/.claude/prompts/persona.md`
- 播客风格文件：`social-media/.claude/prompts/podcast_script.md`

## 流程

### Step 0：准备工作
1. 创建临时目录：`mkdir -p /tmp/script_creation`
2. 读取人设文件 `social-media/.claude/prompts/persona.md`
3. 读取播客风格文件 `social-media/.claude/prompts/podcast_script.md`
4. 确定目标时长和对应字数范围

### Step 1：准备素材
- 如果是小宇宙链接 → 运行转录脚本获取文本
- 如果是文件路径 → 读取文件内容
- 如果是文本 → 直接使用
- 搜索 `40_Wiki/` 中相关知识词条

### Step 2：准备 writer prompt 输入
将以下内容拼装写入 `/tmp/script_creation/writer_input.md`：
```
## 人设档案
<persona.md 的内容>

## 播客风格指令
<podcast_script.md 的内容>

## 素材
<用户提供的素材/转录文本/主题>

## 任务
请按照上述人设和播客风格指令，生成一篇完整的「乐乎玄学馆」播客对话稿。
目标时长：<XX>分钟，字数范围：<XXXX-XXXX>字。
直接输出成品对话稿，不要加任何说明性文字。用 markdown 格式。
```

### Step 3：调用 Writer 子代理
通过 CLI 调用独立的 writer 子进程：

```bash
cat /tmp/script_creation/writer_input.md | \
claude -p \
  \
  --allowedTools "Read,WebFetch" \
  --add-dir "$(pwd)" \
  2>/dev/null > /tmp/script_creation/draft.md
```

### Step 4：调用 Reviewer 子代理
对生成的草稿，调用独立的 reviewer 子进程进行审核：

```bash
cat /tmp/script_creation/draft.md | \
claude -p \
  \
  --tools "" \
  --append-system-prompt "你是一个严格独立的播客稿件审核员。按照以下标准逐项打分，输出纯 JSON（不要代码块标记），直接以{开头}结尾。评分维度（每项1-10分，总分60分，≥48分通过）：1.信息密度 2.情绪节奏 3.对话自然度 4.Hook吸引力 5.行动价值 6.字数合规。严格使用以下字段名：{\"total\":数字,\"pass\":true/false,\"scores\":{\"信息密度\":数字,\"情绪节奏\":数字,\"对话自然度\":数字,\"Hook吸引力\":数字,\"行动价值\":数字,\"字数合规\":数字},\"feedback\":\"修改建议或null\",\"highlights\":\"亮点\"}。不要增加任何额外字段。" \
  "请审核以上播客对话稿" \
  2>/dev/null > /tmp/script_creation/review.json
```

**注意**：
- reviewer 使用 `--tools ""` 禁用所有工具，只做纯文本审核，确保完全独立
- 如果输出被 ` ```json ``` ` 代码块包裹，解析时先 strip 掉代码块标记再提取 JSON

### Step 5：循环改进
主会话读取 reviewer 的 JSON 输出，判断是否通过：

```
读取 review.json
  → total ≥ 48 → 通过 → 进入归仓
  → total < 48 → 将 feedback 追加到 writer_input，重新调用 writer
  → 最多循环 3 轮
  → 3 轮后仍未通过 → 输出最后一版 + 审核结果，由用户决定
```

重新调用 writer 时，在输入文件末尾追加：
```
## 修改要求（第N轮）
上一轮审核未通过（XX/60分），请按以下意见修改：
<reviewer 的 feedback>

严格按修改意见调整，直接输出修改后的完整对话稿。
```

### Step 6：产出归仓

审核通过后，执行以下归仓操作：

1. **成品归档**：将终稿写入 `60_Published/podcast/EP<编号>_<标题>.md`
   - 编号自动递增（检查 `60_Published/podcast/` 下最大编号）
   - 文件头部包含元信息：审核分数、生成日期、目标时长
   - 文件内容：完整播客对话稿
2. **项目状态回写**：如果 `20_Project/` 中存在对应项目文件
   - 在该项目 Progress 段追加：`- [YYYY-MM-DD] 完成播客稿件：EP<编号> <标题>`
   - 如果不存在对应项目，跳过此步
3. **每日记录**：在 `10_Daily/YYYY-MM-DD.md` 追加产出记录
   - 格式：`- 完成播客稿件：[[EP<编号>_<标题>]]，审核分数 XX/60`
   - 如果当日文件不存在，基于 `99_System/templates/daily.md` 创建
4. **清理临时文件**：`rm -rf /tmp/script_creation/`

### Step 7：输出展示

在终端中展示：
```
--- 乐乎玄学馆 EP[XX]: [标题] ---
[生成的对话稿预览（前500字）]
...

审核分数：XX/60
亮点：<highlights>
归档路径：60_Published/podcast/EP<编号>_<标题>.md
```

向用户报告：
- 终稿预览
- 审核分数 + 亮点
- 归档路径
- 循环轮次（如有）

## 注意事项

- 所有内容用中文输出
- 不要自己编造事实，忠实于原始输入内容
- 扩写时可以补充合理的占星/心理学论据，但核心观点必须来自用户输入
- **必须以小狗仔和小刀的人格对话形式输出**，不能写成单人稿
- CLI 子代理调用失败时（如 claude 命令不可用），回退到主会话内直接生成
- 如果 reviewer 输出不是合法 JSON，尝试从文本中提取分数信息
