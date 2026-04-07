#!/usr/bin/env python3
"""
数据采集：记录发布内容的点赞数据，提醒未采集数据的发布记录。
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_connection


def cmd_record(args):
    conn = get_connection()
    try:
        # 验证 publication 存在
        pub = conn.execute("SELECT id FROM publications WHERE id = ?", (args.pub_id,)).fetchone()
        if not pub:
            print(f"发布记录不存在: {args.pub_id}", file=sys.stderr)
            sys.exit(1)

        conn.execute(
            """INSERT INTO metrics (publication_id, views, likes, collects, comments, shares)
               VALUES (?, 0, ?, 0, 0, 0)""",
            (args.pub_id, args.likes),
        )
        conn.commit()

        result = {
            "publication_id": args.pub_id,
            "likes": args.likes,
        }
        print(json.dumps(result, ensure_ascii=False))
        print(f"数据已记录: publication #{args.pub_id}", file=sys.stderr)
    except Exception as e:
        print(f"记录失败: {e}", file=sys.stderr)
        sys.exit(3)
    finally:
        conn.close()


def cmd_remind(args):
    conn = get_connection()
    try:
        # 查找 published 但 7 天内未采集数据的发布记录
        rows = conn.execute(
            """SELECT p.id, p.content_id, p.persona_id, p.platform, p.published_at
               FROM publications p
               WHERE p.status = 'published'
               AND NOT EXISTS (
                   SELECT 1 FROM metrics m
                   WHERE m.publication_id = p.id
                   AND m.captured_at >= datetime('now', '-7 days', 'localtime')
               )
               ORDER BY p.published_at DESC""",
        ).fetchall()

        results = [dict(r) for r in rows]
        print(json.dumps(results, ensure_ascii=False))
        if results:
            print(f"有 {len(results)} 条发布记录需要采集数据", file=sys.stderr)
        else:
            print("所有发布记录数据均已采集", file=sys.stderr)
    except Exception as e:
        print(f"查询失败: {e}", file=sys.stderr)
        sys.exit(3)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="数据采集")
    subparsers = parser.add_subparsers(dest="command")

    # record
    p_record = subparsers.add_parser("record", help="记录点赞数据")
    p_record.add_argument("--pub-id", type=int, required=True, help="发布记录 ID")
    p_record.add_argument("--likes", type=int, required=True, help="点赞数")

    # remind
    subparsers.add_parser("remind", help="查找未采集数据的发布记录")

    args = parser.parse_args()

    if not args.command:
        parser.print_help(sys.stderr)
        sys.exit(1)

    dispatch = {
        "record": cmd_record,
        "remind": cmd_remind,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
