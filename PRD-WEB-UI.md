# PRD: autoWriteAgent Web UI — 小白零门槛全流程操作

> **产品经理**：产品组
> **开发者**：Claude Code (autoWriteAgent-web-ui task)
> **日期**：2026-04-08
> **优先级**：P0（阻塞上线）
> **目标**：一个从未接触过本系统的用户，打开 Web UI 后能独立完成「灵感采集 → 内容创作 → 排版 → 选文 → 发布 → 数据跟踪」全流程，无需命令行、无需读代码。

---

## 一、现状分析

### 已有页面
| 页面 | 路由 | 状态 |
|------|------|------|
| 灵感池 | /ideas | 基本可用：CRUD、AI采集、AI展开 |
| 成品仓库 | /contents | 基本可用：创建、编辑、修订、排版 |
| 发布数据 | /publications | 基本可用：状态管理、手动录入指标 |
| 任务监控 | /tasks | 基本可用：轮询任务状态 |

### 关键缺陷（阻塞小白使用）
1. **无引导**：打开首页直接进灵感池列表，新用户不知道该干什么
2. **人设硬编码**：后端 `db_service.py:42` 写死 `persona_id = 'yuejian'`，无法切换
3. **无选文功能**：Selector Agent 只有 CLI，UI 完全缺失
4. **无 Dashboard**：没有全局数据概览，不知道当前产出和发布状态
5. **流程断裂**：灵感→创作→排版→发布之间需要用户自己在页面间跳转，无引导链路

---

## 二、需求清单（按优先级）

### P0：阻塞全流程，必须做

#### 需求 1：Dashboard 首页
**路由**：`/` （替代当前的 redirect 到 /ideas）

**功能**：
- 顶部统计卡片：
  - 待处理灵感数（status=pending）
  - 待发布成品数（status=final）
  - 已发布总数（status=published）
  - 本周新增发布数
- 快捷操作区（大按钮，一看就懂）：
  - 「采集灵感」→ 弹出采集对话框（复用现有 collect 逻辑）
  - 「创作文章」→ 跳转 /contents 并自动打开创建面板
  - 「选文发布」→ 跳转 /select
- 最近动态列表（最近 10 条 status_log 记录，展示"XX文章 从draft变为final"之类）

**后端**：
- 新增 `GET /api/dashboard` 接口，返回统计数据 + 最近动态
- 查询示例：
```sql
SELECT status, COUNT(*) as count FROM ideas GROUP BY status;
SELECT status, COUNT(*) as count FROM contents GROUP BY status;
SELECT COUNT(*) FROM publications WHERE published_at >= date('now', '-7 days', 'localtime');
SELECT sl.content_id, c.title, sl.from_status, sl.to_status, sl.created_at
  FROM status_log sl LEFT JOIN contents c ON sl.content_id = c.content_id
  ORDER BY sl.created_at DESC LIMIT 10;
```

---

#### 需求 2：人设切换
**位置**：侧边栏顶部，logo 下方

**功能**：
- 下拉选择器，列出 `personas/` 目录下所有子目录
- 选择后全局生效，所有列表查询和创建操作使用选中的 persona_id
- 默认选中第一个（按字母排序）
- 选择状态用前端 localStorage 持久化

**后端**：
- 新增 `GET /api/personas` 接口
  - 扫描 `personas/` 目录，返回 `[{id: "yuejian", name: "月见", platforms: ["xiaohongshu"]}]`
  - name 从 `personas/<id>/index.md` 的第一行 `# xxx` 提取
  - platforms 从 `personas/<id>/platforms/` 下的 `.md` 文件名提取
- **修改所有现有查询**：将 `WHERE persona_id = 'yuejian'` 改为接受 `persona_id` 参数
  - `GET /api/contents?persona_id=xxx`
  - `GET /api/publications?persona_id=xxx`
  - `agent_runner.py` 中的 `run_create_pipeline` 和 `run_revise_pipeline` 改为接受 persona_id 参数，不再硬编码 "yuejian"

---

#### 需求 3：选文工作流页面
**路由**：`/select`

**交互流程**：
1. 进入页面，显示所有 `status=final` 的成品列表（卡片式，显示标题、评分、创建日期）
2. 用户手动勾选要发布的文章（checkbox），或点击「AI 推荐」让 Selector Agent 推荐
3. 「AI 推荐」逻辑：
   - 调用 Selector Agent，输入所有 final 文章的标题+摘要
   - 返回推荐的 content_id 列表和推荐理由
   - 前端自动勾选推荐的文章，显示推荐理由
4. 点击「确认发布」：
   - 对每个勾选的文章，创建 publication 记录（调用现有 `tools/publish.py`）
   - 文章 status 从 final → publishing
   - 跳转到 /publications 页面

**后端**：
- 新增 `POST /api/select/recommend` 接口
  - 调用 Selector Agent（类似 agent_runner 中现有模式）
  - 输入：当前所有 final 状态文章
  - 输出：推荐 content_id 列表 + 理由
- 新增 `POST /api/select/publish` 接口
  - 接收 `{content_ids: ["xxx", "yyy"]}`
  - 批量创建 publication 记录
  - 批量更新 contents 状态为 publishing

---

#### 需求 4：侧边栏导航更新
**修改文件**：`ui/frontend/src/App.vue` 和 `router/index.ts`

当前导航：灵感池 → 成品仓库 → 发布数据 → 任务监控

改为：
```
仪表盘    /           （新增）
灵感池    /ideas
成品仓库  /contents
选文发布  /select     （新增）
发布数据  /publications
任务监控  /tasks
```

图标用文字即可，不需要 icon library。

---

### P1：提升体验，强烈建议做

#### 需求 5：成品创作增加平台选择联动
**位置**：/contents 创建文章对话框

**当前问题**：创建文章时 platform 是固定选项，没有和人设关联

**改为**：
- platform 下拉选项从当前选中人设的 platforms 列表动态获取
- 如果当前人设只有一个平台，自动选中，不显示下拉

---

#### 需求 6：流程引导条
**位置**：每个页面顶部

**功能**：
- 展示当前步骤在全流程中的位置：`采集灵感 → 创作文章 → 排版生图 → 选文 → 发布 → 数据跟踪`
- 当前页面对应的步骤高亮
- 每步可点击跳转到对应页面
- 样式：简洁的横向步骤条，不要太占空间（高度 40px 左右）

---

#### 需求 7：灵感池 → 创作的一键衔接
**位置**：/ideas 页面，每个灵感卡片/行

**功能**：
- 灵感列表每行增加「用这个灵感写文章」按钮
- 点击后：跳转到 /contents，自动打开创建对话框，idea_id 和 title 已预填

**实现**：
- 路由跳转带 query：`/contents?create_from_idea=xxx`
- ContentsView 在 mounted 时检查 query 参数，自动弹出创建对话框

---

#### 需求 8：发布数据页面增加「去发布」引导
**位置**：/publications 页面

**当前问题**：publication 记录是由选文流程创建的，但用户在发布页面看到 status=draft 的记录后不知道下一步该干什么

**改为**：
- status=draft 的记录显示醒目的「去发布」按钮
- 点击后弹出对话框：
  - 显示文章标题和内容预览
  - 提示"请将内容发布到平台后，粘贴发布链接"
  - 输入框：发布链接（post_url）
  - 确认后：status 变为 published，保存 post_url

---

### P2：锦上添花

#### 需求 9：排版快捷入口
**位置**：/contents 成品列表，每行操作按钮

**功能**：
- 增加「排版」图标按钮，点击直接展开该文章的排版面板（复用现有 typeset 逻辑）
- 不需要先点"编辑"再找排版功能

---

#### 需求 10：任务监控改进
**位置**：/tasks

**功能**：
- 任务完成后显示结果摘要（创建了什么文章、采集了几个灵感等）
- 任务失败后显示友好的错误信息（不是原始 traceback）
- 增加「重试」按钮（对 failed 任务）

---

## 三、技术约束

1. **前端技术栈**：Vue 3 + TypeScript + Vite（沿用现有）
2. **后端技术栈**：FastAPI + SQLite（沿用现有）
3. **不引入新的 npm 依赖**：尽量用原生 CSS 和 Vue 内置功能
4. **所有数据操作通过 tools/**：遵循项目 CLAUDE.md 的规则
5. **后端运行在 Mac Mini**：通过 SSH tunnel 访问，前端在本地开发
6. **API 前缀**：所有接口保持 `/api/` 前缀
7. **不做用户认证**：单用户本地工具，不需要登录

---

## 四、验收标准（小白测试脚本）

一个从未用过本系统的人，按以下步骤操作，每步都应该能在 UI 上找到明确的入口和指引：

### Step 1：打开首页
- [ ] 看到仪表盘，了解当前有多少灵感、成品、发布
- [ ] 看到快捷操作按钮

### Step 2：采集灵感
- [ ] 点击「采集灵感」
- [ ] 粘贴一段文字或 URL
- [ ] 点击「AI 采集」
- [ ] 等待任务完成，看到新灵感出现在灵感池

### Step 3：创作文章
- [ ] 在灵感池找到刚才的灵感
- [ ] 点击「用这个灵感写文章」
- [ ] 自动跳转到成品仓库，创建对话框已弹出
- [ ] 选择平台（或自动选中唯一平台）
- [ ] 点击「AI 创作」
- [ ] 等待任务完成，看到新文章出现

### Step 4：排版
- [ ] 在成品仓库找到新文章
- [ ] 点击「排版」
- [ ] 选择模板，生成图片
- [ ] 下载图片

### Step 5：选文发布
- [ ] 进入「选文发布」页面
- [ ] 看到可发布的文章列表
- [ ] 勾选文章（或点 AI 推荐）
- [ ] 点击「确认发布」
- [ ] 文章进入发布队列

### Step 6：记录发布链接
- [ ] 在「发布数据」页面看到待发布记录
- [ ] 点击「去发布」
- [ ] 将内容发到平台后，粘贴链接
- [ ] 确认，状态变为已发布

### Step 7：录入数据
- [ ] 找到已发布的文章
- [ ] 点击录入/更新数据（阅读、点赞、收藏、评论、转发）
- [ ] 回到仪表盘，看到统计更新

---

## 五、实施顺序建议

```
Phase 1（先跑通骨架）：
  需求 2 人设切换 → 需求 4 导航更新 → 需求 1 Dashboard → 需求 3 选文

Phase 2（串联流程）：
  需求 7 灵感→创作衔接 → 需求 5 平台联动 → 需求 8 发布引导 → 需求 6 流程条

Phase 3（打磨）：
  需求 9 排版快捷入口 → 需求 10 任务监控改进
```

每个 Phase 完成后 `git commit && git push`，方便增量验收。

---

## 六、不做的事情（明确排除）

- 不做用户注册/登录
- 不做多用户协作
- 不做自动发布到平台（仍然是人工发到小红书后回填链接）
- 不做人设创建/编辑 UI（人设通过 markdown 文件管理就够了）
- 不做知识库管理 UI
- 不做每日规划 UI
- 不做数据可视化图表（纯数字就够）
