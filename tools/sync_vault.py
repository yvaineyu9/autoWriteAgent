#!/usr/bin/env python3
"""
Vault 同步脚本：从 data/ 单向生成 Obsidian 只读视图。

用法：
  python tools/sync_vault.py [--vault-path <path>]

默认 vault 路径从 .env 的 VAULT_PATH 读取，或用命令行参数指定。
每次执行会完整重建 vault 内容（.obsidian/ 目录除外）。
"""

import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_connection, PROJECT_ROOT

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DATA_CONTENT_DIR = os.path.join(DATA_DIR, "content")
KNOWLEDGE_DIR = os.path.join(DATA_DIR, "knowledge")

# 平台 slug → 中文显示名
PLATFORM_NAMES = {
    "xiaohongshu": "小红书",
    "wechat": "微信公众号",
    "twitter": "Twitter",
    "podcast": "播客",
}

# 人设 ID → 中文显示名
PERSONA_NAMES = {
    "yuejian": "月见",
    "chongxiaoyu": "虫小宇",
}


def _get_vault_path(cli_path=None):
    """获取 vault 路径：CLI 参数 > .env > 默认。"""
    if cli_path:
        return os.path.expanduser(cli_path)

    env_file = os.path.join(PROJECT_ROOT, ".env")
    if os.path.isfile(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("VAULT_PATH="):
                    return os.path.expanduser(line.split("=", 1)[1].strip().strip('"').strip("'"))

    return os.path.expanduser("~/.openclaw/workspace/vault")


def _clean_vault(vault_path):
    """清空 vault 中除 .obsidian/ 外的所有内容。"""
    for item in os.listdir(vault_path):
        if item in (".obsidian", ".DS_Store"):
            continue
        path = os.path.join(vault_path, item)
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)


def _truncate_title(title, max_len=20):
    """截断标题用于目录名。"""
    # 去掉文件名不安全字符
    safe = re.sub(r'[/\\:*?"<>|]', "", title)
    return safe[:max_len] if len(safe) > max_len else safe


def sync_ideas(conn, vault_path):
    """同步灵感素材到 vault/10_灵感/。"""
    dest_dir = os.path.join(vault_path, "10_灵感")
    os.makedirs(dest_dir, exist_ok=True)

    rows = conn.execute(
        "SELECT id, title, tags, source, status, file_path, created_at FROM ideas ORDER BY created_at DESC"
    ).fetchall()

    for r in rows:
        idea_id = r["id"]
        title = r["title"]
        tags = r["tags"] or "[]"
        source = r["source"]
        status = r["status"]
        file_path = r["file_path"]
        created_at = r["created_at"]

        # 读取正文
        abs_path = os.path.join(DATA_CONTENT_DIR, file_path)
        body = ""
        if os.path.isfile(abs_path):
            with open(abs_path, "r", encoding="utf-8") as f:
                body = f.read()

        # 写入 vault（用标题命名，方便浏览）
        safe_title = _truncate_title(title, 40)
        dest_file = os.path.join(dest_dir, f"{safe_title}.md")

        # 避免重名
        if os.path.exists(dest_file):
            dest_file = os.path.join(dest_dir, f"{safe_title}_{idea_id[:8]}.md")

        frontmatter = f"""---
id: "{idea_id}"
title: "{title}"
tags: {tags}
source: "{source}"
status: "{status}"
created_at: "{created_at}"
---"""

        with open(dest_file, "w", encoding="utf-8") as f:
            f.write(frontmatter + "\n\n" + body)

    return len(rows)


def sync_contents(conn, vault_path):
    """同步成品内容到 vault/20_内容/<persona>/<platform>/。"""
    dest_base = os.path.join(vault_path, "20_内容")
    os.makedirs(dest_base, exist_ok=True)

    rows = conn.execute(
        """SELECT c.content_id, c.title, c.persona_id, c.platform, c.status,
                  c.file_path, c.review_score, c.source_idea, c.created_at,
                  p.post_url, p.published_at, p.platform_status,
                  p.platform_checked_at, p.platform_failure_reason,
                  p.id as pub_id
           FROM contents c
           LEFT JOIN publications p ON p.content_id = c.content_id
               AND p.id = (SELECT MAX(id) FROM publications WHERE content_id = c.content_id)
           ORDER BY c.created_at DESC"""
    ).fetchall()

    for r in rows:
        content_id = r["content_id"]
        title = r["title"]
        persona = r["persona_id"]
        platform = r["platform"]
        status = r["status"]
        file_path = r["file_path"]
        review_score = r["review_score"]
        source_idea = r["source_idea"]
        created_at = r["created_at"]
        post_url = r["post_url"]
        published_at = r["published_at"]
        platform_status = r["platform_status"]
        platform_checked_at = r["platform_checked_at"]
        platform_failure_reason = r["platform_failure_reason"]
        pub_id = r["pub_id"]

        # 读取正文
        abs_path = os.path.join(DATA_CONTENT_DIR, file_path)
        body = ""
        if os.path.isfile(abs_path):
            with open(abs_path, "r", encoding="utf-8") as f:
                body = f.read()

        # 获取最新 metrics
        metrics_line = ""
        if pub_id:
            m = conn.execute(
                """SELECT likes, captured_at
                   FROM metrics WHERE publication_id = ?
                   ORDER BY captured_at DESC LIMIT 1""",
                (pub_id,),
            ).fetchone()
            if m:
                metrics_line = (
                    f'likes: {m["likes"]}\n'
                    f'metrics_captured_at: "{m["captured_at"]}"'
                )

        # 从 content_id 提取日期部分
        date_match = re.search(r"_(\d{8})_", content_id)
        date_prefix = date_match.group(1) if date_match else "00000000"
        safe_title = _truncate_title(title, 30)

        # 目录结构：20_内容/<persona>/<platform>/<YYYYMMDD_标题>/
        dir_name = f"{date_prefix}_{safe_title}"
        dest_dir = os.path.join(dest_base, persona, platform, dir_name)
        os.makedirs(dest_dir, exist_ok=True)

        # 构建 frontmatter
        fm_lines = [
            "---",
            f'content_id: "{content_id}"',
            f'title: "{title}"',
            f'persona: "{persona}"',
            f'persona_name: "{PERSONA_NAMES.get(persona, persona)}"',
            f'platform: "{platform}"',
            f'platform_name: "{PLATFORM_NAMES.get(platform, platform)}"',
            f'status: "{status}"',
        ]
        if review_score is not None:
            fm_lines.append(f"review_score: {review_score}")
        if source_idea:
            fm_lines.append(f'source_idea: "{source_idea}"')
        fm_lines.append(f'created_at: "{created_at}"')
        if post_url:
            fm_lines.append(f'post_url: "{post_url}"')
        if published_at:
            fm_lines.append(f'published_at: "{published_at}"')
        if platform_status:
            fm_lines.append(f'platform_status: "{platform_status}"')
        if platform_checked_at:
            fm_lines.append(f'platform_checked_at: "{platform_checked_at}"')
        if platform_failure_reason:
            fm_lines.append(f'platform_failure_reason: "{platform_failure_reason}"')
        if metrics_line:
            fm_lines.append(metrics_line)
        fm_lines.append("---")

        dest_file = os.path.join(dest_dir, "content.md")
        with open(dest_file, "w", encoding="utf-8") as f:
            f.write("\n".join(fm_lines) + "\n\n" + body)

        # 复制附件
        src_dir = os.path.join(DATA_CONTENT_DIR, content_id)
        if os.path.isdir(src_dir):
            for fname in os.listdir(src_dir):
                if fname == "content.md":
                    continue
                src = os.path.join(src_dir, fname)
                dst = os.path.join(dest_dir, fname)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)

    return len(rows)


def sync_knowledge(vault_path):
    """同步知识库到 vault/30_知识库/。"""
    dest_base = os.path.join(vault_path, "30_知识库")
    count = 0

    for subdir in ("wiki", "research"):
        src = os.path.join(KNOWLEDGE_DIR, subdir)
        dst = os.path.join(dest_base, subdir)
        if not os.path.isdir(src):
            continue

        os.makedirs(dst, exist_ok=True)
        for item in os.listdir(src):
            s = os.path.join(src, item)
            d = os.path.join(dst, item)
            if os.path.isfile(s):
                shutil.copy2(s, d)
                count += 1
            elif os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
                count += 1

    return count


def sync_daily(conn, vault_path):
    """同步日记到 vault/40_日记/。"""
    dest_dir = os.path.join(vault_path, "40_日记")
    os.makedirs(dest_dir, exist_ok=True)

    rows = conn.execute(
        "SELECT date, plan, output, notes FROM daily_logs ORDER BY date DESC"
    ).fetchall()

    for r in rows:
        date = r["date"]
        plan = r["plan"] or ""
        output = r["output"] or ""
        notes = r["notes"] or ""

        content = f"""---
date: "{date}"
---

# {date}

## 今日计划
{plan}

## 产出记录
{output}

## 随想
{notes}
"""
        dest_file = os.path.join(dest_dir, f"{date}.md")
        with open(dest_file, "w", encoding="utf-8") as f:
            f.write(content)

    return len(rows)


def _gen_dashboard_overview(conn, vault_path):
    """生成内容总览看板。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows = conn.execute(
        """SELECT c.content_id, c.title, c.persona_id, c.platform, c.status,
                  c.review_score, c.created_at,
                  p.post_url, p.published_at
           FROM contents c
           LEFT JOIN publications p ON p.content_id = c.content_id
               AND p.id = (SELECT MAX(id) FROM publications WHERE content_id = c.content_id)
           ORDER BY c.created_at DESC"""
    ).fetchall()

    # 按状态分组
    groups = {}
    for r in rows:
        status = r["status"]
        if status not in groups:
            groups[status] = []
        groups[status].append(r)

    lines = [
        f"# 内容总览",
        f"",
        f"> 自动生成于 {now}，请勿手动编辑",
        f"",
    ]

    # 统计
    total = len(rows)
    lines.append("## 统计\n")
    for s in ["published", "final", "publishing", "draft", "revising", "archived"]:
        if s in groups:
            lines.append(f"- **{s}**: {len(groups[s])} 篇")
    lines.append(f"- **总计**: {total} 篇")
    lines.append("")

    # 按状态输出表格
    status_order = ["publishing", "final", "published", "draft", "revising", "archived"]
    status_labels = {
        "published": "已发布",
        "final": "待发布（定稿）",
        "publishing": "发布中",
        "draft": "草稿",
        "revising": "修改中",
        "archived": "已归档",
    }

    for status in status_order:
        items = groups.get(status, [])
        if not items:
            continue

        label = status_labels.get(status, status)
        lines.append(f"## {label}（{len(items)} 篇）\n")

        if status == "published":
            lines.append("| 内容 | 人设 | 平台 | 评分 | 发布日期 | 链接 |")
            lines.append("|------|------|------|------|---------|------|")
            for r in items:
                persona_name = PERSONA_NAMES.get(r["persona_id"], r["persona_id"])
                platform_name = PLATFORM_NAMES.get(r["platform"], r["platform"])
                score = r["review_score"] if r["review_score"] else "-"
                pub_date = (r["published_at"] or "")[:10]
                # 生成 vault 内链接
                date_match = re.search(r"_(\d{8})_", r["content_id"])
                date_prefix = date_match.group(1) if date_match else ""
                safe_title = _truncate_title(r["title"], 30)
                link_path = f'20_内容/{r["persona_id"]}/{r["platform"]}/{date_prefix}_{safe_title}/content'
                link = f'[[{link_path}|{r["title"][:25]}]]'
                url = f'[链接]({r["post_url"]})' if r["post_url"] else "-"
                lines.append(f"| {link} | {persona_name} | {platform_name} | {score} | {pub_date} | {url} |")
        else:
            lines.append("| 内容 | 人设 | 平台 | 评分 | 创建日期 |")
            lines.append("|------|------|------|------|---------|")
            for r in items:
                persona_name = PERSONA_NAMES.get(r["persona_id"], r["persona_id"])
                platform_name = PLATFORM_NAMES.get(r["platform"], r["platform"])
                score = r["review_score"] if r["review_score"] else "-"
                date = (r["created_at"] or "")[:10]
                date_match = re.search(r"_(\d{8})_", r["content_id"])
                date_prefix = date_match.group(1) if date_match else ""
                safe_title = _truncate_title(r["title"], 30)
                link_path = f'20_内容/{r["persona_id"]}/{r["platform"]}/{date_prefix}_{safe_title}/content'
                link = f'[[{link_path}|{r["title"][:25]}]]'
                lines.append(f"| {link} | {persona_name} | {platform_name} | {score} | {date} |")

        lines.append("")

    return "\n".join(lines)


def _gen_dashboard_ideas(conn, vault_path):
    """生成灵感池看板。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows = conn.execute(
        "SELECT id, title, tags, source, status, created_at FROM ideas ORDER BY created_at DESC"
    ).fetchall()

    groups = {}
    for r in rows:
        s = r["status"]
        if s not in groups:
            groups[s] = []
        groups[s].append(r)

    lines = [
        "# 灵感池",
        "",
        f"> 自动生成于 {now}，请勿手动编辑",
        "",
        "## 统计\n",
    ]

    for s in ["pending", "used", "archived"]:
        lines.append(f"- **{s}**: {len(groups.get(s, []))} 条")
    lines.append(f"- **总计**: {len(rows)} 条\n")

    status_labels = {"pending": "待使用", "used": "已使用", "archived": "已归档"}
    for status in ["pending", "used", "archived"]:
        items = groups.get(status, [])
        if not items:
            continue

        label = status_labels.get(status, status)
        lines.append(f"## {label}（{len(items)} 条）\n")
        lines.append("| 灵感 | 标签 | 来源 | 日期 |")
        lines.append("|------|------|------|------|")
        for r in items:
            safe_title = _truncate_title(r["title"], 40)
            link = f"[[10_灵感/{safe_title}|{r['title'][:30]}]]"
            tags = r["tags"] or "[]"
            try:
                tag_list = json.loads(tags)
                tags_display = ", ".join(tag_list) if isinstance(tag_list, list) else tags
            except json.JSONDecodeError:
                tags_display = tags
            date = (r["created_at"] or "")[:10]
            lines.append(f"| {link} | {tags_display} | {r['source']} | {date} |")
        lines.append("")

    return "\n".join(lines)


def _gen_dashboard_publish(conn, vault_path):
    """生成发布追踪看板。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows = conn.execute(
        """SELECT p.id as pub_id, p.content_id, p.persona_id, p.platform,
                  p.status, p.post_url, p.published_at,
                  c.title, c.review_score
           FROM publications p
           LEFT JOIN contents c ON c.content_id = p.content_id
           ORDER BY p.published_at DESC NULLS LAST, p.id DESC"""
    ).fetchall()

    lines = [
        "# 发布追踪",
        "",
        f"> 自动生成于 {now}，请勿手动编辑",
        "",
    ]

    # 需要采集 metrics 的
    needs_metrics = []
    for r in rows:
        if r["status"] == "published" and r["published_at"]:
            m = conn.execute(
                "SELECT COUNT(*) as cnt FROM metrics WHERE publication_id = ?",
                (r["pub_id"],),
            ).fetchone()
            if m["cnt"] == 0:
                needs_metrics.append(r)

    if needs_metrics:
        lines.append(f"## 待采集 Metrics（{len(needs_metrics)} 条）\n")
        lines.append("| 内容 | 人设 | 发布日期 | 状态 |")
        lines.append("|------|------|---------|------|")
        for r in needs_metrics:
            title = r["title"] or r["content_id"]
            persona_name = PERSONA_NAMES.get(r["persona_id"], r["persona_id"])
            pub_date = (r["published_at"] or "")[:10]
            lines.append(f"| {title[:30]} | {persona_name} | {pub_date} | 需补采 |")
        lines.append("")

    # 已发布（含 metrics）
    published = [r for r in rows if r["status"] == "published"]
    if published:
        lines.append(f"## 已发布（{len(published)} 条）\n")
        lines.append("| 内容 | 人设 | 平台 | 发布日期 | 点赞 |")
        lines.append("|------|------|------|---------|------|")
        for r in published:
            title = r["title"] or r["content_id"]
            persona_name = PERSONA_NAMES.get(r["persona_id"], r["persona_id"])
            platform_name = PLATFORM_NAMES.get(r["platform"], r["platform"])
            pub_date = (r["published_at"] or "")[:10]

            m = conn.execute(
                """SELECT likes
                   FROM metrics WHERE publication_id = ?
                   ORDER BY captured_at DESC LIMIT 1""",
                (r["pub_id"],),
            ).fetchone()

            likes = m["likes"] if m else "-"
            lines.append(f"| {title[:25]} | {persona_name} | {platform_name} | {pub_date} | {likes} |")
        lines.append("")

    # 待发布
    draft = [r for r in rows if r["status"] == "draft"]
    if draft:
        lines.append(f"## 待发布（{len(draft)} 条）\n")
        lines.append("| 内容 | 人设 | 平台 |")
        lines.append("|------|------|------|")
        for r in draft:
            title = r["title"] or r["content_id"]
            persona_name = PERSONA_NAMES.get(r["persona_id"], r["persona_id"])
            platform_name = PLATFORM_NAMES.get(r["platform"], r["platform"])
            lines.append(f"| {title[:30]} | {persona_name} | {platform_name} |")
        lines.append("")

    # 人设汇总
    lines.append("## 人设汇总\n")
    persona_ids = set(r["persona_id"] for r in rows)
    for pid in sorted(persona_ids):
        pname = PERSONA_NAMES.get(pid, pid)
        p_rows = [r for r in published if r["persona_id"] == pid]
        total_likes = 0
        for r in p_rows:
            m = conn.execute(
                """SELECT likes
                   FROM metrics WHERE publication_id = ?
                   ORDER BY captured_at DESC LIMIT 1""",
                (r["pub_id"],),
            ).fetchone()
            if m:
                total_likes += m["likes"] or 0

        lines.append(f"### {pname}")
        lines.append(f"- 已发布：{len(p_rows)} 篇")
        lines.append(f"- 总点赞：{total_likes}")
        lines.append("")

    return "\n".join(lines)


def _gen_dashboard_daily(conn, vault_path):
    """生成每日回顾看板（最近 7 天）。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    rows = conn.execute(
        "SELECT date, plan, output, notes FROM daily_logs WHERE date >= ? ORDER BY date DESC",
        (week_ago,),
    ).fetchall()

    lines = [
        "# 每日回顾",
        "",
        f"> 自动生成于 {now}，最近 7 天",
        "",
    ]

    if not rows:
        lines.append("_暂无日记记录_")
    else:
        for r in rows:
            lines.append(f"## {r['date']}\n")
            if r["plan"]:
                lines.append(f"**计划**：{r['plan'][:200]}\n")
            if r["output"]:
                lines.append(f"**产出**：{r['output'][:200]}\n")
            if r["notes"]:
                lines.append(f"**随想**：{r['notes'][:200]}\n")
            lines.append("---\n")

    return "\n".join(lines)


def sync_dashboards(conn, vault_path):
    """生成所有看板页面。"""
    dash_dir = os.path.join(vault_path, "00_看板")
    os.makedirs(dash_dir, exist_ok=True)

    dashboards = {
        "内容总览.md": _gen_dashboard_overview,
        "灵感池.md": _gen_dashboard_ideas,
        "发布追踪.md": _gen_dashboard_publish,
        "每日回顾.md": _gen_dashboard_daily,
    }

    for fname, gen_func in dashboards.items():
        content = gen_func(conn, vault_path)
        with open(os.path.join(dash_dir, fname), "w", encoding="utf-8") as f:
            f.write(content)

    return len(dashboards)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Vault 同步：data/ → Obsidian 只读视图")
    parser.add_argument("--vault-path", default=None, help="Obsidian vault 路径")
    args = parser.parse_args()

    vault_path = _get_vault_path(args.vault_path)

    if not os.path.isdir(vault_path):
        os.makedirs(vault_path, exist_ok=True)
        print(f"创建 vault 目录: {vault_path}", file=sys.stderr)

    conn = get_connection()

    try:
        print(f"Vault 路径: {vault_path}", file=sys.stderr)
        print("清理旧内容...", file=sys.stderr)
        _clean_vault(vault_path)

        n_ideas = sync_ideas(conn, vault_path)
        print(f"灵感同步: {n_ideas} 条", file=sys.stderr)

        n_contents = sync_contents(conn, vault_path)
        print(f"内容同步: {n_contents} 篇", file=sys.stderr)

        n_knowledge = sync_knowledge(vault_path)
        print(f"知识库同步: {n_knowledge} 个文件", file=sys.stderr)

        n_daily = sync_daily(conn, vault_path)
        print(f"日记同步: {n_daily} 天", file=sys.stderr)

        n_dash = sync_dashboards(conn, vault_path)
        print(f"看板生成: {n_dash} 个", file=sys.stderr)

        # 输出 JSON 结果
        result = {
            "vault_path": vault_path,
            "synced": {
                "ideas": n_ideas,
                "contents": n_contents,
                "knowledge": n_knowledge,
                "daily": n_daily,
                "dashboards": n_dash,
            },
        }
        print(json.dumps(result, ensure_ascii=False))

    finally:
        conn.close()


if __name__ == "__main__":
    main()
