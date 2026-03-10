---
name: transcription
description: 音视频转录工具，将URL或本地文件转为文字，有价值的转录存入 Research
allowed-tools: Bash, Read, Write
argument-hint: "<URL or file path>"
---

## 任务
将音视频内容转录为文字。

## 流程

### 如果输入是小宇宙链接
直接使用项目自带的转录脚本（内置下载+缓存+faster_whisper 转录）：
```bash
python3 scripts/podcast_transcribe.py "$ARGUMENTS" -m medium
```
脚本会：
1. 自动从小宇宙页面提取音频链接
2. 下载音频（带缓存，不重复下载）
3. 用 faster_whisper 转录（带缓存，不重复转录）
4. 输出 `META:{json}` 头 + `---` 分隔 + 转录文本

### 如果输入是其他 URL
用 yt-dlp 下载后手动转录：
```bash
yt-dlp -x --audio-format wav -o "/tmp/transcribe_input.wav" "$ARGUMENTS"
python3 -c "
from faster_whisper import WhisperModel
model = WhisperModel('medium', device='cpu', compute_type='int8')
segments, info = model.transcribe('/tmp/transcribe_input.wav', language='zh', beam_size=5, vad_filter=True)
for seg in segments:
    print(seg.text.strip())
"
```

### 如果输入是本地文件路径
直接用 faster_whisper 转录：
```bash
python3 -c "
from faster_whisper import WhisperModel
model = WhisperModel('medium', device='cpu', compute_type='int8')
segments, info = model.transcribe('$ARGUMENTS', language='zh', beam_size=5, vad_filter=True)
for seg in segments:
    print(seg.text.strip())
"
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
