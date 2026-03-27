# Agent Workflow

纯 agent 版写稿/改稿/审核脚本，支持 provider 切换。

## 目标

- 不依赖 Web UI
- 不依赖 Claude slash skill
- 同一套脚本同时支持 `claude` 和 `codex`

## Provider 选择

默认读取：

```bash
export AI_PROVIDER=claude
```

也可以单次覆盖：

```bash
./run_content_task.sh --provider codex ...
```

当前支持：

- `claude`
- `codex`

## 写稿

```bash
./run_content_task.sh \
  --provider claude \
  --persona yuejian \
  --platform xiaohongshu \
  --input-path "$VAULT_PATH/00_Inbox/小红书/2026-03-20_别把安坏当纯爱.md" \
  --output-file /tmp/out.md
```

## 改稿

```bash
./run_revision_task.sh \
  --provider codex \
  --persona yuejian \
  --platform xiaohongshu \
  --instruction "重写标题并压短开头" \
  --input-file /tmp/out.md
```

## 审核

```bash
./run_review_task.sh \
  --provider claude \
  --persona yuejian \
  --platform xiaohongshu \
  --input-file /tmp/out.md
```

## 说明

- 这套脚本走的是“本地 prompt workflow”，不是 `/content-creation`
- Claude skill 仍然可保留，但不再是唯一入口
- 如果 `codex` 所在环境没有网络或账号未登录，调用会失败
