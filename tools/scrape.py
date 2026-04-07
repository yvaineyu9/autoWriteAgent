#!/usr/bin/env python3
"""
灵感采集（浏览器自动化）：从小红书采集笔记内容到 inbox。

用法：
  python tools/scrape.py note <url>                    # 单篇采集
  python tools/scrape.py favorites [--limit N]         # 收藏页采集
  python tools/scrape.py account <url> [--limit N]     # 账号页采集

输出：
  stdout: JSON 结果
  data/content/inbox/<uuid>.md + ideas 表
"""

import argparse
import json
import os
import sys
import uuid
from dataclasses import asdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_connection, PROJECT_ROOT
from browser.engine import BrowserEngine
from browser.xhs import XhsScraper, NoteData

INBOX_DIR = os.path.join(PROJECT_ROOT, "data", "content", "inbox")


def _normalize_source_url(url: str) -> str:
    """统一 source_url，便于去重。"""
    return (url or "").split("?", 1)[0].strip()


def _note_to_markdown(note: NoteData) -> str:
    """将 NoteData 转为 inbox markdown 格式。"""
    lines = [f"# {note.title or '无标题'}", ""]

    lines.append(f"**作者**: {note.author}")
    lines.append(f"**来源**: [小红书原文]({note.source_url})")
    if note.published_at:
        lines.append(f"**发布时间**: {note.published_at}")

    # 互动数据
    metrics_parts = []
    if note.likes:
        metrics_parts.append(f"点赞 {note.likes}")
    if note.collects:
        metrics_parts.append(f"收藏 {note.collects}")
    if note.comments:
        metrics_parts.append(f"评论 {note.comments}")
    if note.shares:
        metrics_parts.append(f"分享 {note.shares}")
    if metrics_parts:
        lines.append(f"**互动数据**: {' / '.join(metrics_parts)}")

    lines.append("")

    # 正文
    if note.content_text:
        lines.append("## 正文")
        lines.append("")
        lines.append(note.content_text)
        lines.append("")

    # 图片 OCR
    if note.image_ocr:
        lines.append("## 图片文字")
        lines.append("")
        for i, ocr_text in enumerate(note.image_ocr, 1):
            lines.append(f"### 图{i}")
            lines.append(ocr_text if ocr_text else "（未识别到文字）")
            lines.append("")

    # 标签
    if note.tags:
        lines.append("## 标签")
        lines.append(" ".join(f"#{t}" for t in note.tags))
        lines.append("")

    return "\n".join(lines)


def _normalize_title(title: str) -> str:
    """标准化标题用于内容去重：去除标点、空格、emoji，转小写。"""
    import re as _re
    if not title:
        return ""
    # 去除 emoji 和特殊符号，只保留中文、字母、数字
    text = _re.sub(r'[^\u4e00-\u9fff\w]', '', title)
    return text.lower()


def _save_to_inbox(note: NoteData) -> dict:
    """将采集结果存入 inbox 文件和 ideas 表。"""
    normalized_url = _normalize_source_url(note.source_url)
    title = note.title or normalized_url or note.source_url
    tags_json = json.dumps(note.tags, ensure_ascii=False) if note.tags else "[]"

    conn = get_connection()
    try:
        existing = None
        if note.note_id:
            existing = conn.execute(
                """SELECT id, title, file_path
                   FROM ideas
                   WHERE note_id = ?
                   ORDER BY created_at DESC
                   LIMIT 1""",
                (note.note_id,),
            ).fetchone()

        if not existing and normalized_url:
            existing = conn.execute(
                """SELECT id, title, file_path
                   FROM ideas
                   WHERE source_url = ?
                   ORDER BY created_at DESC
                   LIMIT 1""",
                (normalized_url,),
            ).fetchone()

        # 内容去重：标题相似度比对
        if not existing and title:
            norm_title = _normalize_title(title)
            if norm_title and len(norm_title) >= 4:
                rows = conn.execute(
                    "SELECT id, title, file_path FROM ideas"
                ).fetchall()
                for row in rows:
                    existing_norm = _normalize_title(row["title"])
                    if not existing_norm:
                        continue
                    # 完全匹配 或 一方包含另一方（短标题至少 8 字符才做包含判断）
                    if norm_title == existing_norm:
                        existing = row
                        break
                    if len(norm_title) >= 8 and len(existing_norm) >= 8:
                        if norm_title in existing_norm or existing_norm in norm_title:
                            existing = row
                            break

        if existing:
            return {
                "idea_id": existing["id"],
                "title": existing["title"],
                "file_path": existing["file_path"],
                "note_id": note.note_id,
                "capture_status": note.capture_status,
                "duplicate": True,
            }

        idea_id = str(uuid.uuid4())
        os.makedirs(INBOX_DIR, exist_ok=True)

        # 写文件
        content = _note_to_markdown(note)
        file_name = f"{idea_id}.md"
        abs_path = os.path.join(INBOX_DIR, file_name)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

        # 写数据库
        rel_path = f"inbox/{file_name}"
        conn.execute(
            """INSERT INTO ideas (id, title, tags, source, status, note_id, source_url, file_path)
               VALUES (?, ?, ?, 'scrape', 'pending', ?, ?, ?)""",
            (idea_id, title, tags_json, note.note_id or None, normalized_url or None, rel_path),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "idea_id": idea_id,
        "title": title,
        "file_path": rel_path,
        "note_id": note.note_id,
        "capture_status": note.capture_status,
        "duplicate": False,
    }


def cmd_note(args):
    """采集单篇笔记。"""
    with BrowserEngine(port=args.port) as engine:
        scraper = XhsScraper(engine)
        print(f"正在采集: {args.url}", file=sys.stderr)

        note = scraper.scrape_note(args.url)

        if note.capture_status == "failed":
            print(f"采集失败: {note.failure_reason}", file=sys.stderr)
            print(json.dumps(asdict(note), ensure_ascii=False, default=str))
            sys.exit(2)

        result = _save_to_inbox(note)
        if result["duplicate"]:
            print(f"已存在，跳过入库: {result['title']}", file=sys.stderr)
        else:
            print(f"采集完成: {note.title}", file=sys.stderr)
        print(json.dumps(result, ensure_ascii=False))


def cmd_favorites(args):
    """采集收藏页。"""
    min_eng = args.min_engagement
    with BrowserEngine(port=args.port) as engine:
        scraper = XhsScraper(engine)
        print(f"正在采集收藏页 (limit={args.limit}, 入库门槛={min_eng})...", file=sys.stderr)

        summaries = scraper.scrape_favorites(limit=args.limit)
        print(f"发现 {len(summaries)} 条笔记，开始逐条采集...", file=sys.stderr)

        results = []
        saved = 0
        duplicates = 0
        failed = 0
        low_engagement = 0
        for i, summary in enumerate(summaries, 1):
            print(f"[{i}/{len(summaries)}] {summary.title or summary.note_id}", file=sys.stderr)

            note = scraper.scrape_note(summary.source_url)
            if note.capture_status == "failed":
                failed += 1
                print(f"  采集失败，跳过: {note.failure_reason}", file=sys.stderr)
                results.append({
                    "note_id": note.note_id,
                    "source_url": _normalize_source_url(note.source_url),
                    "capture_status": note.capture_status,
                    "failure_reason": note.failure_reason,
                    "skipped": True,
                })
                continue

            # 入库门槛：点赞+收藏 >= min_engagement
            engagement = note.likes + note.collects
            if engagement < min_eng:
                low_engagement += 1
                print(f"  互动不足 ({engagement}<{min_eng})，跳过: {note.title}", file=sys.stderr)
                results.append({
                    "note_id": note.note_id,
                    "title": note.title,
                    "engagement": engagement,
                    "skipped": True,
                    "skip_reason": "low_engagement",
                })
                continue

            result = _save_to_inbox(note)
            if result["duplicate"]:
                duplicates += 1
                print(f"  已存在，跳过入库: {result['title']}", file=sys.stderr)
            else:
                saved += 1
                print(f"  入库成功 (互动={engagement}): {note.title}", file=sys.stderr)
            results.append(result)

            BrowserEngine.random_delay(2.0, 4.0)

        output = {
            "count": len(results),
            "saved": saved,
            "duplicates": duplicates,
            "failed": failed,
            "low_engagement": low_engagement,
            "ideas": results,
        }
        print(json.dumps(output, ensure_ascii=False))


def cmd_account(args):
    """采集账号页笔记。"""
    min_eng = args.min_engagement
    with BrowserEngine(port=args.port) as engine:
        scraper = XhsScraper(engine)
        print(f"正在采集账号页: {args.url} (limit={args.limit}, 入库门槛={min_eng})", file=sys.stderr)

        summaries = scraper.scrape_account(args.url, limit=args.limit)
        print(f"发现 {len(summaries)} 条笔记，开始逐条采集...", file=sys.stderr)

        results = []
        saved = 0
        duplicates = 0
        failed = 0
        low_engagement = 0
        for i, summary in enumerate(summaries, 1):
            print(f"[{i}/{len(summaries)}] {summary.title or summary.note_id}", file=sys.stderr)

            note = scraper.scrape_note(summary.source_url)
            if note.capture_status == "failed":
                failed += 1
                print(f"  采集失败，跳过: {note.failure_reason}", file=sys.stderr)
                results.append({
                    "note_id": note.note_id,
                    "source_url": _normalize_source_url(note.source_url),
                    "capture_status": note.capture_status,
                    "failure_reason": note.failure_reason,
                    "skipped": True,
                })
                continue

            # 入库门槛：点赞+收藏 >= min_engagement
            engagement = note.likes + note.collects
            if engagement < min_eng:
                low_engagement += 1
                print(f"  互动不足 ({engagement}<{min_eng})，跳过: {note.title}", file=sys.stderr)
                results.append({
                    "note_id": note.note_id,
                    "title": note.title,
                    "engagement": engagement,
                    "skipped": True,
                    "skip_reason": "low_engagement",
                })
                continue

            result = _save_to_inbox(note)
            if result["duplicate"]:
                duplicates += 1
                print(f"  已存在，跳过入库: {result['title']}", file=sys.stderr)
            else:
                saved += 1
                print(f"  入库成功 (互动={engagement}): {note.title}", file=sys.stderr)
            results.append(result)

            BrowserEngine.random_delay(2.0, 4.0)

        output = {
            "count": len(results),
            "saved": saved,
            "duplicates": duplicates,
            "failed": failed,
            "low_engagement": low_engagement,
            "ideas": results,
        }
        print(json.dumps(output, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="小红书灵感采集")
    parser.add_argument("--port", type=int, default=9222, help="Chrome debug 端口")
    subparsers = parser.add_subparsers(dest="command")

    # note
    p_note = subparsers.add_parser("note", help="单篇笔记采集")
    p_note.add_argument("url", help="小红书笔记 URL")

    # favorites
    p_fav = subparsers.add_parser("favorites", help="收藏页采集")
    p_fav.add_argument("--limit", type=int, default=20, help="采集数量上限")
    p_fav.add_argument("--min-engagement", type=int, default=500, help="入库门槛：点赞+收藏最低值（默认 500）")

    # account
    p_acc = subparsers.add_parser("account", help="账号页笔记采集")
    p_acc.add_argument("url", help="账号主页 URL")
    p_acc.add_argument("--limit", type=int, default=20, help="采集数量上限")
    p_acc.add_argument("--min-engagement", type=int, default=500, help="入库门槛：点赞+收藏最低值（默认 500）")

    args = parser.parse_args()

    if not args.command:
        parser.print_help(sys.stderr)
        sys.exit(1)

    dispatch = {
        "note": cmd_note,
        "favorites": cmd_favorites,
        "account": cmd_account,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
