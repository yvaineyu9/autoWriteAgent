#!/usr/bin/env python3
"""
发布管理：创建发布任务、标记已发布、查询发布记录、注册人设。
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_connection


def cmd_list(args):
    conn = get_connection()
    try:
        if args.status == "final":
            rows = conn.execute(
                "SELECT content_id, title, persona_id, platform, status, file_path, created_at "
                "FROM contents WHERE status = 'final' ORDER BY created_at DESC"
            ).fetchall()
        else:
            if args.status:
                rows = conn.execute(
                    "SELECT id, content_id, persona_id, platform, status, post_url, published_at, created_at "
                    "FROM publications WHERE status = ? ORDER BY created_at DESC",
                    (args.status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, content_id, persona_id, platform, status, post_url, published_at, created_at "
                    "FROM publications ORDER BY created_at DESC"
                ).fetchall()

        results = [dict(r) for r in rows]

        if args.format == "json":
            print(json.dumps(results, ensure_ascii=False))
        else:
            print(json.dumps(results, ensure_ascii=False, indent=2))

        print(f"共 {len(results)} 条记录", file=sys.stderr)
    finally:
        conn.close()


def cmd_create(args):
    conn = get_connection()
    try:
        # 检查 content 是否存在
        content = conn.execute(
            "SELECT content_id, platform, persona_id FROM contents WHERE content_id = ?",
            (args.content_id,),
        ).fetchone()
        if not content:
            print(f"内容不存在: {args.content_id}", file=sys.stderr)
            sys.exit(1)

        # 插入发布记录
        cursor = conn.execute(
            """INSERT INTO publications (content_id, persona_id, platform, status)
               VALUES (?, ?, ?, 'draft')""",
            (args.content_id, args.persona, content["platform"]),
        )
        pub_id = cursor.lastrowid

        # 更新内容状态
        conn.execute(
            "UPDATE contents SET status='publishing', updated_at=datetime('now','localtime') WHERE content_id=?",
            (args.content_id,),
        )
        conn.execute(
            "INSERT INTO status_log (content_id, from_status, to_status, operator, note) VALUES (?, 'final', 'publishing', 'publish', ?)",
            (args.content_id, f"创建发布任务 #{pub_id}"),
        )
        conn.commit()

        result = {"publication_id": pub_id, "content_id": args.content_id, "status": "draft"}
        print(json.dumps(result, ensure_ascii=False))
        print(f"发布任务已创建: #{pub_id}", file=sys.stderr)
    except Exception as e:
        print(f"创建失败: {e}", file=sys.stderr)
        sys.exit(3)
    finally:
        conn.close()


def cmd_done(args):
    conn = get_connection()
    try:
        pub = conn.execute("SELECT id, content_id FROM publications WHERE id = ?", (args.id,)).fetchone()
        if not pub:
            print(f"发布记录不存在: {args.id}", file=sys.stderr)
            sys.exit(1)

        conn.execute(
            """UPDATE publications
               SET status='published', post_url=?, published_at=datetime('now','localtime')
               WHERE id=?""",
            (args.url, args.id),
        )
        conn.execute(
            "UPDATE contents SET status='published', updated_at=datetime('now','localtime') WHERE content_id=?",
            (pub["content_id"],),
        )
        conn.execute(
            "INSERT INTO status_log (content_id, from_status, to_status, operator, note) VALUES (?, 'publishing', 'published', 'publish', ?)",
            (pub["content_id"], f"已发布: {args.url}"),
        )
        conn.commit()

        result = {"publication_id": args.id, "status": "published", "post_url": args.url}
        print(json.dumps(result, ensure_ascii=False))
        print(f"已标记为已发布: #{args.id}", file=sys.stderr)
    except Exception as e:
        print(f"操作失败: {e}", file=sys.stderr)
        sys.exit(3)
    finally:
        conn.close()


def cmd_add_persona(args):
    conn = get_connection()
    try:
        # 检查是否已存在
        existing = conn.execute("SELECT id FROM personas WHERE id = ?", (args.id,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE personas SET name=?, description=? WHERE id=?",
                (args.name, args.description, args.id),
            )
            print(f"人设已更新: {args.id}", file=sys.stderr)
        else:
            conn.execute(
                "INSERT INTO personas (id, name, description) VALUES (?, ?, ?)",
                (args.id, args.name, args.description),
            )
            print(f"人设已注册: {args.id}", file=sys.stderr)
        conn.commit()

        result = {"persona_id": args.id, "name": args.name}
        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(f"操作失败: {e}", file=sys.stderr)
        sys.exit(3)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="发布管理")
    subparsers = parser.add_subparsers(dest="command")

    # list
    p_list = subparsers.add_parser("list", help="查询发布记录")
    p_list.add_argument("--status", default=None, help="筛选状态")
    p_list.add_argument("--format", default="pretty", choices=["json", "pretty"], help="输出格式")

    # create
    p_create = subparsers.add_parser("create", help="创建发布任务")
    p_create.add_argument("--content-id", required=True, help="内容 ID")
    p_create.add_argument("--persona", required=True, help="人设 ID")
    p_create.add_argument("--title", required=True, help="标题")

    # done
    p_done = subparsers.add_parser("done", help="标记已发布")
    p_done.add_argument("--id", type=int, required=True, help="发布记录 ID")
    p_done.add_argument("--url", required=True, help="发布链接")

    # add-persona
    p_persona = subparsers.add_parser("add-persona", help="注册人设")
    p_persona.add_argument("--id", required=True, help="人设 ID")
    p_persona.add_argument("--name", required=True, help="人设名称")
    p_persona.add_argument("--description", default=None, help="人设描述")

    args = parser.parse_args()

    if not args.command:
        parser.print_help(sys.stderr)
        sys.exit(1)

    dispatch = {
        "list": cmd_list,
        "create": cmd_create,
        "done": cmd_done,
        "add-persona": cmd_add_persona,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
