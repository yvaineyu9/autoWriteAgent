from __future__ import annotations

import os
import sys
from typing import Optional

# Ensure tools/ is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "tools"))

from db import get_connection, PROJECT_ROOT as PROJ_ROOT

DATA_CONTENT_DIR = os.path.join(PROJ_ROOT, "data", "content")


def list_ideas(status: Optional[str] = None) -> list:
    conn = get_connection()
    try:
        sql = "SELECT id, title, tags, source, status, created_at, updated_at FROM ideas"
        params = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def get_idea(idea_id: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_contents(status: Optional[str] = None, platform: Optional[str] = None) -> list:
    conn = get_connection()
    try:
        sql = "SELECT content_id, title, persona_id, platform, status, review_score, review_json, source_idea, created_at, updated_at FROM contents WHERE persona_id = 'yuejian'"
        params: list = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if platform:
            sql += " AND platform = ?"
            params.append(platform)
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def get_content(content_id: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM contents WHERE content_id = ?", (content_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def read_content_body(file_path: str) -> Optional[str]:
    abs_path = os.path.join(DATA_CONTENT_DIR, file_path)
    if not os.path.isfile(abs_path):
        return None
    with open(abs_path, "r", encoding="utf-8") as f:
        return f.read()


def create_idea(title: str, content: str, tags: str) -> dict:
    import uuid
    idea_id = str(uuid.uuid4())
    inbox_dir = os.path.join(DATA_CONTENT_DIR, "inbox")
    os.makedirs(inbox_dir, exist_ok=True)
    rel_path = "inbox/{}.md".format(idea_id)
    abs_path = os.path.join(DATA_CONTENT_DIR, rel_path)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO ideas (id, title, tags, source, file_path) VALUES (?, ?, ?, 'human', ?)",
            (idea_id, title, tags, rel_path),
        )
        conn.commit()
        row = conn.execute("SELECT id, title, tags, source, status, created_at, updated_at FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_idea(idea_id: str, title: str, content: str, tags: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        if not row:
            return None
        # Update file
        abs_path = os.path.join(DATA_CONTENT_DIR, row["file_path"])
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        conn.execute(
            "UPDATE ideas SET title=?, tags=?, updated_at=datetime('now','localtime') WHERE id=?",
            (title, tags, idea_id),
        )
        conn.commit()
        updated = conn.execute("SELECT id, title, tags, source, status, created_at, updated_at FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        return dict(updated)
    finally:
        conn.close()


def delete_idea(idea_id: str) -> bool:
    conn = get_connection()
    try:
        row = conn.execute("SELECT file_path FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        if not row:
            return False
        abs_path = os.path.join(DATA_CONTENT_DIR, row["file_path"])
        if os.path.isfile(abs_path):
            os.remove(abs_path)
        conn.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def delete_content(content_id: str) -> bool:
    conn = get_connection()
    try:
        row = conn.execute("SELECT content_id, file_path, status FROM contents WHERE content_id = ?", (content_id,)).fetchone()
        if not row:
            return False
        if row["status"] == "published":
            return False
        content_dir = os.path.join(DATA_CONTENT_DIR, content_id)
        if os.path.isdir(content_dir):
            import shutil
            shutil.rmtree(content_dir)
        conn.execute("DELETE FROM status_log WHERE content_id = ?", (content_id,))
        conn.execute("DELETE FROM contents WHERE content_id = ?", (content_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def write_content_body(file_path: str, body: str):
    abs_path = os.path.join(DATA_CONTENT_DIR, file_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(body)


def read_idea_body(file_path: str) -> Optional[str]:
    abs_path = os.path.join(DATA_CONTENT_DIR, file_path)
    if not os.path.isfile(abs_path):
        return None
    with open(abs_path, "r", encoding="utf-8") as f:
        return f.read()


def list_publications(status: Optional[str] = None) -> list:
    conn = get_connection()
    try:
        sql = """
            SELECT p.id, p.content_id, p.persona_id, p.platform, p.status,
                   p.post_url, p.published_at, p.created_at,
                   c.title as content_title,
                   m.views, m.likes, m.collects, m.comments, m.shares, m.captured_at as metrics_captured_at
            FROM publications p
            LEFT JOIN contents c ON p.content_id = c.content_id
            LEFT JOIN metrics m ON m.publication_id = p.id
                AND m.id = (SELECT MAX(m2.id) FROM metrics m2 WHERE m2.publication_id = p.id)
            WHERE p.persona_id = 'yuejian'
        """
        params: list = []
        if status:
            sql += " AND p.status = ?"
            params.append(status)
        sql += " ORDER BY p.created_at DESC"

        results = []
        for r in conn.execute(sql, params).fetchall():
            row = dict(r)
            pub = {
                "id": row["id"],
                "content_id": row["content_id"],
                "persona_id": row["persona_id"],
                "platform": row["platform"],
                "status": row["status"],
                "post_url": row["post_url"],
                "published_at": row["published_at"],
                "created_at": row["created_at"],
                "content_title": row["content_title"],
                "latest_metrics": None,
            }
            if row.get("metrics_captured_at"):
                pub["latest_metrics"] = {
                    "views": row["views"],
                    "likes": row["likes"],
                    "collects": row["collects"],
                    "comments": row["comments"],
                    "shares": row["shares"],
                    "captured_at": row["metrics_captured_at"],
                }
            results.append(pub)
        return results
    finally:
        conn.close()


def get_publication(pub_id: int) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM publications WHERE id = ?", (pub_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_metrics(pub_id: int, views: int, likes: int, collects: int, comments: int, shares: int) -> dict:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM metrics WHERE publication_id = ?", (pub_id,))
        conn.execute(
            "INSERT INTO metrics (publication_id, views, likes, collects, comments, shares) VALUES (?, ?, ?, ?, ?, ?)",
            (pub_id, views, likes, collects, comments, shares),
        )
        conn.commit()
        row = conn.execute(
            "SELECT views, likes, collects, comments, shares, captured_at FROM metrics WHERE publication_id = ?",
            (pub_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_publication(pub_id: int, status: str, post_url: Optional[str] = None):
    conn = get_connection()
    try:
        pub = conn.execute("SELECT id, content_id, status as old_status FROM publications WHERE id = ?", (pub_id,)).fetchone()
        if not pub:
            return None

        if post_url is not None:
            conn.execute(
                "UPDATE publications SET status=?, post_url=?, published_at=datetime('now','localtime') WHERE id=?",
                (status, post_url, pub_id),
            )
        else:
            conn.execute("UPDATE publications SET status=? WHERE id=?", (status, pub_id))
            if status == "published":
                conn.execute("UPDATE publications SET published_at=datetime('now','localtime') WHERE id=? AND published_at IS NULL", (pub_id,))

        conn.execute(
            "UPDATE contents SET status=?, updated_at=datetime('now','localtime') WHERE content_id=?",
            (status if status == "published" else "publishing", pub["content_id"]),
        )
        conn.execute(
            "INSERT INTO status_log (content_id, from_status, to_status, operator, note) VALUES (?, ?, ?, 'ui', ?)",
            (pub["content_id"], pub["old_status"], status, "UI update publication #{}".format(pub_id)),
        )
        conn.commit()

        row = conn.execute("SELECT * FROM publications WHERE id = ?", (pub_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_idea_status(idea_id: str, status: str):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE ideas SET status = ?, updated_at = datetime('now','localtime') WHERE id = ?",
            (status, idea_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_content_after_revise(content_id: str, review_score: Optional[int], review_json: Optional[str]):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE contents SET status='final', review_score=?, review_json=?, updated_at=datetime('now','localtime') WHERE content_id=?",
            (review_score, review_json, content_id),
        )
        conn.execute(
            "INSERT INTO status_log (content_id, from_status, to_status, operator, note) VALUES (?, 'revising', 'final', 'ui-revise', 'UI revision')",
            (content_id,),
        )
        conn.commit()
    finally:
        conn.close()
