# 小红书公开灵感导入工具

## 概述

这个工具用于把外部采集器导出的公开小红书数据，导入到 `claude-workflows` 的灵感池。

它只负责：

- 读取公开采集结果
- 规范化成项目可用的 Markdown 灵感文件
- 写入 `$VAULT_PATH/00_Inbox/小红书/采集/`

它不负责：

- 登录小红书
- 抓取网页
- 自动互动
- 自动发布

也就是说，这个工具是**采集结果导入层**，不是爬虫本身。

## 适用输入

支持以下输入：

- 单个 `.json`
- 单个 `.jsonl`
- 一个目录（递归读取其中的 `.json` / `.jsonl`）

适合对接：

- `MediaCrawler` 这类公开内容采集器
- 浏览器插件或自定义脚本导出的笔记 JSON
- 自己后续做的公开笔记监控结果

## 输出位置

默认写入：

`$VAULT_PATH/00_Inbox/小红书/采集/`

生成的每条灵感都会包含：

- frontmatter 元数据
- 原博正文
- 公开互动数据
- 评论摘录
- 可提炼灵感提示

这样后续可以直接作为 `/content-creation` 或本地改写链路的输入素材。

## 快速使用

```bash
python3 social-media/tools/xhs-inspiration-import/import.py \
  --input /path/to/crawler/output \
  --persona yuejian \
  --source-name agent:mediacrawler
```

如果只想预览将会创建哪些文件：

```bash
python3 social-media/tools/xhs-inspiration-import/import.py \
  --input /path/to/crawler/output \
  --dry-run
```

## 参数

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--input` | 是 | - | 输入 JSON / JSONL 文件或目录 |
| `--persona` | 否 | `yuejian` | 默认关联人设 |
| `--target-dir` | 否 | `$VAULT_PATH/00_Inbox/小红书/采集` | 导入目标目录 |
| `--source-name` | 否 | `agent:xhs-public-import` | 写入 frontmatter 的 source |
| `--limit` | 否 | 不限制 | 只导入前 N 条 |
| `--dry-run` | 否 | 关闭 | 只预览，不落盘 |

## 去重规则

工具会优先用以下字段去重：

- `xhs_note_id`
- `source_url`

如果目标目录里已经存在同一个笔记 ID 或同一个原文链接，就不会重复导入。

## 与项目规则的关系

- 工具代码放在 Git 仓库：`social-media/tools/`
- 采集产物写入外部数据仓库：`$VAULT_PATH/00_Inbox/...`
- 不直接把采集内容写进 Git 仓库

这符合根目录 [CLAUDE.md](../../../CLAUDE.md) 的“工厂与仓库分离”规则。
