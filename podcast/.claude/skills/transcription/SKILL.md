---
name: transcription
description: 音视频转录工具，将URL或本地文件转为文字
allowed-tools: Bash, Read
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

### 输出
返回转录后的完整文字内容。
