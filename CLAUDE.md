# autoWriteAgent

AI 内容生产系统。

## 命令
| 命令 | 说明 | 定义 |
|------|------|------|
| /create | 内容创作（写 + 审循环） | .claude/skills/create/SKILL.md |
| /collect | 灵感采集 | .claude/skills/collect/SKILL.md |
| /select | 选文推荐 | .claude/skills/select/SKILL.md |
| /publish | 发布管理 | .claude/skills/publish/SKILL.md |
| /daily | 每日规划 | .claude/skills/daily/SKILL.md |

## 项目结构
- agents/         — Agent 定义（writer, reviewer, collector, selector）
- personas/       — 人设配置（每个子目录 = 一个账号）
- .claude/skills/ — 命令编排定义（Claude Code 斜杠命令）
- tools/          — 工具脚本（数据 I/O 的唯一入口）
- data/           — 数据库 + 内容文件（不进 Git）

## 规则
- 所有数据读写必须通过 tools/ 完成，不直接操作 data/
- 每次 tool 调用后检查 exit code（0=成功, 1=参数错误, 2=部分成功, 3=系统错误）
- 不将 .env、密钥、token 写入任何文件
