# Claude Workflows 项目规则

## 自动保存与推送
每当你完成了对本项目文件的修改（包括新增、编辑、删除），在任务结束前必须：
1. `git add .`
2. 根据修改自动生成简洁的中文提交说明
3. `git commit` 并 `git push`

不需要用户提醒，自己判断时机，改完就提交。

## 目录结构约定
- 每个业务领域是一个顶层文件夹（social-media, podcast, etc.）
- 工作流用 `.claude/skills/<name>/SKILL.md` 定义
- 执行者用 `.claude/agents/<name>.md` 定义
- 审核标准用 `standards.md` 放在对应 skill 目录下

## 安全规则
- 绝对不要将 .env、密钥、token 写入任何文件
- 敏感信息只通过环境变量引用
