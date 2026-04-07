#!/usr/bin/env python3
"""
数据监控（浏览器自动化）：自动采集已发布内容的互动数据。

用法：
  python tools/monitor.py run [--pub-id N]     # 单篇或全量巡检
  python tools/monitor.py remind               # 待采提醒（不启动浏览器）

输出：
  stdout: JSON 结果
  metrics 表新增快照 + publications.platform_status 更新
"""

import argparse
import difflib
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_connection
from browser.engine import BrowserEngine
from browser.xhs import XhsScraper
from persona_config import load_platform_config



def _normalize_title(title: str) -> str:
    return re.sub(r"[\W_]+", "", (title or "").lower())


def _normalize_url(url: str) -> str:
    return (url or "").split("?", 1)[0].strip()


def _resolve_account_url(persona: str, platform: str, override_url: str | None) -> str:
    if override_url:
        return override_url

    config = load_platform_config(persona, platform)
    return config.get("profile_url", "")



def _match_title_to_rows(title: str, rows, used_ids: set, id_field: str = "id"):
    normalized_title = _normalize_title(title)
    if not normalized_title:
        return None

    exact_candidates = []
    fuzzy_candidates = []
    scored_candidates = []
    for row in rows:
        row_id = row[id_field]
        if row_id in used_ids:
            continue

        row_title = _normalize_title(row["title"] or row["content_id"])
        if not row_title:
            continue

        if row_title == normalized_title:
            exact_candidates.append(row)
            continue

        if len(row_title) >= 6 and len(normalized_title) >= 6:
            if row_title in normalized_title or normalized_title in row_title:
                fuzzy_candidates.append(row)
                continue

        score = difflib.SequenceMatcher(None, normalized_title, row_title).ratio()
        if score >= 0.6:
            scored_candidates.append((score, row))

    if len(exact_candidates) == 1:
        return exact_candidates[0]
    if len(fuzzy_candidates) == 1:
        return fuzzy_candidates[0]
    if scored_candidates:
        scored_candidates.sort(key=lambda item: item[0], reverse=True)
        best_score, best_row = scored_candidates[0]
        second_score = scored_candidates[1][0] if len(scored_candidates) > 1 else 0
        if best_score >= 0.72 and (best_score - second_score >= 0.08):
            return best_row
    return None



def cmd_dump_account(args):
    """导出账号页当前笔记摘要。"""
    account_url = _resolve_account_url(args.persona, args.platform, args.account_url)
    if not account_url:
        print(
            f"未找到 {args.persona}/{args.platform} 的账号主页 URL，请传 --account-url 或补平台配置",
            file=sys.stderr,
        )
        sys.exit(1)

    with BrowserEngine(port=args.port) as engine:
        scraper = XhsScraper(engine)
        summaries = scraper.scrape_account(account_url, limit=args.limit)

    results = []
    for summary in summaries:
        results.append(
            {
                "title": summary.title,
                "author": summary.author,
                "note_id": summary.note_id,
                "post_url": summary.source_url,
                "likes": summary.likes,
            }
        )
    print(json.dumps(results, ensure_ascii=False))
    print(f"账号页抓到 {len(results)} 条笔记摘要", file=sys.stderr)



def cmd_sync_account(args):
    """按账号页当前内容全量对齐发布记录，同时采集卡片点赞数。"""
    persona = args.persona
    platform = args.platform
    account_url = _resolve_account_url(persona, platform, args.account_url)
    if not account_url:
        print(
            f"未找到 {persona}/{platform} 的账号主页 URL，请传 --account-url 或补平台配置",
            file=sys.stderr,
        )
        sys.exit(1)

    conn = get_connection()
    try:
        checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = conn.execute(
            """SELECT p.id, p.content_id, p.status, p.post_url, p.published_at, p.created_at,
                      c.title
               FROM publications p
               LEFT JOIN contents c ON c.content_id = p.content_id
               WHERE p.persona_id = ?
                 AND p.platform = ?
               ORDER BY p.id DESC""",
            (persona, platform),
        ).fetchall()

        with BrowserEngine(port=args.port) as engine:
            scraper = XhsScraper(engine)
            summaries = scraper.scrape_account(account_url, limit=args.limit)

        used_publication_ids = set()
        matched = 0
        changed = 0
        unmatched_live = []
        unmatched_db = []
        results = []

        # 预加载无 publication 的素材，用于二次匹配
        content_rows = conn.execute(
            """SELECT c.content_id, c.title, c.status
               FROM contents c
               WHERE c.persona_id = ? AND c.platform = ?
                 AND NOT EXISTS (
                     SELECT 1 FROM publications p WHERE p.content_id = c.content_id
                 )
               ORDER BY c.created_at DESC""",
            (persona, platform),
        ).fetchall()
        used_content_ids = set()

        for summary in summaries:
            row = _match_title_to_rows(summary.title, rows, used_publication_ids)
            if not row:
                # 二次匹配：在无 publication 的素材中查找
                content_row = _match_title_to_rows(
                    summary.title, content_rows, used_content_ids,
                    id_field="content_id",
                )
                if content_row:
                    # 自动创建 publication 记录
                    used_content_ids.add(content_row["content_id"])
                    cursor = conn.execute(
                        """INSERT INTO publications
                               (content_id, persona_id, platform, status, published_at,
                                platform_status, platform_checked_at)
                           VALUES (?, ?, ?, 'published', ?, 'normal', ?)""",
                        (content_row["content_id"], persona, platform, checked_at, checked_at),
                    )
                    new_pub_id = cursor.lastrowid
                    conn.execute(
                        "UPDATE contents SET status='published', updated_at=datetime('now','localtime') WHERE content_id=?",
                        (content_row["content_id"],),
                    )
                    conn.execute(
                        """INSERT INTO status_log (content_id, from_status, to_status, operator, note)
                           VALUES (?, ?, 'published', 'account_sync', '账号页对齐-自动建台账')""",
                        (content_row["content_id"], content_row["status"]),
                    )
                    conn.execute(
                        """INSERT INTO metrics (publication_id, views, likes, collects, comments, shares, captured_at)
                           VALUES (?, 0, ?, 0, 0, 0, ?)""",
                        (new_pub_id, summary.likes, checked_at),
                    )
                    matched += 1
                    changed += 1
                    results.append(
                        {
                            "publication_id": new_pub_id,
                            "content_id": content_row["content_id"],
                            "title": content_row["title"],
                            "matched_post_title": summary.title,
                            "likes": summary.likes,
                            "from_status": "new",
                            "changed": True,
                        }
                    )
                    continue

                unmatched_live.append(
                    {
                        "title": summary.title,
                        "note_id": summary.note_id,
                        "likes": summary.likes,
                    }
                )
                continue

            used_publication_ids.add(row["id"])
            matched += 1
            previous_status = row["status"]
            was_changed = previous_status != "published"

            conn.execute(
                """UPDATE publications
                   SET status = 'published',
                       published_at = COALESCE(published_at, created_at),
                       platform_status = 'normal',
                       platform_checked_at = ?,
                       platform_failure_reason = NULL
                   WHERE id = ?""",
                (checked_at, row["id"]),
            )
            conn.execute(
                "UPDATE contents SET status='published', updated_at=datetime('now','localtime') WHERE content_id=?",
                (row["content_id"],),
            )
            if previous_status != "published":
                conn.execute(
                    """INSERT INTO status_log (content_id, from_status, to_status, operator, note)
                       VALUES (?, ?, 'published', 'account_sync', '账号页对齐')""",
                    (row["content_id"], previous_status),
                )

            # 写入点赞数快照（仅点赞，来自账号页卡片）
            conn.execute(
                """INSERT INTO metrics (publication_id, views, likes, collects, comments, shares, captured_at)
                   VALUES (?, 0, ?, 0, 0, 0, ?)""",
                (row["id"], summary.likes, checked_at),
            )

            if was_changed:
                changed += 1

            results.append(
                {
                    "publication_id": row["id"],
                    "content_id": row["content_id"],
                    "title": row["title"] or row["content_id"],
                    "matched_post_title": summary.title,
                    "likes": summary.likes,
                    "from_status": previous_status,
                    "changed": was_changed,
                }
            )

        for row in rows:
            if row["id"] in used_publication_ids:
                continue
            if row["status"] == "published":
                conn.execute(
                    """UPDATE publications
                       SET platform_status = 'missing_from_profile',
                           platform_checked_at = ?,
                           platform_failure_reason = ?
                       WHERE id = ?""",
                    (checked_at, "未在账号页当前可见内容中匹配到", row["id"]),
                )
            unmatched_db.append(
                {
                    "publication_id": row["id"],
                    "content_id": row["content_id"],
                    "title": row["title"] or row["content_id"],
                    "status": row["status"],
                }
            )

        conn.commit()
        output = {
            "account_count": len(summaries),
            "matched": matched,
            "changed": changed,
            "live_unmatched": unmatched_live,
            "db_unmatched": unmatched_db,
            "results": results,
        }
        print(json.dumps(output, ensure_ascii=False))
        print(
            f"账号全量对齐完成：账号页 {len(summaries)} 条，匹配 {matched} 条，更新 {changed} 条",
            file=sys.stderr,
        )
    finally:
        conn.close()



def cmd_remind(args):
    """查找需要采集数据的发布记录。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT p.id, p.content_id, p.persona_id, p.platform, p.post_url, p.published_at,
                      c.title
               FROM publications p
               LEFT JOIN contents c ON c.content_id = p.content_id
               WHERE p.status = 'published'
               AND NOT EXISTS (
                   SELECT 1 FROM metrics m
                   WHERE m.publication_id = p.id
                   AND m.captured_at >= datetime('now', '-7 days', 'localtime')
               )
               ORDER BY p.published_at DESC"""
        ).fetchall()

        results = []
        for r in rows:
            results.append({
                "pub_id": r["id"],
                "content_id": r["content_id"],
                "title": r["title"] or r["content_id"],
                "persona": r["persona_id"],
                "platform": r["platform"],
                "post_url": r["post_url"] or "",
                "published_at": r["published_at"] or "",
                "has_url": bool(r["post_url"]),
            })

        print(json.dumps(results, ensure_ascii=False))

        # 汇总提示
        total = len(results)
        with_url = sum(1 for r in results if r["has_url"])
        without_url = total - with_url
        if total:
            print(f"有 {total} 条发布记录需要采集数据", file=sys.stderr)
            if without_url:
                print(f"  其中 {without_url} 条缺少 post_url，需手动补充后才能自动监控", file=sys.stderr)
            if with_url:
                print(f"  {with_url} 条可自动监控: python tools/monitor.py run", file=sys.stderr)
        else:
            print("所有发布记录数据均已采集", file=sys.stderr)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="数据监控")
    parser.add_argument("--port", type=int, default=9222, help="Chrome debug 端口")
    subparsers = parser.add_subparsers(dest="command")

    # dump-account
    p_dump = subparsers.add_parser("dump-account", help="导出账号页当前笔记摘要")
    p_dump.add_argument("--persona", required=True, help="人设 ID")
    p_dump.add_argument("--platform", default="xiaohongshu", help="平台")
    p_dump.add_argument("--account-url", default=None, help="账号主页 URL（可覆盖配置）")
    p_dump.add_argument("--limit", type=int, default=60, help="账号页采集数量上限")

    # sync-account
    p_sync = subparsers.add_parser("sync-account", help="按账号页对齐发布记录并采集点赞数")
    p_sync.add_argument("--persona", required=True, help="人设 ID")
    p_sync.add_argument("--platform", default="xiaohongshu", help="平台")
    p_sync.add_argument("--account-url", default=None, help="账号主页 URL（可覆盖配置）")
    p_sync.add_argument("--limit", type=int, default=60, help="账号页采集数量上限")

    # remind
    subparsers.add_parser("remind", help="查找待采集记录")

    args = parser.parse_args()

    if not args.command:
        parser.print_help(sys.stderr)
        sys.exit(1)

    dispatch = {
        "dump-account": cmd_dump_account,
        "sync-account": cmd_sync_account,
        "remind": cmd_remind,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
