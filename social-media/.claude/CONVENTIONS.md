# Social Media Workflow Conventions

这份文档是 `social-media/` 生产线的统一约定。若其他文档与此冲突，以本文件为准。

## 1. 正式入口

当前正式、通用的工作流入口只有两个：

- `/content-creation`：内容生成主链
- `/publishing`：发布记录与数据追踪

以下内容目前**不是**正式、独立的 skill 入口：

- `revision`：属于内容生成后的修改动作，可由主会话或后续包装层调用
- `selection`：当前没有独立 skill，通常由人工判断或专用代理完成

`content-planner` 是月见专用策划代理，不是通用主入口。

## 2. Agent 角色

`/content-creation` 内部使用 CLI 子代理协作：

- writer：生成草稿
- reviewer：审核草稿

实际文件路径：

- `social-media/.claude/agents/writer/writer.md`
- `social-media/.claude/agents/reviewer/reviewer.md`

## 3. 人设与平台配置路径

人设文件：

- `social-media/.claude/personas/<persona>/persona.md`

平台文件：

- `social-media/.claude/personas/<persona>/platforms/<platform>.md`

## 4. 成品归档路径

社媒内容的唯一正式归档路径为：

`$VAULT_PATH/60_Published/social-media/<persona>/<platform>/YYYY-MM-DD_<title>/content.md`

说明：

- `content.md` 是正文主文件
- 文章目录名使用 `YYYY-MM-DD_<title>`
- 图片等发布物料与 `content.md` 放在同一目录
- 历史路径 `60_Published/<persona>/<platform>/...` 仅视为待迁移旧数据，不再作为正式约定
- 新脚本、新技能文档、新功能设计都必须按这一路径编写

## 5. reviewer 评分契约

reviewer 的正式输出契约为**纯 JSON**，总分 10 分：

```json
{
  "total": 8,
  "pass": true,
  "scores": {
    "内容质量": 2,
    "人设一致性": 2,
    "平台适配": 1,
    "情感共鸣": 1,
    "传播潜力": 2
  },
  "feedback": null,
  "highlights": "标题和结构完整"
}
```

规则：

- 5 个维度
- 每项 0-2 分
- 总分 10
- `>= 7` 视为通过

不再使用 60 分制。

## 6. 发布链定义

发布链不是自动发平台，而是“记录 + 跟踪”：

1. 成品内容已归档到 `60_Published/...`
2. `/publishing create` 或 `publish.py create` 创建发布任务
3. 人工到平台实际发布
4. `/publishing done` 或 `publish.py done` 回填发布链接
5. `metrics.py record` 录入数据

发布记录数据位于：

- `$VAULT_PATH/70_Distribution/distribution.db`

## 7. 路径变量

文档示例里优先使用：

- `PROJECT_ROOT`：Git 仓库根目录
- `VAULT_PATH`：外部数据仓库目录

不要在正式文档中硬编码 `~/claude-workflows` 这类机器相关路径。
