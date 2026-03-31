#!/usr/bin/env python3
"""
成品归档：将完成的内容文件归档到 data/content/<content_id>/ 并写入数据库。
"""

import argparse
import json
import os
import re
import shutil
import sys
import unicodedata
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_connection, PROJECT_ROOT

DATA_CONTENT_DIR = os.path.join(PROJECT_ROOT, "data", "content")


def _to_slug(title: str, max_len: int = 30) -> str:
    """将标题转为 ASCII slug。优先尝试 pypinyin，fallback 用 unicodedata 转换。"""
    try:
        from pypinyin import lazy_pinyin
        raw = "".join(lazy_pinyin(title))
    except ImportError:
        # fallback: 去掉非 ASCII 后用下划线连接
        nfkd = unicodedata.normalize("NFKD", title)
        raw = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
        raw = re.sub(r"[^\w\s-]", "", raw)

    slug = re.sub(r"[\s_-]+", "_", raw).strip("_").lower()
    # 只保留 ascii 字母数字和下划线
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    return slug[:max_len] if slug else "untitled"


def _unique_slug(conn, persona: str, platform: str, date_str: str, base_slug: str) -> str:
    """确保同日同人设同平台的 slug 唯一。"""
    prefix = f"{persona}_{platform}_{date_str}_{base_slug}"
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM contents WHERE content_id = ?", (prefix,)
    ).fetchone()
    if row["cnt"] == 0:
        return base_slug

    # 追加 _2, _3, ...
    n = 2
    while True:
        candidate = f"{base_slug}_{n}"
        cid = f"{persona}_{platform}_{date_str}_{candidate}"
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM contents WHERE content_id = ?", (cid,)
        ).fetchone()
        if row["cnt"] == 0:
            return candidate
        n += 1


def main():
    parser = argparse.ArgumentParser(description="成品归档")
    parser.add_argument("--persona", required=True, help="人设 ID")
    parser.add_argument("--platform", required=True, help="平台")
    parser.add_argument("--title", required=True, help="标题")
    parser.add_argument("--file", required=True, help="源文件路径")
    parser.add_argument("--review-json", default=None, help="评审 JSON 文件路径")
    parser.add_argument("--source-idea", default=None, help="来源灵感 ID")
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"文件不存在: {args.file}", file=sys.stderr)
        sys.exit(1)

    date_str = datetime.now().strftime("%Y%m%d")
    base_slug = _to_slug(args.title)

    # 读取 review 数据
    review_json_str = None
    review_score = None
    if args.review_json:
        try:
            with open(args.review_json, "r", encoding="utf-8") as f:
                review_data = json.load(f)
            review_json_str = json.dumps(review_data, ensure_ascii=False)
            review_score = review_data.get("total")
        except Exception as e:
            print(f"读取 review JSON 失败: {e}", file=sys.stderr)

    conn = None
    content_id = None
    dest_dir = None
    dest_file = None

    try:
        conn = get_connection()

        # 幂等检查：查找同人设同平台同标题的已有记录
        existing = conn.execute(
            "SELECT content_id FROM contents WHERE persona_id=? AND platform=? AND title=? AND content_id LIKE ?",
            (args.persona, args.platform, args.title, f"{args.persona}_{args.platform}_{date_str}_%"),
        ).fetchone()

        if existing:
            # 已存在 → 幂等更新，使用原 content_id
            content_id = existing["content_id"]
        else:
            # 不存在 → 生成唯一 slug
            slug = _unique_slug(conn, args.persona, args.platform, date_str, base_slug)
            content_id = f"{args.persona}_{args.platform}_{date_str}_{slug}"

        dest_dir = os.path.join(DATA_CONTENT_DIR, content_id)
        os.makedirs(dest_dir, exist_ok=True)

        dest_file = os.path.join(dest_dir, "content.md")
        shutil.copy2(args.file, dest_file)

        if existing:
            # 更新
            conn.execute(
                """UPDATE contents SET file_path=?, review_json=?, review_score=?,
                   updated_at=datetime('now','localtime') WHERE content_id=?""",
                (dest_file, review_json_str, review_score, content_id),
            )
            conn.commit()
            print(f"已更新已有记录: {content_id}", file=sys.stderr)
        else:
            # 插入
            conn.execute(
                """INSERT INTO contents
                   (content_id, title, persona_id, platform, status, file_path,
                    review_score, review_json, source_idea)
                   VALUES (?, ?, ?, ?, 'final', ?, ?, ?, ?)""",
                (
                    content_id, args.title, args.persona, args.platform,
                    dest_file, review_score, review_json_str, args.source_idea,
                ),
            )
            conn.execute(
                """INSERT INTO status_log (content_id, from_status, to_status, operator, note)
                   VALUES (?, NULL, 'final', 'archive', '成品归档')""",
                (content_id,),
            )
            # 追加 daily_logs 产出记录
            today = datetime.now().strftime("%Y-%m-%d")
            row = conn.execute("SELECT output FROM daily_logs WHERE date = ?", (today,)).fetchone()
            entry = f"[归档] {args.title} ({content_id})"
            if row:
                old_output = row["output"] or ""
                new_output = (old_output + "\n" + entry).strip()
                conn.execute(
                    "UPDATE daily_logs SET output=?, updated_at=datetime('now','localtime') WHERE date=?",
                    (new_output, today),
                )
            else:
                conn.execute(
                    "INSERT INTO daily_logs (date, output) VALUES (?, ?)",
                    (today, entry),
                )
            conn.commit()
            print(f"归档成功: {content_id}", file=sys.stderr)

        result = {"content_id": content_id, "file_path": dest_file, "status": "final"}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)

    except Exception as e:
        if dest_file and os.path.isfile(dest_file):
            # 文件写入成功但数据库失败
            print(f"数据库操作失败: {e}", file=sys.stderr)
            result = {"content_id": content_id or "unknown", "file_path": dest_file, "status": "file_only"}
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(2)
        else:
            print(f"归档失败: {e}", file=sys.stderr)
            sys.exit(3)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
