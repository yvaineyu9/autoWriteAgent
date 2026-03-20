from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from .config import get_settings


settings = get_settings()
DB_PATH = settings.vault_path / "70_Distribution" / "distribution.db"
INBOX_DIR = settings.vault_path / "00_Inbox"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate() -> None:
    with closing(get_conn()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS content_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_id TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'social-media',
                persona_id TEXT,
                platform TEXT,
                status TEXT NOT NULL DEFAULT 'idea',
                source_path TEXT,
                output_path TEXT,
                review_score INTEGER,
                operator_type TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS status_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_id TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT NOT NULL,
                operator TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (content_id) REFERENCES content_status(content_id)
            )
            """
        )
        _ensure_column(conn, "publications", "content_id", "TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_publications_content_id ON publications(content_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_content_status_status ON content_status(status)")
        _recover_transient_statuses(conn)
        _repair_output_path_conflicts(conn)
        _repair_invalid_terminal_statuses(conn)
        conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def _recover_transient_statuses(conn: sqlite3.Connection) -> None:
    drafting_rows = conn.execute(
        "SELECT content_id, output_path FROM content_status WHERE status = 'drafting'"
    ).fetchall()
    for row in drafting_rows:
        next_status = "draft" if row["output_path"] else "idea"
        conn.execute(
            "UPDATE content_status SET status = ?, updated_at = datetime('now', 'localtime') WHERE content_id = ?",
            (next_status, row["content_id"]),
        )
        conn.execute(
            """INSERT INTO status_log (content_id, from_status, to_status, operator, note)
               VALUES (?, 'drafting', ?, 'system', '服务重启后恢复瞬时状态')""",
            (row["content_id"], next_status),
        )

    revising_rows = conn.execute(
        "SELECT content_id, output_path FROM content_status WHERE status = 'revising'"
    ).fetchall()
    for row in revising_rows:
        next_status = "final" if row["output_path"] else "draft"
        conn.execute(
            "UPDATE content_status SET status = ?, updated_at = datetime('now', 'localtime') WHERE content_id = ?",
            (next_status, row["content_id"]),
        )
        conn.execute(
            """INSERT INTO status_log (content_id, from_status, to_status, operator, note)
               VALUES (?, 'revising', ?, 'system', '服务重启后恢复瞬时状态')""",
            (row["content_id"], next_status),
        )


def _status_priority(status: str | None) -> int:
    order = {
        "published": 5,
        "publishing": 4,
        "final": 3,
        "draft": 2,
        "idea": 1,
    }
    return order.get(status or "", 0)


def _repair_output_path_conflicts(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT content_id, status, output_path, updated_at
        FROM content_status
        WHERE output_path IS NOT NULL
        ORDER BY output_path, updated_at DESC
        """
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(str(row["output_path"]), []).append(row)

    for output_path, items in grouped.items():
        if len(items) <= 1:
            continue
        ranked = sorted(
            items,
            key=lambda item: (_status_priority(item["status"]), str(item["updated_at"] or "")),
            reverse=True,
        )
        keeper = ranked[0]
        for row in ranked[1:]:
            fallback_status = "idea"
            conn.execute(
                """
                UPDATE content_status
                SET output_path = NULL,
                    status = ?,
                    updated_at = datetime('now', 'localtime')
                WHERE content_id = ?
                """,
                (fallback_status, row["content_id"]),
            )
            conn.execute(
                """
                INSERT INTO status_log (content_id, from_status, to_status, operator, note)
                VALUES (?, ?, ?, 'system', ?)
                """,
                (
                    row["content_id"],
                    row["status"],
                    fallback_status,
                    f"修复重复 output_path 绑定，保留 {keeper['content_id']} 使用 {output_path}",
                ),
            )


def _repair_invalid_terminal_statuses(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT content_id, status
        FROM content_status
        WHERE output_path IS NULL
          AND status IN ('draft', 'final', 'publishing', 'published')
        """
    ).fetchall()
    for row in rows:
        conn.execute(
            """
            UPDATE content_status
            SET status = 'idea',
                updated_at = datetime('now', 'localtime')
            WHERE content_id = ?
            """,
            (row["content_id"],),
        )
        conn.execute(
            """
            INSERT INTO status_log (content_id, from_status, to_status, operator, note)
            VALUES (?, ?, 'idea', 'system', '修复无输出文件的终态内容')
            """,
            (row["content_id"], row["status"]),
        )


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value.strip()).strip("-").lower()
    return cleaned or "untitled"


def _parse_frontmatter(raw: str) -> tuple[dict[str, str | list[str]], str]:
    if not raw.startswith("---"):
        return {}, raw
    # 支持 \r\n 和 \n 换行
    normalized = raw.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}, raw
    parts = normalized.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, raw
    yaml_block = parts[0][4:]  # 去掉开头的 "---\n"
    body = parts[1]
    try:
        import yaml

        parsed = yaml.safe_load(yaml_block)
        if not isinstance(parsed, dict):
            return {}, raw
        # 确保值类型为 str 或 list[str]
        frontmatter: dict[str, str | list[str]] = {}
        for key, value in parsed.items():
            if isinstance(value, list):
                frontmatter[str(key)] = [str(item) for item in value]
            elif value is not None:
                frontmatter[str(key)] = str(value)
        return frontmatter, body
    except ImportError:
        # 回退到简单解析
        frontmatter = {}
        for line in yaml_block.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                items = [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
                frontmatter[key] = items
            else:
                frontmatter[key] = value
        return frontmatter, body


def _dump_frontmatter(data: dict[str, object]) -> str:
    lines = ["---"]
    for key, value in data.items():
        if value is None or value == []:
            continue
        if isinstance(value, list):
            rendered = ", ".join(str(item) for item in value)
            lines.append(f"{key}: [{rendered}]")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def list_inspirations() -> list[dict[str, object]]:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    statuses = _status_by_source_path()
    items: list[dict[str, object]] = []
    for path in sorted(INBOX_DIR.rglob("*.md"), reverse=True):
        raw = path.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(raw)
        relative_path = str(path.relative_to(settings.vault_path))
        status_row = statuses.get(relative_path)
        tags = frontmatter.get("tags", [])
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
        items.append(
            {
                "path": relative_path,
                "title": str(frontmatter.get("title") or path.stem),
                "summary": body.strip().replace("\n", " ")[:100],
                "source": frontmatter.get("source"),
                "persona": frontmatter.get("persona"),
                "platform": frontmatter.get("platform"),
                "tags": tags,
                "created": frontmatter.get("created"),
                "status": status_row["status"] if status_row else "idea",
                "content_id": status_row["content_id"] if status_row else None,
            }
        )
    return items


def create_inspiration(payload: dict[str, object]) -> dict[str, object]:
    title = str(payload["title"])
    created = datetime.now().strftime("%Y-%m-%d")
    filename = f"{created}_{_slugify(title)}.md"
    path = INBOX_DIR / filename
    suffix = 1
    while path.exists():
        path = INBOX_DIR / f"{created}_{_slugify(title)}-{suffix}.md"
        suffix += 1
    frontmatter = {
        "title": title,
        "source": payload.get("source", "human"),
        "persona": payload.get("persona"),
        "platform": payload.get("platform"),
        "tags": payload.get("tags", []),
        "created": created,
    }
    path.write_text(f"{_dump_frontmatter(frontmatter)}\n{payload['body'].strip()}\n", encoding="utf-8")
    relative_path = str(path.relative_to(settings.vault_path))
    content_id = ensure_content_record(
        title=title,
        source_path=relative_path,
        persona_id=payload.get("persona"),
        platform=payload.get("platform"),
        status="idea",
        operator="human",
        note="创建灵感",
    )
    return get_inspiration(relative_path) | {"content_id": content_id}


def get_inspiration(relative_path: str) -> dict[str, object]:
    path = settings.vault_path / relative_path
    raw = path.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(raw)
    status_row = _status_by_source_path().get(relative_path)
    tags = frontmatter.get("tags", [])
    if isinstance(tags, str):
        tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
    return {
        "path": relative_path,
        "title": str(frontmatter.get("title") or path.stem),
        "body": body.strip(),
        "source": frontmatter.get("source"),
        "persona": frontmatter.get("persona"),
        "platform": frontmatter.get("platform"),
        "tags": tags,
        "created": frontmatter.get("created"),
        "status": status_row["status"] if status_row else "idea",
        "content_id": status_row["content_id"] if status_row else None,
    }


def update_inspiration(relative_path: str, payload: dict[str, object]) -> dict[str, object]:
    current = get_inspiration(relative_path)
    merged = {**current, **{k: v for k, v in payload.items() if v is not None}}
    path = settings.vault_path / relative_path
    frontmatter = {
        "title": merged["title"],
        "source": merged["source"],
        "persona": merged["persona"],
        "platform": merged["platform"],
        "tags": merged["tags"],
        "created": merged["created"],
    }
    path.write_text(f"{_dump_frontmatter(frontmatter)}\n{str(merged['body']).strip()}\n", encoding="utf-8")
    if merged.get("content_id"):
        update_content_metadata(
            content_id=str(merged["content_id"]),
            title=str(merged["title"]),
            persona_id=merged.get("persona"),
            platform=merged.get("platform"),
            source_path=relative_path,
            operator="human",
            note="更新灵感",
        )
    return get_inspiration(relative_path)


def delete_inspiration(relative_path: str) -> None:
    path = settings.vault_path / relative_path
    if path.exists():
        path.unlink()


def _status_by_source_path() -> dict[str, sqlite3.Row]:
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT content_id, source_path, status FROM content_status WHERE source_path IS NOT NULL").fetchall()
    return {str(row["source_path"]): row for row in rows}


def ensure_content_record(
    *,
    title: str,
    source_path: str | None,
    persona_id: str | None,
    platform: str | None,
    status: str,
    operator: str,
    note: str | None = None,
    content_type: str = "social-media",
) -> str:
    with closing(get_conn()) as conn:
        existing = None
        if source_path:
            existing = conn.execute(
                "SELECT content_id, status FROM content_status WHERE source_path = ?",
                (source_path,),
            ).fetchone()
        if existing:
            content_id = str(existing["content_id"])
            if status != existing["status"]:
                transition_content_status(
                    content_id=content_id,
                    to_status=status,
                    operator=operator,
                    note=note,
                    conn=conn,
                )
            conn.execute(
                """UPDATE content_status
                   SET title = ?, persona_id = ?, platform = ?, updated_at = datetime('now', 'localtime')
                   WHERE content_id = ?""",
                (title, persona_id, platform, content_id),
            )
            conn.commit()
            return content_id

        content_id = str(uuid4())
        conn.execute(
            """INSERT INTO content_status
               (content_id, title, content_type, persona_id, platform, status, source_path, operator_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (content_id, title, content_type, persona_id, platform, status, source_path, operator.split(":", 1)[0]),
        )
        conn.execute(
            """INSERT INTO status_log (content_id, from_status, to_status, operator, note)
               VALUES (?, NULL, ?, ?, ?)""",
            (content_id, status, operator, note),
        )
        conn.commit()
        return content_id


def activate_inspiration(relative_path: str) -> dict[str, object]:
    inspiration = get_inspiration(relative_path)
    content_id = inspiration.get("content_id")
    if content_id:
        return inspiration
    content_id = ensure_content_record(
        title=str(inspiration["title"]),
        source_path=relative_path,
        persona_id=inspiration.get("persona"),
        platform=inspiration.get("platform"),
        status="idea",
        operator="human",
        note="从灵感池激活内容",
    )
    updated = get_inspiration(relative_path)
    updated["content_id"] = content_id
    return updated


def transition_content_status(
    *,
    content_id: str,
    to_status: str,
    operator: str,
    note: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    owns_conn = conn is None
    conn = conn or get_conn()
    current = conn.execute(
        "SELECT status FROM content_status WHERE content_id = ?",
        (content_id,),
    ).fetchone()
    from_status = current["status"] if current else None
    conn.execute(
        """UPDATE content_status
           SET status = ?, operator_type = ?, updated_at = datetime('now', 'localtime')
           WHERE content_id = ?""",
        (to_status, operator.split(":", 1)[0], content_id),
    )
    conn.execute(
        """INSERT INTO status_log (content_id, from_status, to_status, operator, note)
           VALUES (?, ?, ?, ?, ?)""",
        (content_id, from_status, to_status, operator, note),
    )
    if owns_conn:
        conn.commit()
        conn.close()


def update_content_metadata(
    *,
    content_id: str,
    title: str,
    persona_id: str | None,
    platform: str | None,
    source_path: str | None = None,
    output_path: str | None = None,
    review_score: int | None = None,
    operator: str = "human",
    note: str | None = None,
) -> None:
    with closing(get_conn()) as conn:
        if output_path:
            existing = conn.execute(
                """
                SELECT content_id
                FROM content_status
                WHERE output_path = ? AND content_id != ?
                LIMIT 1
                """,
                (output_path, content_id),
            ).fetchone()
            if existing:
                raise ValueError(f"output_path 已被其他内容占用: {output_path}")
        conn.execute(
            """UPDATE content_status
               SET title = ?, persona_id = ?, platform = ?, source_path = COALESCE(?, source_path),
                   output_path = COALESCE(?, output_path), review_score = COALESCE(?, review_score),
                   operator_type = ?, updated_at = datetime('now', 'localtime')
               WHERE content_id = ?""",
            (title, persona_id, platform, source_path, output_path, review_score, operator.split(":", 1)[0], content_id),
        )
        if note:
            current = conn.execute("SELECT status FROM content_status WHERE content_id = ?", (content_id,)).fetchone()
            conn.execute(
                "INSERT INTO status_log (content_id, from_status, to_status, operator, note) VALUES (?, ?, ?, ?, ?)",
                (content_id, current["status"] if current else None, current["status"] if current else "idea", operator, note),
            )
        conn.commit()


def list_final_contents(persona: str | None = None, platform: str | None = None, limit: int = 20) -> list[dict[str, object]]:
    with closing(get_conn()) as conn:
        sql = """
            SELECT content_id, title, persona_id, platform, review_score, output_path, created_at
            FROM content_status
            WHERE status = 'final'
        """
        params: list[object] = []
        if persona:
            sql += " AND persona_id = ?"
            params.append(persona)
        if platform:
            sql += " AND platform = ?"
            params.append(platform)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def list_contents(status: str | None = None, limit: int = 50) -> list[dict[str, object]]:
    with closing(get_conn()) as conn:
        sql = """
            SELECT content_id, title, persona_id, platform, status, source_path, output_path, review_score, updated_at
            FROM content_status
            WHERE 1=1
        """
        params: list[object] = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def list_publications(limit: int = 50) -> list[dict[str, object]]:
    with closing(get_conn()) as conn:
        rows = conn.execute(
            """
            SELECT pub.*, a.account_name, a.platform, p.name AS persona_name
            FROM publications pub
            JOIN accounts a ON pub.account_id = a.id
            JOIN personas p ON a.persona_id = p.id
            ORDER BY pub.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_publications_for_contents(content_ids: Iterable[str]) -> list[int]:
    ids: list[int] = []
    with closing(get_conn()) as conn:
        for content_id in content_ids:
            content = conn.execute(
                "SELECT title, output_path, persona_id, platform FROM content_status WHERE content_id = ?",
                (content_id,),
            ).fetchone()
            if not content:
                continue
            accounts = conn.execute(
                "SELECT id FROM accounts WHERE persona_id = ? AND platform = ? AND status = 'active'",
                (content["persona_id"], content["platform"]),
            ).fetchall()
            if not accounts and content["persona_id"] and content["platform"]:
                account_id = _ensure_default_account(conn, str(content["persona_id"]), str(content["platform"]))
                accounts = [{"id": account_id}]
            for account in accounts:
                cur = conn.execute(
                    """INSERT INTO publications (content_id, content_path, account_id, title, status)
                       VALUES (?, ?, ?, ?, 'draft')""",
                    (content_id, content["output_path"], account["id"], content["title"]),
                )
                ids.append(int(cur.lastrowid))
            transition_content_status(
                content_id=content_id,
                to_status="publishing",
                operator="human",
                note="选稿确认",
                conn=conn,
            )
        conn.commit()
    return ids


def _ensure_default_account(conn: sqlite3.Connection, persona_id: str, platform: str) -> int:
    existing = conn.execute(
        "SELECT id FROM accounts WHERE persona_id = ? AND platform = ? ORDER BY id LIMIT 1",
        (persona_id, platform),
    ).fetchone()
    if existing:
        conn.execute("UPDATE accounts SET status = 'active' WHERE id = ?", (existing["id"],))
        return int(existing["id"])

    persona = conn.execute("SELECT name FROM personas WHERE id = ?", (persona_id,)).fetchone()
    account_name = f"{persona['name'] if persona else persona_id}-{platform}"
    cur = conn.execute(
        "INSERT INTO accounts (persona_id, platform, account_name, status) VALUES (?, ?, ?, 'active')",
        (persona_id, platform, account_name),
    )
    return int(cur.lastrowid)


def mark_publication_published(publication_id: int, post_url: str | None, published_at: str | None) -> None:
    published_at = published_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with closing(get_conn()) as conn:
        pub = conn.execute("SELECT content_id FROM publications WHERE id = ?", (publication_id,)).fetchone()
        conn.execute(
            "UPDATE publications SET status = 'published', post_url = ?, published_at = ? WHERE id = ?",
            (post_url, published_at, publication_id),
        )
        if pub and pub["content_id"]:
            transition_content_status(
                content_id=str(pub["content_id"]),
                to_status="published",
                operator="human",
                note=f"发布记录 #{publication_id} 已发布",
                conn=conn,
            )
        conn.commit()


def create_metric(publication_id: int, payload: dict[str, object]) -> None:
    with closing(get_conn()) as conn:
        conn.execute(
            """INSERT INTO metrics (publication_id, views, likes, collects, comments, shares, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                publication_id,
                payload.get("views", 0),
                payload.get("likes", 0),
                payload.get("collects", 0),
                payload.get("comments", 0),
                payload.get("shares", 0),
                payload.get("notes"),
            ),
        )
        current = conn.execute("SELECT status FROM publications WHERE id = ?", (publication_id,)).fetchone()
        if current and current["status"] == "published":
            conn.execute("UPDATE publications SET status = 'tracking' WHERE id = ?", (publication_id,))
        conn.commit()


def finalize_content(content_id: str) -> None:
    current = read_content(content_id)
    if not current:
        raise FileNotFoundError(f"content 不存在: {content_id}")
    if not current.get("output_path"):
        raise ValueError("当前内容还没有生成稿件，不能直接定稿")
    transition_content_status(content_id=content_id, to_status="final", operator="human", note="人工定稿")


def read_content(content_id: str) -> dict[str, object] | None:
    with closing(get_conn()) as conn:
        row = conn.execute("SELECT * FROM content_status WHERE content_id = ?", (content_id,)).fetchone()
    return dict(row) if row else None


def read_content_detail(content_id: str) -> dict[str, object] | None:
    row = read_content(content_id)
    if not row:
        return None
    body = ""
    resolved_path = None
    if row.get("output_path"):
        resolved_path = settings.vault_path / str(row["output_path"])
    elif row.get("source_path"):
        resolved_path = settings.vault_path / str(row["source_path"])
    if resolved_path and resolved_path.exists():
        body = resolved_path.read_text(encoding="utf-8")
    row["body"] = body
    row["resolved_path"] = str(resolved_path) if resolved_path else None
    return row


def save_content_detail(content_id: str, body: str, title: str | None = None) -> dict[str, object]:
    current = read_content(content_id)
    if not current:
        raise FileNotFoundError(f"content 不存在: {content_id}")

    resolved_path: Path | None = None
    if current.get("output_path"):
        resolved_path = settings.vault_path / str(current["output_path"])
    elif current.get("source_path"):
        resolved_path = settings.vault_path / str(current["source_path"])
    if not resolved_path:
        raise FileNotFoundError(f"content 没有关联文件: {content_id}")

    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    next_title = title or str(current.get("title") or "未命名内容")

    if resolved_path.suffix == ".md":
        raw = body.strip()
        if raw.startswith("---\n"):
            resolved_path.write_text(raw + "\n", encoding="utf-8")
        else:
            frontmatter = {
                "title": next_title,
                "persona": current.get("persona_id"),
                "platform": current.get("platform"),
                "content_id": content_id,
            }
            resolved_path.write_text(f"{_dump_frontmatter(frontmatter)}\n{raw}\n", encoding="utf-8")
    else:
        resolved_path.write_text(body, encoding="utf-8")

    with closing(get_conn()) as conn:
        previous_status = str(current["status"])
        conn.execute(
            """UPDATE content_status
               SET title = ?, updated_at = datetime('now', 'localtime')
               WHERE content_id = ?""",
            (next_title, content_id),
        )
        conn.execute(
            """INSERT INTO status_log (content_id, from_status, to_status, operator, note)
               VALUES (?, ?, ?, 'human', '通过 Web UI 保存内容')""",
            (content_id, previous_status, previous_status),
        )
        conn.commit()

    return read_content_detail(content_id) or {}


def write_output_markdown(content_id: str, title: str, persona: str, platform: str, body: str, review_score: int | None = None) -> str:
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    safe_title = _slugify(title)
    folder = settings.vault_path / "60_Published" / "social-media" / persona / platform / f"{date_prefix}_{safe_title}"
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / "content.md"
    frontmatter = {
        "title": title,
        "persona": persona,
        "platform": platform,
        "date": date_prefix,
        "review_score": review_score,
        "content_id": content_id,
    }
    output.write_text(f"{_dump_frontmatter(frontmatter)}\n{body.strip()}\n", encoding="utf-8")
    relative = str(output.relative_to(settings.vault_path))
    update_content_metadata(
        content_id=content_id,
        title=title,
        persona_id=persona,
        platform=platform,
        output_path=relative,
        review_score=review_score,
        operator="agent:content-creation",
    )
    return relative
