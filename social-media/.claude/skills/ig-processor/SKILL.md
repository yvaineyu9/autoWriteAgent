---
name: ig-processor
description: 下载Instagram视频，提取关键帧并去重，保存独特帧到指定目录
allowed-tools: Bash, Read
argument-hint: "<url>"
---

## 任务
下载 Instagram 视频/帖子，提取关键帧（1fps），去除重复帧，保存到桌面。

## 流程

### Step 1：下载并处理
```bash
python3 /Users/smalldog/Desktop/instagram_processor.py "$ARGUMENTS"
```

### Step 2：报告结果
处理完成后，报告：
- 下载的视频信息
- 提取了多少帧
- 去重后保留了多少帧
- 文件保存位置
