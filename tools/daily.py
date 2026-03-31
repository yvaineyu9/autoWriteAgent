#!/usr/bin/env python3
"""
每日记录：日记的读写和产出统计。
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_connection


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _resolve_date(date_arg: str) -> str:
    if not date_arg or date_arg == "today":
        return _today()
    if date_arg == "yesterday":
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    return date_arg


def cmd_read(args):
    date = _resolve_date(args.date)
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT date, plan, output, notes, created_at, updated_at FROM daily_logs WHERE date = ?",
            (date,),
        ).fetchone()
        if row:
            result = dict(row)
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(json.dumps({"date": date, "plan": None, "output": None, "notes": None}))
            print(f"未找到 {date} 的日记", file=sys.stderr)
    finally:
        conn.close()


def cmd_write(args):
    today = _today()
    conn = get_connection()
    try:
        existing = conn.execute("SELECT date FROM daily_logs WHERE date = ?", (today,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE daily_logs SET plan=?, updated_at=datetime('now','localtime') WHERE date=?",
                (args.plan, today),
            )
        else:
            conn.execute(
                "INSERT INTO daily_logs (date, plan) VALUES (?, ?)",
                (today, args.plan),
            )
        conn.commit()
        print(f"今日计划已写入: {today}", file=sys.stderr)

        row = conn.execute(
            "SELECT date, plan, output, notes FROM daily_logs WHERE date = ?", (today,)
        ).fetchone()
        print(json.dumps(dict(row), ensure_ascii=False))
    finally:
        conn.close()


def cmd_append(args):
    today = _today()
    message = args.message
    conn = get_connection()
    try:
        row = conn.execute("SELECT output FROM daily_logs WHERE date = ?", (today,)).fetchone()
        if row:
            old_output = row["output"] or ""
            new_output = (old_output + "\n" + message).strip()
            conn.execute(
                "UPDATE daily_logs SET output=?, updated_at=datetime('now','localtime') WHERE date=?",
                (new_output, today),
            )
        else:
            conn.execute(
                "INSERT INTO daily_logs (date, output) VALUES (?, ?)",
                (today, message),
            )
        conn.commit()
        print(f"已追加产出记录", file=sys.stderr)
        print(json.dumps({"date": today, "appended": message}))
    finally:
        conn.close()


def cmd_summary(args):
    conn = get_connection()
    try:
        # 活跃内容（非 final 非 archived）
        active = conn.execute(
            "SELECT COUNT(*) as cnt FROM contents WHERE status NOT IN ('final', 'archived', 'published')"
        ).fetchone()["cnt"]

        # 待处理灵感
        pending = conn.execute(
            "SELECT COUNT(*) as cnt FROM ideas WHERE status = 'pending'"
        ).fetchone()["cnt"]

        # 最近产出（最近 7 天的 daily_logs output）
        seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT date, output FROM daily_logs WHERE date >= ? AND output IS NOT NULL ORDER BY date DESC",
            (seven_days_ago,),
        ).fetchall()
        recent_outputs = [{"date": r["date"], "output": r["output"]} for r in rows]

        result = {
            "active_contents": active,
            "pending_ideas": pending,
            "recent_outputs": recent_outputs,
        }
        print(json.dumps(result, ensure_ascii=False))
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="每日记录")
    subparsers = parser.add_subparsers(dest="command")

    # read
    p_read = subparsers.add_parser("read", help="读取日记")
    p_read.add_argument("date", nargs="?", default="today", help="日期（YYYY-MM-DD / yesterday / today）")

    # write
    p_write = subparsers.add_parser("write", help="写入今日计划")
    p_write.add_argument("--plan", required=True, help="计划内容")

    # append
    p_append = subparsers.add_parser("append", help="追加产出记录")
    p_append.add_argument("message", help="产出消息")

    # summary
    subparsers.add_parser("summary", help="产出统计")

    args = parser.parse_args()

    if not args.command:
        parser.print_help(sys.stderr)
        sys.exit(1)

    try:
        {"read": cmd_read, "write": cmd_write, "append": cmd_append, "summary": cmd_summary}[args.command](args)
    except Exception as e:
        print(f"操作失败: {e}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
