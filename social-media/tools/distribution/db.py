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


def get_conn() -> sqlite3.Connection:
    """获取数据库连接，自动建表"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _init_schema(conn)
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
            post_url      TEXT,
            scheduled_at  TEXT,
            published_at  TEXT,
            status        TEXT NOT NULL DEFAULT 'draft'
                          CHECK(status IN ('draft', 'published', 'tracking', 'archived')),
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


if __name__ == "__main__":
    # 初始化数据库
    conn = get_conn()
    print(f"数据库已初始化: {DB_PATH}")
    for row in conn.execute("SELECT * FROM personas"):
        print(f"  人设: {row['name']} ({row['id']})")
