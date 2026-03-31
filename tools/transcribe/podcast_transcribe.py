#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
播客转录工具
输入小宇宙链接 → 下载音频 → Whisper 转录 → stdout 输出文本
带缓存：同一链接不重复转录
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup
from faster_whisper import WhisperModel

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
}

CACHE_DIR = os.path.expanduser("~/.cache/social_media/transcripts")
AUDIO_CACHE_DIR = os.path.expanduser("~/.cache/social_media/audio")


# ── 缓存 ─────────────────────────────────────────────────────

def get_cache_key(url):
    """URL → 稳定的缓存文件名"""
    episode_id = re.search(r"/episode/([a-f0-9]+)", url)
    if episode_id:
        return episode_id.group(1)
    return hashlib.md5(url.encode()).hexdigest()


def load_cache(url):
    """尝试加载缓存的转录结果，返回 (transcript, meta) 或 (None, None)"""
    key = get_cache_key(url)
    cache_file = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data["transcript"], data.get("meta", {})
    return None, None


def save_cache(url, transcript, meta):
    """保存转录结果到缓存"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = get_cache_key(url)
    cache_file = os.path.join(CACHE_DIR, f"{key}.json")
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({
            "url": url,
            "transcript": transcript,
            "meta": meta,
            "cached_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, f, ensure_ascii=False, indent=2)


# ── 小宇宙 ───────────────────────────────────────────────────

def fetch_episode_info(url):
    """从小宇宙页面提取音频链接和标题"""
    print("[1/3] 获取播客信息...", file=sys.stderr)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag or not script_tag.string:
        raise ValueError("无法提取页面数据，页面结构可能已变更")

    data = json.loads(script_tag.string)
    ep = data["props"]["pageProps"]["episode"]

    title = ep.get("title", "未知标题")
    podcast = ep.get("podcast", {}).get("title", "")
    audio_url = ep["enclosure"]["url"]

    print(f"     播客: {podcast}", file=sys.stderr)
    print(f"     单集: {title}", file=sys.stderr)
    return audio_url, title, podcast


def download_audio(audio_url, save_path):
    """下载音频文件"""
    print("[2/3] 下载音频...", file=sys.stderr)
    resp = requests.get(audio_url, headers=HEADERS, stream=True, timeout=60)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                print(f"\r     进度: {downloaded/total*100:.0f}%",
                      end="", flush=True, file=sys.stderr)
    print(f"\n     完成: {downloaded // 1024 // 1024}MB", file=sys.stderr)


# ── 转录 ─────────────────────────────────────────────────────

def transcribe(audio_path, model_size="medium", language="zh"):
    """Whisper 转录，返回完整文本"""
    print(f"[3/3] 转录中 (模型: {model_size})...", file=sys.stderr)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    start = time.time()

    segments, info = model.transcribe(
        audio_path, language=language, beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=600, speech_pad_ms=200),
    )

    paragraphs, current, last_end = [], [], 0.0
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        if seg.start - last_end > 2.0 and current:
            paragraphs.append("".join(current))
            current = []
        current.append(text)
        last_end = seg.end
    if current:
        paragraphs.append("".join(current))

    elapsed = time.time() - start
    print(f"     完成 | 音频: {info.duration:.0f}s | 耗时: {elapsed:.0f}s",
          file=sys.stderr)
    return "\n\n".join(paragraphs)


# ── 主流程 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="播客转录工具")
    parser.add_argument("url", help="小宇宙单集链接")
    parser.add_argument("-m", "--model", default="medium",
                        choices=["tiny", "base", "small", "medium", "large-v3"],
                        help="Whisper 模型 (默认: medium)")
    args = parser.parse_args()

    if not re.match(r"https?://(www\.)?xiaoyuzhoufm\.com/episode/", args.url):
        print("错误: 请输入小宇宙单集链接", file=sys.stderr)
        sys.exit(1)

    # 检查缓存
    cached_transcript, cached_meta = load_cache(args.url)
    if cached_transcript:
        print("[缓存] 该链接已转录过，直接使用缓存", file=sys.stderr)
        if cached_meta:
            print(f"     播客: {cached_meta.get('podcast', '')}", file=sys.stderr)
            print(f"     单集: {cached_meta.get('title', '')}", file=sys.stderr)
        # 输出元信息头（JSON 格式，便于解析）
        meta_line = json.dumps(cached_meta, ensure_ascii=False)
        print(f"META:{meta_line}")
        print("---")
        print(cached_transcript)
        return

    # 1. 获取信息
    audio_url, title, podcast = fetch_episode_info(args.url)

    # 2. 下载音频（缓存到 ~/.cache）
    os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
    audio_path = os.path.join(AUDIO_CACHE_DIR, f"{get_cache_key(args.url)}.m4a")
    if os.path.exists(audio_path):
        print("[2/3] 音频已存在，跳过下载", file=sys.stderr)
    else:
        download_audio(audio_url, audio_path)

    # 3. 转录
    transcript = transcribe(audio_path, model_size=args.model)

    # 4. 保存缓存
    meta = {"title": title, "podcast": podcast, "url": args.url}
    save_cache(args.url, transcript, meta)

    # 5. 输出到 stdout（Claude Code 读取）
    meta_line = json.dumps(meta, ensure_ascii=False)
    print(f"META:{meta_line}")
    print("---")
    print(transcript)

    print(f"\n转录完成!", file=sys.stderr)


if __name__ == "__main__":
    main()
