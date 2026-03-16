---
name: save-and-push
description: 快速保存当前修改并推送到 GitHub 远程仓库
allowed-tools: Bash
argument-hint: "[提交说明]"
---

## 任务
将当前所有修改保存并推送到 GitHub。

## 流程

### Step 1：检查状态
```bash
cd /Users/moonvision/claude-workflows && git status
```

### Step 2：暂存所有修改
```bash
git add .
```

### Step 3：提交
如果 `$ARGUMENTS` 不为空，用它作为提交说明：
```bash
git commit -m "$ARGUMENTS"
```
如果为空，自动根据修改内容生成简短的提交说明。

### Step 4：推送
```bash
git push
```

### Step 5：确认
输出推送结果，确认成功。
