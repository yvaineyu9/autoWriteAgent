#!/usr/bin/env python3
"""
分发中心数据层 — SQLite schema + 连接管理

数据库位置：70_Distribution/distribution.db
"""

import sqlite3
from pathlib import Path
from datetime import datetime

import os

VAULT_PATH = Path(os.getenv("VAULT_PATH", "~/Desktop/vault")).expanduser()
DB_PATH = VAULT_PATH / "70_Distribution" / "distribution.db"

_conn_singleton = None


def get_conn() -> sqlite3.Connection:
    """获取数据库单例连接，自动建表"""
    global _conn_singleton
    if _conn_singleton is not None:
        return _conn_singleton
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _init_schema(conn)
    _conn_singleton = conn
    return conn


def _init_schema(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS personas (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            config_path TEXT
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_id   TEXT NOT NULL REFERENCES personas(id),
            platform     TEXT NOT NULL DEFAULT 'xiaohongshu',
            account_name TEXT NOT NULL,
            account_id   TEXT,
            status       TEXT NOT NULL DEFAULT 'active'
                         CHECK(status IN ('active', 'paused')),
            created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS publications (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            content_path  TEXT,
            account_id    INTEGER NOT NULL REFERENCES accounts(id),
            title         TEXT NOT NULL,
            body_text     TEXT,
            tags          TEXT,
            image_paths   TEXT,
            cover_path    TEXT,
            platform_post_id TEXT,
            platform_status  TEXT DEFAULT 'unknown',
            post_url      TEXT,
            scheduled_at  TEXT,
            published_at  TEXT,
            status        TEXT NOT NULL DEFAULT 'draft',
            created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS metrics (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            publication_id  INTEGER NOT NULL REFERENCES publications(id),
            captured_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            views           INTEGER DEFAULT 0,
            likes           INTEGER DEFAULT 0,
            collects        INTEGER DEFAULT 0,
            comments        INTEGER DEFAULT 0,
            shares          INTEGER DEFAULT 0,
            notes           TEXT
        );
    """)
    conn.commit()

    # 迁移已有数据库（幂等）
    _migrate_schema(conn)

    # 初始化默认人设（幂等）
    _seed_personas(conn)


def _seed_personas(conn: sqlite3.Connection):
    personas = [
        ("chongxiaoyu", "虫小宇", "social-media/.claude/personas/chongxiaoyu/persona.md"),
        ("yuejian", "月见", "social-media/.claude/personas/yuejian/persona.md"),
    ]
    for pid, name, cfg in personas:
        conn.execute(
            "INSERT OR IGNORE INTO personas (id, name, config_path) VALUES (?, ?, ?)",
            (pid, name, cfg),
        )
    conn.commit()


def _get_schema_version(conn: sqlite3.Connection) -> int:
    """获取当前 schema 版本号"""
    try:
        row = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0


def _migrate_schema(conn: sqlite3.Connection):
    """为已有数据库添加新字段 + 修复旧约束（幂等）"""
    # 创建版本跟踪表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version     INTEGER PRIMARY KEY,
            applied_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.commit()

    current_version = _get_schema_version(conn)

    # Migration v1: 添加新字段
    if current_version < 1:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(publications)").fetchall()}
        migrations = [
            ("body_text",         "TEXT"),
            ("tags",              "TEXT"),
            ("image_paths",       "TEXT"),
            ("cover_path",        "TEXT"),
            ("platform_post_id",  "TEXT"),
            ("platform_status",   "TEXT DEFAULT 'unknown'"),
        ]
        for col, col_type in migrations:
            if col not in existing:
                conn.execute(f"ALTER TABLE publications ADD COLUMN {col} {col_type}")
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.commit()

    # Migration v2: 移除旧 CHECK 约束
    if current_version < 2:
        schema = conn.execute("SELECT sql FROM sqlite_master WHERE name='publications'").fetchone()
        if schema and schema[0] and "CHECK" in schema[0]:
            rows = conn.execute("SELECT * FROM publications").fetchall()
            col_names = [r[1] for r in conn.execute("PRAGMA table_info(publications)").fetchall()]
            try:
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute("ALTER TABLE publications RENAME TO publications_backup")
                conn.execute("""
                    CREATE TABLE publications (
                        id            INTEGER PRIMARY KEY AUTOINCREMENT,
                        content_path  TEXT,
                        account_id    INTEGER NOT NULL REFERENCES accounts(id),
                        title         TEXT NOT NULL,
                        body_text     TEXT,
                        tags          TEXT,
                        image_paths   TEXT,
                        cover_path    TEXT,
                        platform_post_id TEXT,
                        platform_status  TEXT DEFAULT 'unknown',
                        post_url      TEXT,
                        scheduled_at  TEXT,
                        published_at  TEXT,
                        status        TEXT NOT NULL DEFAULT 'draft',
                        created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                    )
                """)
                new_cols = [r[1] for r in conn.execute("PRAGMA table_info(publications)").fetchall()]
                for row in rows:
                    d = dict(zip(col_names, row))
                    vals = {c: d.get(c) for c in new_cols if c in d}
                    phs = ", ".join(["?"] * len(vals))
                    cn = ", ".join(vals.keys())
                    conn.execute(f"INSERT INTO publications ({cn}) VALUES ({phs})", list(vals.values()))
                conn.execute("DROP TABLE publications_backup")
                conn.commit()
            except Exception:
                # 回滚：如果新表创建失败，恢复备份表
                try:
                    conn.execute("DROP TABLE IF EXISTS publications")
                    conn.execute("ALTER TABLE publications_backup RENAME TO publications")
                    conn.commit()
                except Exception:
                    pass
                raise
            finally:
                conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("INSERT INTO schema_version (version) VALUES (2)")
        conn.commit()


# ─── 便捷查询 ───

def list_accounts(persona_id: str = None, platform: str = None, status: str = "active"):
    """列出账号，可按人设/平台/状态筛选"""
    conn = get_conn()
    sql = """
        SELECT a.*, p.name as persona_name
        FROM accounts a JOIN personas p ON a.persona_id = p.id
        WHERE 1=1
    """
    params = []
    if persona_id:
        sql += " AND a.persona_id = ?"
        params.append(persona_id)
    if platform:
        sql += " AND a.platform = ?"
        params.append(platform)
    if status:
        sql += " AND a.status = ?"
        params.append(status)
    return conn.execute(sql, params).fetchall()


def add_account(persona_id: str, platform: str, account_name: str, account_id: str = None):
    """添加账号"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO accounts (persona_id, platform, account_name, account_id) VALUES (?, ?, ?, ?)",
        (persona_id, platform, account_name, account_id),
    )
    conn.commit()


def create_publication(
    account_id: int,
    title: str,
    content_path: str = None,
    body_text: str = None,
    tags: str = None,
    image_paths: str = None,
    cover_path: str = None,
    status: str = "draft",
    published_at: str = None,
    post_url: str = None,
) -> int:
    """创建发布记录，返回记录 ID"""
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO publications
           (content_path, account_id, title, body_text, tags, image_paths, cover_path,
            status, published_at, post_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (content_path, account_id, title, body_text, tags, image_paths, cover_path,
         status, published_at, post_url),
    )
    conn.commit()
    return cur.lastrowid


def list_publications(persona_id: str = None, status: str = None, limit: int = 50):
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
    if persona_id:
        sql += " AND p.id = ?"
        params.append(persona_id)
    if status:
        sql += " AND pub.status = ?"
        params.append(status)
    sql += " ORDER BY pub.created_at DESC LIMIT ?"
    params.append(limit)
    return conn.execute(sql, params).fetchall()


if __name__ == "__main__":
    # 初始化数据库
    conn = get_conn()
    print(f"数据库已初始化: {DB_PATH}")
    for row in conn.execute("SELECT * FROM personas"):
        print(f"  人设: {row['name']} ({row['id']})")
