#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
播客说话人分离转录工具
使用 faster-whisper 转录 + SpeechBrain 说话人分离
无需 HuggingFace token
"""

import argparse
import json
import os
import sys
import numpy as np
from pathlib import Path

CACHE_DIR = os.path.expanduser("~/.cache/social_media")
AUDIO_DIR = os.path.join(CACHE_DIR, "audio")
TRANSCRIPT_DIR = os.path.join(CACHE_DIR, "transcripts_diarized")


def load_audio(audio_path, sr=16000):
    """加载音频文件并转为 16kHz 单声道"""
    import torch
    import torchaudio

    waveform, sample_rate = torchaudio.load(audio_path)
    # 转为单声道
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    # 重采样到 16kHz
    if sample_rate != sr:
        resampler = torchaudio.transforms.Resample(sample_rate, sr)
        waveform = resampler(waveform)
    return waveform.squeeze(0).numpy(), sr


def transcribe_with_timestamps(audio_path, model_size="medium"):
    """使用 faster-whisper 转录并获取带时间戳的片段"""
    from faster_whisper import WhisperModel

    print("[1/3] 加载 Whisper 模型...", file=sys.stderr)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print("[2/3] 转录中（带时间戳）...", file=sys.stderr)
    segments, info = model.transcribe(
        audio_path,
        language="zh",
        vad_filter=True,
        vad_parameters=dict(
            min_silence_duration_ms=300,
            speech_pad_ms=200,
        ),
    )

    result = []
    for seg in segments:
        result.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        })
        # 进度提示
        print(f"     {seg.start:.1f}s - {seg.end:.1f}s: {seg.text.strip()[:30]}...", file=sys.stderr)

    print(f"     转录完成，共 {len(result)} 个片段", file=sys.stderr)
    return result


def diarize_segments(audio_path, segments, num_speakers=2):
    """使用 SpeechBrain 对每个片段做说话人识别"""
    from speechbrain.inference.speaker import EncoderClassifier
    from spectralcluster import SpectralClusterer
    import torch
    import torchaudio

    print("[3/3] 说话人分离中...", file=sys.stderr)

    # 加载说话人嵌入模型
    print("     加载 SpeechBrain 模型...", file=sys.stderr)
    classifier = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=os.path.join(CACHE_DIR, "speechbrain_model"),
        run_opts={"device": "cpu"},
    )

    # 加载完整音频
    waveform, sample_rate = torchaudio.load(audio_path)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sample_rate != 16000:
        resampler = torchaudio.transforms.Resample(sample_rate, 16000)
        waveform = resampler(waveform)
        sample_rate = 16000

    # 对每个片段提取说话人嵌入
    embeddings = []
    valid_indices = []
    for i, seg in enumerate(segments):
        start_sample = int(seg["start"] * sample_rate)
        end_sample = int(seg["end"] * sample_rate)
        chunk = waveform[:, start_sample:end_sample]

        # 跳过太短的片段（小于0.5秒）
        if chunk.shape[1] < sample_rate * 0.5:
            continue

        with torch.no_grad():
            emb = classifier.encode_batch(chunk)
            embeddings.append(emb.squeeze().numpy())
            valid_indices.append(i)

    if not embeddings:
        print("     警告：没有足够长的片段可以分析", file=sys.stderr)
        return segments

    embeddings_array = np.array(embeddings)

    # 使用谱聚类分离说话人
    print(f"     对 {len(embeddings)} 个片段进行聚类（{num_speakers} 个说话人）...", file=sys.stderr)
    clusterer = SpectralClusterer(
        min_clusters=num_speakers,
        max_clusters=num_speakers,
    )
    labels = clusterer.predict(embeddings_array)

    # 将标签写回 segments
    for idx, label in zip(valid_indices, labels):
        segments[idx]["speaker"] = f"Speaker_{label}"

    # 对没有分配到标签的短片段，使用最近的有标签片段的说话人
    for i, seg in enumerate(segments):
        if "speaker" not in seg:
            # 找最近的有标签的片段
            nearest = None
            min_dist = float("inf")
            for j, other in enumerate(segments):
                if "speaker" in other:
                    dist = abs(seg["start"] - other["start"])
                    if dist < min_dist:
                        min_dist = dist
                        nearest = other["speaker"]
            seg["speaker"] = nearest or "Speaker_0"

    # 统计每个说话人的发言量
    speaker_stats = {}
    for seg in segments:
        spk = seg["speaker"]
        if spk not in speaker_stats:
            speaker_stats[spk] = {"count": 0, "duration": 0}
        speaker_stats[spk]["count"] += 1
        speaker_stats[spk]["duration"] += seg["end"] - seg["start"]

    for spk, stats in sorted(speaker_stats.items()):
        print(f"     {spk}: {stats['count']} 段, {stats['duration']:.1f}秒", file=sys.stderr)

    return segments


def merge_consecutive(segments):
    """合并同一说话人连续的片段"""
    if not segments:
        return segments

    merged = [segments[0].copy()]
    for seg in segments[1:]:
        prev = merged[-1]
        # 如果同一个说话人且间隔小于2秒，合并
        if seg["speaker"] == prev["speaker"] and (seg["start"] - prev["end"]) < 2.0:
            prev["end"] = seg["end"]
            prev["text"] += seg["text"]
        else:
            merged.append(seg.copy())

    return merged


def format_output(segments, speaker_names=None):
    """格式化输出为对话体"""
    if speaker_names is None:
        speaker_names = {}

    output = []
    for seg in segments:
        speaker = speaker_names.get(seg["speaker"], seg["speaker"])
        text = seg["text"].strip()
        if text:
            output.append(f"{speaker}：{text}\n")

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="播客说话人分离转录工具")
    parser.add_argument("audio", help="音频文件路径")
    parser.add_argument("-m", "--model", default="medium", help="Whisper 模型大小")
    parser.add_argument("-n", "--num-speakers", type=int, default=2, help="说话人数量")
    parser.add_argument("--names", default=None,
                        help="说话人名称映射，格式: 'Speaker_0=小狗仔,Speaker_1=小刀'")
    parser.add_argument("-o", "--output", default=None, help="输出文件路径")

    args = parser.parse_args()

    if not os.path.exists(args.audio):
        print(f"错误: 音频文件不存在: {args.audio}", file=sys.stderr)
        sys.exit(1)

    # 解析说话人名称
    speaker_names = {}
    if args.names:
        for pair in args.names.split(","):
            key, val = pair.strip().split("=")
            speaker_names[key.strip()] = val.strip()

    # 转录
    segments = transcribe_with_timestamps(args.audio, args.model)

    # 说话人分离
    segments = diarize_segments(args.audio, segments, args.num_speakers)

    # 合并连续片段
    segments = merge_consecutive(segments)

    # 格式化输出
    output = format_output(segments, speaker_names)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"\n输出已保存到: {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
