---
name: ig-processor
description: 下载Instagram视频，提取关键帧并去重，保存到仓库 Resources 目录
allowed-tools: Bash, Read, Write
argument-hint: "<url>"
---

## 任务
下载 Instagram 视频/帖子，提取关键帧（1fps），去除重复帧，保存到仓库。

## 流程

### Step 1：下载并处理
```bash
python3 /Users/smalldog/Desktop/instagram_processor.py "$ARGUMENTS"
```

### Step 2：归仓

1. **素材归档**：将提取的关键帧移动到 `50_Resources/ig_<日期>_<简述>/`
2. **每日记录**：在 `10_Daily/YYYY-MM-DD.md` 追加记录
   - 格式：`- IG素材处理：<URL简述>，提取 N 帧 → [[50_Resources/ig_<日期>_<简述>]]`
   - 如果当日文件不存在，基于 `99_System/templates/daily.md` 创建

### Step 3：报告结果
处理完成后，报告：
- 下载的视频信息
- 提取了多少帧
- 去重后保留了多少帧
- 文件保存位置（仓库路径）
