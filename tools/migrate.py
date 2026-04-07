#!/usr/bin/env python3
"""
一次性迁移脚本：从旧 vault + distribution.db 迁移到 data/ 目录结构。

用法：
  python tools/migrate.py --old-vault <vault_path> [--dry-run]

迁移内容：
  1. personas / accounts → personas, accounts 表
  2. 60_Published/ 成品文件 → data/content/<content_id>/ + contents 表
  3. publications / metrics → publications, metrics 表（关联新 content_id）
  4. 00_Inbox/ 灵感文件 → data/content/inbox/ + ideas 表
  5. 30_Research/ → data/knowledge/research/
  6. 10_Daily/ → daily_logs 表
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_connection, PROJECT_ROOT

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DATA_CONTENT_DIR = os.path.join(DATA_DIR, "content")
INBOX_DIR = os.path.join(DATA_CONTENT_DIR, "inbox")
KNOWLEDGE_DIR = os.path.join(DATA_DIR, "knowledge")


def _to_slug(title: str, max_len: int = 30) -> str:
    """将标题转为 ASCII slug（复用 archive.py 逻辑）。"""
    try:
        from pypinyin import lazy_pinyin
        raw = "-".join(lazy_pinyin(title))
    except ImportError:
        alpha_num = re.sub(r"[^a-zA-Z0-9]", " ", title).strip()
        alpha_num = re.sub(r"\s+", "-", alpha_num)
        if len(alpha_num) >= 3:
            raw = alpha_num
        else:
            import hashlib
            raw = hashlib.md5(title.encode()).hexdigest()[:12]

    slug = re.sub(r"[\s_-]+", "-", raw).strip("-").lower()
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    return slug[:max_len] if slug else "untitled"


def _parse_frontmatter(filepath):
    """解析 markdown 文件的 frontmatter，返回 (metadata_dict, body_text)。"""
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    meta = {}
    for line in parts[1].strip().split("\n"):
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        meta[key] = val

    body = parts[2].strip()
    return meta, body


def _normalize_title(title):
    """去掉标点符号，用于模糊匹配标题。"""
    return re.sub(r'[，。！？、；：\u201c\u201d\u2018\u2019（）\s,\.!\?;:\"\'()\[\]【】…—\-\\/]', '', title).lower()


def _parse_daily(filepath):
    """解析 daily 文件，提取 plan / output / notes 段落。"""
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    sections = {"plan": "", "output": "", "notes": ""}
    current = None

    for line in text.split("\n"):
        lower = line.strip().lower()
        if "今日计划" in line:
            current = "plan"
            continue
        elif "产出记录" in line:
            current = "output"
            continue
        elif "随想" in line:
            current = "notes"
            continue
        elif line.startswith("## ") and current is not None:
            # 其他 ## 段落（如 Inbox 处理、项目进展）归入 notes
            current = "notes"
            continue

        if current and line.strip():
            sections[current] += line + "\n"

    return {k: v.strip() for k, v in sections.items()}


def migrate_personas(old_db_conn, new_conn, dry_run):
    """迁移人设和账号数据。"""
    print("\n=== 迁移人设和账号 ===")

    rows = old_db_conn.execute("SELECT id, name FROM personas").fetchall()
    for r in rows:
        print(f"  人设: {r[0]} ({r[1]})")
        if not dry_run:
            new_conn.execute(
                "INSERT OR IGNORE INTO personas (id, name) VALUES (?, ?)",
                (r[0], r[1]),
            )

    rows = old_db_conn.execute(
        "SELECT persona_id, platform, account_name FROM accounts WHERE status='active'"
    ).fetchall()
    for r in rows:
        print(f"  账号: {r[0]}/{r[1]} → {r[2]}")
        if not dry_run:
            new_conn.execute(
                "INSERT OR IGNORE INTO accounts (persona_id, platform, account_name) VALUES (?, ?, ?)",
                (r[0], r[1], r[2]),
            )

    if not dry_run:
        new_conn.commit()


def migrate_published_content(old_vault, old_db_conn, new_conn, dry_run):
    """迁移 60_Published/ 下的成品文件。返回 {old_pub_title: new_content_id} 映射。"""
    print("\n=== 迁移成品内容 ===")

    pub_dir = os.path.join(old_vault, "60_Published", "social-media")
    if not os.path.isdir(pub_dir):
        print(f"  跳过：目录不存在 {pub_dir}")
        return {}

    # 用于 slug 去重
    used_content_ids = set()
    # title → content_id 映射（用于关联 publications）
    # 存多种形式的标题以提高匹配率
    title_to_cid = {}
    # normalized_title → content_id（模糊匹配用）
    norm_title_to_cid = {}
    migrated = 0

    for persona in sorted(os.listdir(pub_dir)):
        persona_dir = os.path.join(pub_dir, persona)
        if not os.path.isdir(persona_dir):
            continue
        for platform in sorted(os.listdir(persona_dir)):
            platform_dir = os.path.join(persona_dir, platform)
            if not os.path.isdir(platform_dir):
                continue
            for content_dir_name in sorted(os.listdir(platform_dir)):
                content_dir = os.path.join(platform_dir, content_dir_name)
                content_file = os.path.join(content_dir, "content.md")
                if not os.path.isfile(content_file):
                    continue

                meta, body = _parse_frontmatter(content_file)
                title = meta.get("title", content_dir_name)

                # 从目录名提取日期
                date_match = re.match(r"(\d{4}-\d{2}-\d{2})", content_dir_name)
                if date_match:
                    date_str = date_match.group(1).replace("-", "")
                    date_display = date_match.group(1)
                else:
                    date_str = meta.get("date", "20260101").replace("-", "")
                    date_display = meta.get("date", "2026-01-01")

                # 生成 content_id
                slug = _to_slug(title)
                content_id = f"{persona}_{platform}_{date_str}_{slug}"

                # 去重
                if content_id in used_content_ids:
                    n = 2
                    while f"{content_id}_{n}" in used_content_ids:
                        n += 1
                    content_id = f"{content_id}_{n}"
                used_content_ids.add(content_id)

                title_to_cid[title] = content_id
                norm_title_to_cid[_normalize_title(title)] = content_id
                # 也存目录名中的标题（去日期前缀）
                dir_title = re.sub(r"^\d{4}-\d{2}-\d{2}_?", "", content_dir_name)
                if dir_title:
                    norm_title_to_cid[_normalize_title(dir_title)] = content_id

                # 判断状态
                pub_status = meta.get("publish_status", "")
                if pub_status == "published":
                    status = "published"
                else:
                    status = "final"

                # review_score
                review_score = None
                if meta.get("review_score"):
                    try:
                        review_score = int(meta["review_score"])
                    except ValueError:
                        pass

                print(f"  [{status:>9}] {content_id}")

                if dry_run:
                    migrated += 1
                    continue

                # 复制文件（含图片等附件）
                dest_dir = os.path.join(DATA_CONTENT_DIR, content_id)
                os.makedirs(dest_dir, exist_ok=True)

                # 写入纯正文（不含 frontmatter）
                dest_file = os.path.join(dest_dir, "content.md")
                with open(dest_file, "w", encoding="utf-8") as f:
                    f.write(body)

                # 复制附件（jpg/png 等）
                for fname in os.listdir(content_dir):
                    if fname == "content.md":
                        continue
                    src = os.path.join(content_dir, fname)
                    dst = os.path.join(dest_dir, fname)
                    if os.path.isfile(src):
                        shutil.copy2(src, dst)

                # 写入 contents 表
                rel_path = f"{content_id}/content.md"
                created_at = f"{date_display} 00:00:00"

                new_conn.execute(
                    """INSERT OR IGNORE INTO contents
                       (content_id, title, persona_id, platform, status, file_path,
                        review_score, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))""",
                    (content_id, title, persona, platform, status,
                     rel_path, review_score, created_at),
                )
                migrated += 1

    if not dry_run:
        new_conn.commit()

    # 也处理 _legacy
    legacy_dir = os.path.join(old_vault, "60_Published", "_legacy")
    if os.path.isdir(legacy_dir):
        for persona in sorted(os.listdir(legacy_dir)):
            persona_dir = os.path.join(legacy_dir, persona)
            if not os.path.isdir(persona_dir):
                continue
            for platform in sorted(os.listdir(persona_dir)):
                platform_dir = os.path.join(persona_dir, platform)
                if not os.path.isdir(platform_dir):
                    continue
                for content_dir_name in sorted(os.listdir(platform_dir)):
                    content_dir = os.path.join(platform_dir, content_dir_name)
                    content_file = os.path.join(content_dir, "content.md")
                    if not os.path.isfile(content_file):
                        continue

                    meta, body = _parse_frontmatter(content_file)
                    title = meta.get("title", content_dir_name)
                    date_match = re.match(r"(\d{4}-\d{2}-\d{2})", content_dir_name)
                    date_str = date_match.group(1).replace("-", "") if date_match else "20260101"
                    date_display = date_match.group(1) if date_match else "2026-01-01"

                    slug = _to_slug(title)
                    content_id = f"{persona}_{platform}_{date_str}_{slug}"
                    if content_id in used_content_ids:
                        n = 2
                        while f"{content_id}_{n}" in used_content_ids:
                            n += 1
                        content_id = f"{content_id}_{n}"
                    used_content_ids.add(content_id)
                    title_to_cid[title] = content_id
                    norm_title_to_cid[_normalize_title(title)] = content_id
                    dir_title = re.sub(r"^\d{4}-\d{2}-\d{2}_?", "", content_dir_name)
                    if dir_title:
                        norm_title_to_cid[_normalize_title(dir_title)] = content_id

                    print(f"  [  legacy] {content_id}")

                    if not dry_run:
                        dest_dir = os.path.join(DATA_CONTENT_DIR, content_id)
                        os.makedirs(dest_dir, exist_ok=True)
                        dest_file = os.path.join(dest_dir, "content.md")
                        with open(dest_file, "w", encoding="utf-8") as f:
                            f.write(body)
                        for fname in os.listdir(content_dir):
                            if fname == "content.md":
                                continue
                            src = os.path.join(content_dir, fname)
                            dst = os.path.join(dest_dir, fname)
                            if os.path.isfile(src):
                                shutil.copy2(src, dst)

                        rel_path = f"{content_id}/content.md"
                        new_conn.execute(
                            """INSERT OR IGNORE INTO contents
                               (content_id, title, persona_id, platform, status, file_path,
                                created_at, updated_at)
                               VALUES (?, ?, ?, ?, 'archived', ?, ?, datetime('now','localtime'))""",
                            (content_id, title, persona, platform, rel_path,
                             f"{date_display} 00:00:00"),
                        )
                    migrated += 1

    if not dry_run:
        new_conn.commit()

    print(f"  成品迁移完成: {migrated} 篇")
    return title_to_cid, norm_title_to_cid


def migrate_publications(old_db_conn, new_conn, title_to_cid, norm_title_to_cid, dry_run):
    """迁移发布记录和 metrics。返回 {old_pub_id: new_pub_id} 映射。"""
    print("\n=== 迁移发布记录 ===")

    old_pub_id_map = {}
    rows = old_db_conn.execute(
        """SELECT p.id, p.title, p.status, p.post_url, p.published_at, p.created_at,
                  a.persona_id, a.platform
           FROM publications p
           LEFT JOIN accounts a ON p.account_id = a.id
           ORDER BY p.id"""
    ).fetchall()

    migrated = 0
    for r in rows:
        old_id = r[0]
        title = r[1]
        status = r[2]
        post_url = r[3]
        published_at = r[4]
        created_at = r[5]
        persona_id = r[6] or "unknown"
        platform = r[7] or "xiaohongshu"

        # 状态映射
        status_map = {
            "published": "published",
            "tracking": "published",
            "ready": "draft",
            "draft": "draft",
        }
        new_status = status_map.get(status, "draft")

        # 查找对应的 content_id（多级匹配）
        content_id = title_to_cid.get(title)
        if not content_id:
            # 尝试标准化后匹配
            content_id = norm_title_to_cid.get(_normalize_title(title))
        if not content_id:
            # 尝试子串匹配
            norm_t = _normalize_title(title)
            for nt, cid in norm_title_to_cid.items():
                if norm_t in nt or nt in norm_t:
                    content_id = cid
                    break

        if not content_id:
            print(f"  [跳过] pub#{old_id} \"{title}\" — 无对应成品文件")
            continue

        print(f"  pub#{old_id} → {content_id} [{new_status}]")

        if not dry_run:
            cursor = new_conn.execute(
                """INSERT INTO publications
                   (content_id, persona_id, platform, status, post_url, published_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (content_id, persona_id, platform, new_status, post_url,
                 published_at, created_at),
            )
            new_pub_id = cursor.lastrowid
            old_pub_id_map[old_id] = new_pub_id
        migrated += 1

    if not dry_run:
        new_conn.commit()

    print(f"  发布记录迁移完成: {migrated} 条")
    return old_pub_id_map


def migrate_metrics(old_db_conn, new_conn, old_pub_id_map, dry_run):
    """迁移 metrics 数据。"""
    print("\n=== 迁移 Metrics ===")

    rows = old_db_conn.execute(
        "SELECT publication_id, views, likes, collects, comments, shares, captured_at FROM metrics"
    ).fetchall()

    migrated = 0
    for r in rows:
        old_pub_id = r[0]
        new_pub_id = old_pub_id_map.get(old_pub_id)
        if not new_pub_id:
            print(f"  [跳过] metrics for old pub#{old_pub_id} — 无对应新发布记录")
            continue

        print(f"  metrics: pub#{old_pub_id} → new_pub#{new_pub_id} "
              f"(V:{r[1]} L:{r[2]} C:{r[3]} Co:{r[4]} S:{r[5]})")

        if not dry_run:
            new_conn.execute(
                """INSERT INTO metrics
                   (publication_id, views, likes, collects, comments, shares, captured_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (new_pub_id, r[1], r[2], r[3], r[4], r[5], r[6]),
            )
        migrated += 1

    if not dry_run:
        new_conn.commit()

    print(f"  Metrics 迁移完成: {migrated} 条")


def migrate_inbox(old_vault, new_conn, dry_run):
    """迁移 00_Inbox/ 下的灵感文件。"""
    print("\n=== 迁移灵感素材 ===")

    inbox_dir = os.path.join(old_vault, "00_Inbox")
    if not os.path.isdir(inbox_dir):
        print(f"  跳过：目录不存在 {inbox_dir}")
        return

    migrated = 0

    for root, dirs, files in os.walk(inbox_dir):
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue

            filepath = os.path.join(root, fname)
            meta, body = _parse_frontmatter(filepath)

            # 从文件名或 frontmatter 提取标题
            title = meta.get("title", "")
            if not title:
                # 从文件名提取（去掉日期前缀和扩展名）
                name = os.path.splitext(fname)[0]
                # 去掉 YYYY-MM-DD 前缀
                title = re.sub(r"^\d{4}-\d{2}-\d{2}[-_]?", "", name).strip()
                if not title:
                    title = name

            # 标签
            tags_str = meta.get("tags", "")
            if not tags_str:
                # 从子目录名推断
                rel = os.path.relpath(root, inbox_dir)
                if rel != ".":
                    tags_str = json.dumps([rel], ensure_ascii=False)
                else:
                    tags_str = "[]"
            elif not tags_str.startswith("["):
                tags_str = json.dumps([t.strip() for t in tags_str.split(",")], ensure_ascii=False)

            # 来源
            source = meta.get("source", "human")

            # 状态
            status = meta.get("status", "pending")

            idea_id = str(uuid.uuid4())

            print(f"  [{status:>7}] {title[:40]}...")

            if dry_run:
                migrated += 1
                continue

            os.makedirs(INBOX_DIR, exist_ok=True)
            dest = os.path.join(INBOX_DIR, f"{idea_id}.md")
            with open(dest, "w", encoding="utf-8") as f:
                f.write(body)

            rel_path = f"inbox/{idea_id}.md"
            new_conn.execute(
                """INSERT INTO ideas (id, title, tags, source, status, file_path)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (idea_id, title, tags_str, source, status, rel_path),
            )
            migrated += 1

    if not dry_run:
        new_conn.commit()

    print(f"  灵感迁移完成: {migrated} 条")


def migrate_knowledge(old_vault, dry_run):
    """迁移 30_Research/ 和 40_Wiki/ 到 data/knowledge/。"""
    print("\n=== 迁移知识库 ===")

    migrated = 0
    for src_name, dst_name in [("30_Research", "research"), ("40_Wiki", "wiki")]:
        src = os.path.join(old_vault, src_name)
        dst = os.path.join(KNOWLEDGE_DIR, dst_name)
        if not os.path.isdir(src):
            continue

        files = [f for f in os.listdir(src) if not f.startswith(".")]
        if not files:
            print(f"  {src_name}: 空目录，跳过")
            continue

        print(f"  {src_name} → data/knowledge/{dst_name}/ ({len(files)} 个文件)")

        if not dry_run:
            os.makedirs(dst, exist_ok=True)
            for fname in files:
                s = os.path.join(src, fname)
                d = os.path.join(dst, fname)
                if os.path.isfile(s):
                    shutil.copy2(s, d)
                    migrated += 1

    print(f"  知识库迁移完成: {migrated} 个文件")


def migrate_daily(old_vault, new_conn, dry_run):
    """迁移 10_Daily/ 日记文件到 daily_logs 表。"""
    print("\n=== 迁移每日日记 ===")

    daily_dir = os.path.join(old_vault, "10_Daily")
    if not os.path.isdir(daily_dir):
        print(f"  跳过：目录不存在 {daily_dir}")
        return

    migrated = 0
    for fname in sorted(os.listdir(daily_dir)):
        if not fname.endswith(".md"):
            continue

        date_str = os.path.splitext(fname)[0]  # YYYY-MM-DD
        filepath = os.path.join(daily_dir, fname)
        sections = _parse_daily(filepath)

        print(f"  {date_str}: plan={len(sections['plan'])}c output={len(sections['output'])}c notes={len(sections['notes'])}c")

        if not dry_run:
            new_conn.execute(
                """INSERT OR IGNORE INTO daily_logs (date, plan, output, notes, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (date_str,
                 sections["plan"] or None,
                 sections["output"] or None,
                 sections["notes"] or None,
                 f"{date_str} 00:00:00"),
            )
        migrated += 1

    if not dry_run:
        new_conn.commit()

    print(f"  日记迁移完成: {migrated} 天")


def main():
    parser = argparse.ArgumentParser(description="一次性迁移：旧 vault → data/")
    parser.add_argument("--old-vault", required=True, help="旧 vault 根目录路径")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际写入")
    args = parser.parse_args()

    old_vault = os.path.expanduser(args.old_vault)
    if not os.path.isdir(old_vault):
        print(f"错误：旧 vault 不存在: {old_vault}")
        sys.exit(1)

    old_db_path = os.path.join(old_vault, "70_Distribution", "distribution.db")
    if not os.path.isfile(old_db_path):
        print(f"错误：旧数据库不存在: {old_db_path}")
        sys.exit(1)

    if args.dry_run:
        print("=== DRY RUN 模式 ===\n")

    # 连接旧数据库
    old_conn = sqlite3.connect(old_db_path)

    # 初始化新数据库
    new_conn = get_connection()

    print(f"旧 vault: {old_vault}")
    print(f"旧数据库: {old_db_path}")
    print(f"新数据目录: {DATA_DIR}")

    try:
        # 1. 人设和账号
        migrate_personas(old_conn, new_conn, args.dry_run)

        # 2. 成品内容（返回 title→content_id 映射）
        title_to_cid, norm_title_to_cid = migrate_published_content(old_vault, old_conn, new_conn, args.dry_run)

        # 3. 发布记录（返回 old_pub_id→new_pub_id 映射）
        old_pub_id_map = migrate_publications(old_conn, new_conn, title_to_cid, norm_title_to_cid, args.dry_run)

        # 4. Metrics
        migrate_metrics(old_conn, new_conn, old_pub_id_map, args.dry_run)

        # 5. 灵感素材
        migrate_inbox(old_vault, new_conn, args.dry_run)

        # 6. 知识库
        migrate_knowledge(old_vault, args.dry_run)

        # 7. 每日日记
        migrate_daily(old_vault, new_conn, args.dry_run)

        print("\n=== 迁移完成 ===")
        if args.dry_run:
            print("（预览模式，未实际写入。去掉 --dry-run 执行真正迁移）")

    finally:
        old_conn.close()
        new_conn.close()


if __name__ == "__main__":
    main()
