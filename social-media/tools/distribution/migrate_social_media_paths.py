#!/usr/bin/env python3
"""
将历史社媒成品路径迁移到统一标准路径：

    60_Published/social-media/<persona>/<platform>/YYYY-MM-DD_<title>/content.md

处理范围：
1. 文件系统中的历史目录：
   60_Published/<persona>/<platform>/<date_title>/content.md
2. distribution.db 中 publications.content_path 的历史引用
3. 若存在 content_status 表，同步修正 output_path

默认 dry-run，仅打印计划操作。
加 --apply 才真正执行。
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
from pathlib import Path


VAULT_PATH = Path(os.getenv("VAULT_PATH", "~/Desktop/vault")).expanduser()
DB_PATH = VAULT_PATH / "70_Distribution" / "distribution.db"
PUBLISHED_ROOT = VAULT_PATH / "60_Published"
SOCIAL_ROOT = PUBLISHED_ROOT / "social-media"
PERSONAS = {"chongxiaoyu", "yuejian"}
PLATFORM_SUFFIX = {
    "小红书": "xiaohongshu",
    "公众号": "wechat",
    "Twitter": "twitter",
    "twitter": "twitter",
}


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def parse_flat_filename(name: str) -> tuple[str | None, str | None]:
    stem = name[:-3] if name.endswith(".md") else name
    for suffix, platform in PLATFORM_SUFFIX.items():
        token = f"_{suffix}"
        if stem.endswith(token):
            return stem[: -len(token)], platform
    return None, None


def canonical_from_legacy_path(relative_path: str, *, persona: str | None = None, platform: str | None = None) -> str | None:
    parts = Path(relative_path).parts
    if len(parts) < 2 or parts[0] != "60_Published":
        return None

    if parts[1] == "social-media":
        if parts[-1] == "content.md":
            return relative_path
        if len(parts) == 4:
            inferred_base, inferred_platform = parse_flat_filename(parts[-1])
            next_persona = parts[2]
            next_platform = platform or inferred_platform
            if next_persona in PERSONAS and inferred_base and next_platform:
                return str(Path("60_Published") / "social-media" / next_persona / next_platform / inferred_base / "content.md")
        if len(parts) == 3:
            inferred_base, inferred_platform = parse_flat_filename(parts[-1])
            next_persona = persona
            next_platform = platform or inferred_platform
            if next_persona and inferred_base and next_platform:
                return str(Path("60_Published") / "social-media" / next_persona / next_platform / inferred_base / "content.md")
        return None

    if len(parts) >= 5 and parts[1] in PERSONAS:
        return str(Path("60_Published") / "social-media" / parts[1] / parts[2] / parts[3] / parts[4])

    return None


def migrate_filesystem(*, apply: bool) -> list[tuple[Path, Path]]:
    moves: list[tuple[Path, Path]] = []
    for persona_dir in sorted(PUBLISHED_ROOT.iterdir()):
        if not persona_dir.is_dir() or persona_dir.name not in PERSONAS:
            continue
        for platform_dir in sorted(persona_dir.iterdir()):
            if not platform_dir.is_dir():
                continue
            for entry in sorted(platform_dir.iterdir()):
                if entry.name.startswith("."):
                    continue
                target = SOCIAL_ROOT / persona_dir.name / platform_dir.name / entry.name
                if entry.resolve() == target.resolve():
                    continue
                moves.append((entry, target))

    for src, dst in moves:
        print(f"[MOVE] {src} -> {dst}")
        if not apply:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            raise FileExistsError(f"目标已存在，停止迁移: {dst}")
        src.rename(dst)

    if apply:
        for persona_dir in sorted(PUBLISHED_ROOT.iterdir()):
            if not persona_dir.is_dir() or persona_dir.name not in PERSONAS:
                continue
            for platform_dir in sorted(persona_dir.iterdir()):
                if platform_dir.is_dir() and not any(platform_dir.iterdir()):
                    platform_dir.rmdir()
            if not any(persona_dir.iterdir()):
                persona_dir.rmdir()
    return moves


def migrate_database(*, apply: bool) -> tuple[int, int]:
    if not DB_PATH.exists():
        print(f"[SKIP] 数据库不存在: {DB_PATH}")
        return 0, 0

    with get_conn() as conn:
        pub_rows = conn.execute(
            """
            SELECT pub.id, pub.content_path, a.platform, p.id AS persona_id
            FROM publications pub
            JOIN accounts a ON pub.account_id = a.id
            JOIN personas p ON a.persona_id = p.id
            WHERE pub.content_path IS NOT NULL
            """
        ).fetchall()

        pub_updates: list[tuple[str, int]] = []
        for row in pub_rows:
            next_path = canonical_from_legacy_path(
                str(row["content_path"]),
                persona=str(row["persona_id"]),
                platform=str(row["platform"]),
            )
            if next_path and next_path != row["content_path"]:
                print(f"[PUB] #{row['id']} {row['content_path']} -> {next_path}")
                pub_updates.append((next_path, int(row["id"])))

        status_updates: list[tuple[str, str]] = []
        has_content_status = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='content_status'"
        ).fetchone()
        if has_content_status:
            rows = conn.execute(
                """
                SELECT content_id, output_path, persona_id, platform
                FROM content_status
                WHERE output_path IS NOT NULL
                """
            ).fetchall()
            for row in rows:
                next_path = canonical_from_legacy_path(
                    str(row["output_path"]),
                    persona=str(row["persona_id"]) if row["persona_id"] else None,
                    platform=str(row["platform"]) if row["platform"] else None,
                )
                if next_path and next_path != row["output_path"]:
                    print(f"[STATUS] {row['content_id']} {row['output_path']} -> {next_path}")
                    status_updates.append((next_path, str(row["content_id"])))

        if apply:
            for next_path, pub_id in pub_updates:
                conn.execute("UPDATE publications SET content_path = ? WHERE id = ?", (next_path, pub_id))
            for next_path, content_id in status_updates:
                conn.execute("UPDATE content_status SET output_path = ? WHERE content_id = ?", (next_path, content_id))
            conn.commit()

        return len(pub_updates), len(status_updates)


def main() -> None:
    parser = argparse.ArgumentParser(description="迁移社媒成品路径到统一目录")
    parser.add_argument("--apply", action="store_true", help="真正执行迁移；默认仅预览")
    args = parser.parse_args()

    print(f"VAULT_PATH = {VAULT_PATH}")
    print(f"MODE = {'APPLY' if args.apply else 'DRY-RUN'}")

    file_moves = migrate_filesystem(apply=args.apply)
    pub_count, status_count = migrate_database(apply=args.apply)

    print()
    print("Summary")
    print(f"  filesystem moves: {len(file_moves)}")
    print(f"  publication path updates: {pub_count}")
    print(f"  content_status updates: {status_count}")


if __name__ == "__main__":
    main()
