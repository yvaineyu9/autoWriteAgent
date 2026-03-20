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
INBOX_DIR = settings.project_root / "00_Inbox"


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
        conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value.strip()).strip("-").lower()
    return cleaned or "untitled"


def _parse_frontmatter(raw: str) -> tuple[dict[str, str | list[str]], str]:
    if not raw.startswith("---\n"):
        return {}, raw
    parts = raw.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, raw
    frontmatter: dict[str, str | list[str]] = {}
    for line in parts[0].splitlines()[1:]:
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
    return frontmatter, parts[1]


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
    for path in sorted(INBOX_DIR.glob("*.md"), reverse=True):
        raw = path.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(raw)
        relative_path = str(path.relative_to(settings.project_root))
        status_row = statuses.get(relative_path)
        items.append(
            {
                "path": relative_path,
                "title": str(frontmatter.get("title") or path.stem),
                "summary": body.strip().replace("\n", " ")[:100],
                "source": frontmatter.get("source"),
                "persona": frontmatter.get("persona"),
                "platform": frontmatter.get("platform"),
                "tags": frontmatter.get("tags", []),
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
    relative_path = str(path.relative_to(settings.project_root))
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
    path = settings.project_root / relative_path
    raw = path.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(raw)
    status_row = _status_by_source_path().get(relative_path)
    return {
        "path": relative_path,
        "title": str(frontmatter.get("title") or path.stem),
        "body": body.strip(),
        "source": frontmatter.get("source"),
        "persona": frontmatter.get("persona"),
        "platform": frontmatter.get("platform"),
        "tags": frontmatter.get("tags", []),
        "created": frontmatter.get("created"),
        "status": status_row["status"] if status_row else "idea",
        "content_id": status_row["content_id"] if status_row else None,
    }


def update_inspiration(relative_path: str, payload: dict[str, object]) -> dict[str, object]:
    current = get_inspiration(relative_path)
    merged = {**current, **{k: v for k, v in payload.items() if v is not None}}
    path = settings.project_root / relative_path
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
    path = settings.project_root / relative_path
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
    transition_content_status(content_id=content_id, to_status="final", operator="human", note="人工定稿")


def read_content(content_id: str) -> dict[str, object] | None:
    with closing(get_conn()) as conn:
        row = conn.execute("SELECT * FROM content_status WHERE content_id = ?", (content_id,)).fetchone()
    return dict(row) if row else None


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
