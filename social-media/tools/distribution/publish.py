#!/usr/bin/env python3
"""
发布管理 CLI — 管理多账号内容分发

用法:
    python publish.py create --persona chongxiaoyu --title "标题" [--content-path 60_Published/...]
    python publish.py done --id 1 --url "https://..."
    python publish.py list [--persona chongxiaoyu] [--status draft]
    python publish.py accounts [--persona chongxiaoyu]
    python publish.py add-account --persona chongxiaoyu --platform xiaohongshu --name "账号昵称" [--account-id xxx]
"""

import argparse
import sys
from datetime import datetime
from db import get_conn, list_accounts, add_account


# ─── 创建发布任务 ───

def cmd_create(args):
    """为人设下所有活跃账号创建发布记录"""
    conn = get_conn()

    # 验证人设存在
    persona = conn.execute("SELECT * FROM personas WHERE id = ?", (args.persona,)).fetchone()
    if not persona:
        print(f"错误: 人设 '{args.persona}' 不存在")
        sys.exit(1)

    # 获取该人设下所有活跃账号
    accounts = list_accounts(persona_id=args.persona, status="active")
    if not accounts:
        print(f"错误: 人设 '{persona['name']}' 下没有活跃账号")
        print("请先添加账号: python publish.py add-account --persona {} --platform xiaohongshu --name '昵称'".format(args.persona))
        sys.exit(1)

    # 为每个账号创建发布记录
    created = []
    for acc in accounts:
        conn.execute(
            """INSERT INTO publications (content_path, account_id, title, scheduled_at, status)
               VALUES (?, ?, ?, ?, 'draft')""",
            (args.content_path, acc['id'], args.title, args.scheduled_at),
        )
        created.append(acc)
    conn.commit()

    print(f"已为 {persona['name']} 创建 {len(created)} 条发布任务:")
    for acc in created:
        print(f"  [{acc['platform']}] {acc['account_name']}")
    if args.content_path:
        print(f"  内容: {args.content_path}")


# ─── 标记已发布 ───

def cmd_done(args):
    """标记发布记录为已发布"""
    conn = get_conn()
    pub = conn.execute("SELECT * FROM publications WHERE id = ?", (args.id,)).fetchone()
    if not pub:
        print(f"错误: 发布记录 #{args.id} 不存在")
        sys.exit(1)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """UPDATE publications
           SET status = 'published', post_url = ?, published_at = ?
           WHERE id = ?""",
        (args.url, now, args.id),
    )
    conn.commit()
    print(f"已标记 #{args.id} 为已发布")
    if args.url:
        print(f"  链接: {args.url}")


# ─── 列出发布记录 ───

def cmd_list(args):
    """列出发布记录"""
    conn = get_conn()
    sql = """
        SELECT pub.*, a.account_name, a.platform, p.name as persona_name
        FROM publications pub
        JOIN accounts a ON pub.account_id = a.id
        JOIN personas p ON a.persona_id = p.id
        WHERE 1=1
    """
    params = []

    if args.persona:
        sql += " AND p.id = ?"
        params.append(args.persona)
    if args.status:
        sql += " AND pub.status = ?"
        params.append(args.status)
    if args.account_id:
        sql += " AND a.id = ?"
        params.append(args.account_id)

    sql += " ORDER BY pub.created_at DESC"

    if args.limit:
        sql += " LIMIT ?"
        params.append(args.limit)

    rows = conn.execute(sql, params).fetchall()

    if not rows:
        print("没有找到发布记录")
        return

    print(f"共 {len(rows)} 条发布记录:\n")
    for r in rows:
        status_icon = {"draft": "📝", "published": "✅", "tracking": "📊", "archived": "📦"}.get(r['status'], "?")
        print(f"  #{r['id']} {status_icon} [{r['persona_name']}] [{r['platform']}:{r['account_name']}]")
        print(f"     标题: {r['title']}")
        if r['post_url']:
            print(f"     链接: {r['post_url']}")
        if r['published_at']:
            print(f"     发布: {r['published_at']}")
        else:
            print(f"     状态: {r['status']}")
        print()


# ─── 账号管理 ───

def cmd_accounts(args):
    """列出账号"""
    accounts = list_accounts(persona_id=args.persona, status=None)
    if not accounts:
        print("没有找到账号")
        return

    print(f"共 {len(accounts)} 个账号:\n")
    current_persona = None
    for acc in accounts:
        if acc['persona_name'] != current_persona:
            current_persona = acc['persona_name']
            print(f"  {current_persona}:")
        status_icon = "🟢" if acc['status'] == 'active' else "⏸️"
        xhs_id = f" ({acc['account_id']})" if acc['account_id'] else ""
        print(f"    {status_icon} #{acc['id']} [{acc['platform']}] {acc['account_name']}{xhs_id}")
    print()


def cmd_add_account(args):
    """添加账号"""
    add_account(args.persona, args.platform, args.name, args.account_id)
    print(f"已添加账号: [{args.platform}] {args.name} → {args.persona}")


# ─── 主入口 ───

def main():
    parser = argparse.ArgumentParser(description="分发中心 - 发布管理")
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="创建发布任务")
    p_create.add_argument("--persona", "-p", required=True, help="人设 ID")
    p_create.add_argument("--title", "-t", required=True, help="内容标题")
    p_create.add_argument("--content-path", "-c", help="内容文件路径（相对于仓库根目录）")
    p_create.add_argument("--scheduled-at", "-s", help="计划发布时间 (YYYY-MM-DD HH:MM)")

    # done
    p_done = sub.add_parser("done", help="标记已发布")
    p_done.add_argument("--id", "-i", type=int, required=True, help="发布记录 ID")
    p_done.add_argument("--url", "-u", help="发布后的链接")

    # list
    p_list = sub.add_parser("list", help="列出发布记录")
    p_list.add_argument("--persona", "-p", help="按人设筛选")
    p_list.add_argument("--status", "-s", help="按状态筛选 (draft/published/tracking/archived)")
    p_list.add_argument("--account-id", "-a", type=int, help="按账号 ID 筛选")
    p_list.add_argument("--limit", "-n", type=int, default=20, help="最多显示条数")

    # accounts
    p_accounts = sub.add_parser("accounts", help="列出账号")
    p_accounts.add_argument("--persona", "-p", help="按人设筛选")

    # add-account
    p_add = sub.add_parser("add-account", help="添加账号")
    p_add.add_argument("--persona", "-p", required=True, help="人设 ID")
    p_add.add_argument("--platform", default="xiaohongshu", help="平台 (默认 xiaohongshu)")
    p_add.add_argument("--name", "-n", required=True, help="平台昵称")
    p_add.add_argument("--account-id", help="平台号")

    args = parser.parse_args()

    cmds = {
        "create": cmd_create,
        "done": cmd_done,
        "list": cmd_list,
        "accounts": cmd_accounts,
        "add-account": cmd_add_account,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
