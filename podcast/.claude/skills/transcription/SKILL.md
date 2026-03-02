---
name: transcription
description: 音视频转录工具，将URL或本地文件转为文字，有价值的转录存入 Research
allowed-tools: Bash, Read, Write
argument-hint: "<URL or file path>"
---

## 任务
将音视频内容转录为文字。

## 流程

### 如果输入是 URL
1. 用 yt-dlp 下载音频
```bash
yt-dlp -x --audio-format wav -o "/tmp/transcribe_input.wav" "$ARGUMENTS"
```

2. 用 whisper 转录
```bash
whisper /tmp/transcribe_input.wav --language Chinese --model medium
```

### 如果输入是本地文件路径
直接用 whisper 转录：
```bash
whisper "$ARGUMENTS" --language Chinese --model medium
```

### 中间产物处理

转录完成后，判断结果是否有沉淀价值：

- **有价值**（完整访谈、讲座、重要讨论）：
  - 存入 `30_Research/转录_<主题>_YYYY-MM-DD.md`
  - 在 `10_Daily/YYYY-MM-DD.md` 追加记录
- **临时性**（仅用于本次生产的片段）：
  - 仅返回文字内容，不保存到仓库

### 输出
返回转录后的完整文字内容，并告知是否已存入仓库。
