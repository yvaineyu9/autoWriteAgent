#!/usr/bin/env python3
"""
执行痕迹：记录和查询任务执行过程。
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_connection


def cmd_start(args):
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO traces (task_id, event_type, message) VALUES (?, 'start', ?)",
            (args.task_id, json.dumps({"type": args.type, "summary": args.summary}, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()
        print(json.dumps({"task_id": args.task_id, "event": "start"}))
        print(f"任务开始: {args.task_id}", file=sys.stderr)
    except Exception as e:
        print(f"记录失败: {e}", file=sys.stderr)


def cmd_log(args):
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO traces (task_id, event_type, message) VALUES (?, 'log', ?)",
            (args.task_id, args.message),
        )
        conn.commit()
        conn.close()
        print(json.dumps({"task_id": args.task_id, "event": "log"}))
    except Exception as e:
        print(f"记录失败: {e}", file=sys.stderr)


def cmd_fail(args):
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO traces (task_id, event_type, message) VALUES (?, 'fail', ?)",
            (args.task_id, args.reason),
        )
        conn.commit()
        conn.close()
        print(json.dumps({"task_id": args.task_id, "event": "fail"}))
        print(f"任务失败: {args.task_id} - {args.reason}", file=sys.stderr)
    except Exception as e:
        print(f"记录失败: {e}", file=sys.stderr)


def cmd_end(args):
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO traces (task_id, event_type, message) VALUES (?, 'end', ?)",
            (args.task_id, json.dumps({"status": args.status, "summary": args.summary}, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()
        print(json.dumps({"task_id": args.task_id, "event": "end", "status": args.status}))
        print(f"任务结束: {args.task_id} ({args.status})", file=sys.stderr)
    except Exception as e:
        print(f"记录失败: {e}", file=sys.stderr)


def cmd_show(args):
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, task_id, event_type, message, created_at FROM traces WHERE task_id = ? ORDER BY id",
            (args.task_id,),
        ).fetchall()
        conn.close()
        events = [dict(r) for r in rows]
        print(json.dumps({"task_id": args.task_id, "events": events}, ensure_ascii=False))
        if not events:
            print(f"未找到任务: {args.task_id}", file=sys.stderr)
    except Exception as e:
        print(f"查询失败: {e}", file=sys.stderr)
        print(json.dumps({"task_id": args.task_id, "events": [], "error": str(e)}))


def main():
    parser = argparse.ArgumentParser(description="执行痕迹")
    subparsers = parser.add_subparsers(dest="command")

    # start
    p_start = subparsers.add_parser("start", help="记录任务开始")
    p_start.add_argument("task_id", help="任务 ID")
    p_start.add_argument("type", help="任务类型")
    p_start.add_argument("summary", help="任务摘要")

    # log
    p_log = subparsers.add_parser("log", help="记录日志")
    p_log.add_argument("task_id", help="任务 ID")
    p_log.add_argument("message", help="日志消息")

    # fail
    p_fail = subparsers.add_parser("fail", help="记录失败")
    p_fail.add_argument("task_id", help="任务 ID")
    p_fail.add_argument("reason", help="失败原因")

    # end
    p_end = subparsers.add_parser("end", help="记录结束")
    p_end.add_argument("task_id", help="任务 ID")
    p_end.add_argument("status", help="结束状态")
    p_end.add_argument("summary", help="结束摘要")

    # show
    p_show = subparsers.add_parser("show", help="查看任务痕迹")
    p_show.add_argument("task_id", help="任务 ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help(sys.stderr)
        sys.exit(1)

    dispatch = {
        "start": cmd_start,
        "log": cmd_log,
        "fail": cmd_fail,
        "end": cmd_end,
        "show": cmd_show,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
