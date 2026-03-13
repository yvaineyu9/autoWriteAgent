#!/usr/bin/env python3
"""
数据采集 CLI — 发布后数据追踪

用法:
    python metrics.py record --pub-id 1 --views 500 --likes 30 --collects 15 --comments 5 --shares 2
    python metrics.py remind                          # 列出需要采集数据的帖子
    python metrics.py query [--persona chongxiaoyu]   # 查询数据汇总
    python metrics.py history --pub-id 1              # 查看某条发布的数据变化
"""

import argparse
import sys
from datetime import datetime, timedelta
from db import get_conn


# ─── 录入数据快照 ───

def cmd_record(args):
    """录入一条数据快照"""
    conn = get_conn()

    pub = conn.execute("SELECT * FROM publications WHERE id = ?", (args.pub_id,)).fetchone()
    if not pub:
        print(f"错误: 发布记录 #{args.pub_id} 不存在")
        sys.exit(1)

    if pub['status'] == 'draft':
        print(f"错误: #{args.pub_id} 还未发布，请先标记为已发布")
        sys.exit(1)

    # 如果是 published 状态，自动转为 tracking
    if pub['status'] == 'published':
        conn.execute("UPDATE publications SET status = 'tracking' WHERE id = ?", (args.pub_id,))

    conn.execute(
        """INSERT INTO metrics (publication_id, views, likes, collects, comments, shares, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (args.pub_id, args.views, args.likes, args.collects, args.comments, args.shares, args.notes),
    )
    conn.commit()

    print(f"已录入 #{args.pub_id} 的数据快照:")
    print(f"  阅读 {args.views} | 点赞 {args.likes} | 收藏 {args.collects} | 评论 {args.comments} | 分享 {args.shares}")
    if args.notes:
        print(f"  备注: {args.notes}")


# ─── 提醒采集 ───

def cmd_remind(args):
    """列出需要采集数据的帖子（发布后 1/3/7 天未采集的）"""
    conn = get_conn()
    now = datetime.now()

    # 查找所有已发布但未归档的帖子
    pubs = conn.execute("""
        SELECT pub.*, a.account_name, a.platform, p.name as persona_name
        FROM publications pub
        JOIN accounts a ON pub.account_id = a.id
        JOIN personas p ON a.persona_id = p.id
        WHERE pub.status IN ('published', 'tracking')
          AND pub.published_at IS NOT NULL
        ORDER BY pub.published_at DESC
    """).fetchall()

    if not pubs:
        print("没有需要采集数据的帖子")
        return

    check_days = [1, 3, 7]
    needs_collection = []

    for pub in pubs:
        pub_time = datetime.strptime(pub['published_at'], "%Y-%m-%d %H:%M:%S")
        days_since = (now - pub_time).days

        # 查找已有的采集记录
        existing = conn.execute(
            "SELECT captured_at FROM metrics WHERE publication_id = ? ORDER BY captured_at",
            (pub['id'],)
        ).fetchall()
        collection_count = len(existing)

        # 判断是否需要采集
        for i, day in enumerate(check_days):
            if days_since >= day and collection_count <= i:
                needs_collection.append({
                    "pub": pub,
                    "days_since": days_since,
                    "check_day": day,
                    "collection_count": collection_count,
                })
                break

        # 超过 7 天且已采集 3 次的，自动归档
        if days_since > 7 and collection_count >= 3:
            conn.execute("UPDATE publications SET status = 'archived' WHERE id = ?", (pub['id'],))

    conn.commit()

    if not needs_collection:
        print("所有帖子数据已是最新，无需采集")
        return

    print(f"有 {len(needs_collection)} 条帖子需要采集数据:\n")
    for item in needs_collection:
        pub = item['pub']
        print(f"  #{pub['id']} [{pub['persona_name']}] [{pub['platform']}:{pub['account_name']}]")
        print(f"     标题: {pub['title']}")
        print(f"     发布于: {pub['published_at']} ({item['days_since']} 天前)")
        print(f"     应采集第 {item['collection_count'] + 1} 次 (第 {item['check_day']} 天)")
        if pub['post_url']:
            print(f"     链接: {pub['post_url']}")
        print()

    print("录入命令示例:")
    first = needs_collection[0]['pub']
    print(f"  python metrics.py record --pub-id {first['id']} --views 0 --likes 0 --collects 0 --comments 0 --shares 0")


# ─── 查询数据汇总 ───

def cmd_query(args):
    """查询数据汇总"""
    conn = get_conn()

    sql = """
        SELECT
            p.name as persona_name,
            a.account_name,
            a.platform,
            pub.id as pub_id,
            pub.title,
            pub.published_at,
            pub.status,
            pub.post_url,
            COALESCE(m.latest_views, 0) as views,
            COALESCE(m.latest_likes, 0) as likes,
            COALESCE(m.latest_collects, 0) as collects,
            COALESCE(m.latest_comments, 0) as comments,
            COALESCE(m.latest_shares, 0) as shares,
            m.collection_count
        FROM publications pub
        JOIN accounts a ON pub.account_id = a.id
        JOIN personas p ON a.persona_id = p.id
        LEFT JOIN (
            SELECT
                publication_id,
                COUNT(*) as collection_count,
                MAX(views) as latest_views,
                MAX(likes) as latest_likes,
                MAX(collects) as latest_collects,
                MAX(comments) as latest_comments,
                MAX(shares) as latest_shares
            FROM metrics
            GROUP BY publication_id
        ) m ON m.publication_id = pub.id
        WHERE pub.status IN ('published', 'tracking', 'archived')
    """
    params = []

    if args.persona:
        sql += " AND p.id = ?"
        params.append(args.persona)
    if args.account_id:
        sql += " AND a.id = ?"
        params.append(args.account_id)

    sql += " ORDER BY pub.published_at DESC"

    if args.limit:
        sql += " LIMIT ?"
        params.append(args.limit)

    rows = conn.execute(sql, params).fetchall()

    if not rows:
        print("没有数据")
        return

    # 汇总
    total_views = sum(r['views'] for r in rows)
    total_likes = sum(r['likes'] for r in rows)
    total_collects = sum(r['collects'] for r in rows)

    print(f"数据汇总 ({len(rows)} 条内容):\n")
    print(f"  总阅读: {total_views} | 总点赞: {total_likes} | 总收藏: {total_collects}\n")

    for r in rows:
        engagement = r['likes'] + r['collects'] + r['comments'] + r['shares']
        engagement_rate = f"{engagement / r['views'] * 100:.1f}%" if r['views'] > 0 else "-"
        collected = f"({r['collection_count']}次采集)" if r['collection_count'] else "(未采集)"

        print(f"  #{r['pub_id']} [{r['persona_name']}:{r['account_name']}]")
        print(f"     {r['title']}")
        print(f"     👁 {r['views']} | 👍 {r['likes']} | ⭐ {r['collects']} | 💬 {r['comments']} | 🔄 {r['shares']} | 互动率 {engagement_rate} {collected}")
        if r['published_at']:
            print(f"     发布: {r['published_at']}")
        print()


# ─── 查看某条发布的数据变化 ───

def cmd_history(args):
    """查看某条发布记录的数据采集历史"""
    conn = get_conn()

    pub = conn.execute("""
        SELECT pub.*, a.account_name, a.platform, p.name as persona_name
        FROM publications pub
        JOIN accounts a ON pub.account_id = a.id
        JOIN personas p ON a.persona_id = p.id
        WHERE pub.id = ?
    """, (args.pub_id,)).fetchone()

    if not pub:
        print(f"错误: 发布记录 #{args.pub_id} 不存在")
        sys.exit(1)

    snapshots = conn.execute(
        "SELECT * FROM metrics WHERE publication_id = ? ORDER BY captured_at",
        (args.pub_id,)
    ).fetchall()

    print(f"#{pub['id']} [{pub['persona_name']}:{pub['account_name']}]")
    print(f"  标题: {pub['title']}")
    print(f"  发布: {pub['published_at']}")
    if pub['post_url']:
        print(f"  链接: {pub['post_url']}")
    print()

    if not snapshots:
        print("  暂无数据采集记录")
        return

    print(f"  数据变化 ({len(snapshots)} 次采集):")
    print(f"  {'采集时间':<20} {'阅读':>6} {'点赞':>6} {'收藏':>6} {'评论':>6} {'分享':>6}")
    print(f"  {'-'*62}")

    for s in snapshots:
        print(f"  {s['captured_at']:<20} {s['views']:>6} {s['likes']:>6} {s['collects']:>6} {s['comments']:>6} {s['shares']:>6}")
        if s['notes']:
            print(f"  {'':>20} 备注: {s['notes']}")


# ─── 主入口 ───

def main():
    parser = argparse.ArgumentParser(description="分发中心 - 数据采集")
    sub = parser.add_subparsers(dest="command", required=True)

    # record
    p_rec = sub.add_parser("record", help="录入数据快照")
    p_rec.add_argument("--pub-id", type=int, required=True, help="发布记录 ID")
    p_rec.add_argument("--views", type=int, default=0, help="阅读数")
    p_rec.add_argument("--likes", type=int, default=0, help="点赞数")
    p_rec.add_argument("--collects", type=int, default=0, help="收藏数")
    p_rec.add_argument("--comments", type=int, default=0, help="评论数")
    p_rec.add_argument("--shares", type=int, default=0, help="分享数")
    p_rec.add_argument("--notes", help="备注")

    # remind
    sub.add_parser("remind", help="列出需要采集数据的帖子")

    # query
    p_query = sub.add_parser("query", help="查询数据汇总")
    p_query.add_argument("--persona", "-p", help="按人设筛选")
    p_query.add_argument("--account-id", "-a", type=int, help="按账号 ID 筛选")
    p_query.add_argument("--limit", "-n", type=int, default=20, help="最多显示条数")

    # history
    p_hist = sub.add_parser("history", help="查看某条发布的数据变化")
    p_hist.add_argument("--pub-id", type=int, required=True, help="发布记录 ID")

    args = parser.parse_args()

    cmds = {
        "record": cmd_record,
        "remind": cmd_remind,
        "query": cmd_query,
        "history": cmd_history,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
