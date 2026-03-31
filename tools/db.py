#!/usr/bin/env python3
"""
数据库管理：连接、schema migration、通用查询。
被其他 tool 引用，不直接由 skill 调用。
"""

import os
import sqlite3
import sys

# 数据库路径：项目根目录/data/autowrite.db
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "autowrite.db")

SCHEMA_VERSION = 1

SCHEMA_SQL = """
-- 灵感
CREATE TABLE IF NOT EXISTS ideas (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    tags          TEXT,
    source        TEXT DEFAULT 'human',
    status        TEXT DEFAULT 'pending',
    file_path     TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 内容（生命周期主表）
CREATE TABLE IF NOT EXISTS contents (
    content_id    TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    persona_id    TEXT NOT NULL,
    platform      TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'draft',
    file_path     TEXT NOT NULL,
    review_score  INTEGER,
    review_json   TEXT,
    source_idea   TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 状态变更日志
CREATE TABLE IF NOT EXISTS status_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id    TEXT NOT NULL,
    from_status   TEXT,
    to_status     TEXT NOT NULL,
    operator      TEXT NOT NULL,
    note          TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (content_id) REFERENCES contents(content_id)
);

-- 发布记录
CREATE TABLE IF NOT EXISTS publications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id    TEXT NOT NULL,
    persona_id    TEXT NOT NULL,
    platform      TEXT NOT NULL,
    account_id    TEXT,
    status        TEXT DEFAULT 'draft',
    post_url      TEXT,
    published_at  TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (content_id) REFERENCES contents(content_id)
);

-- 数据采集
CREATE TABLE IF NOT EXISTS metrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id INTEGER NOT NULL,
    views         INTEGER DEFAULT 0,
    likes         INTEGER DEFAULT 0,
    collects      INTEGER DEFAULT 0,
    comments      INTEGER DEFAULT 0,
    shares        INTEGER DEFAULT 0,
    captured_at   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (publication_id) REFERENCES publications(id)
);

-- 人设
CREATE TABLE IF NOT EXISTS personas (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 平台账号
CREATE TABLE IF NOT EXISTS accounts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id    TEXT NOT NULL,
    platform      TEXT NOT NULL,
    account_name  TEXT NOT NULL,
    active        INTEGER DEFAULT 1,
    FOREIGN KEY (persona_id) REFERENCES personas(id)
);

-- 每日日记
CREATE TABLE IF NOT EXISTS daily_logs (
    date          TEXT PRIMARY KEY,
    plan          TEXT,
    output        TEXT,
    notes         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 执行痕迹
CREATE TABLE IF NOT EXISTS traces (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       TEXT NOT NULL,
    event_type    TEXT NOT NULL,
    message       TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_traces_task ON traces(task_id);

-- schema 版本跟踪
CREATE TABLE IF NOT EXISTS schema_version (
    version       INTEGER PRIMARY KEY
);
"""


def get_connection() -> sqlite3.Connection:
    """获取数据库连接，自动执行 migration。"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection):
    """检查 schema 版本，执行必要的 migration。"""
    # 检查 schema_version 表是否存在
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    if cursor.fetchone() is None:
        # 全新数据库，执行完整 schema
        conn.executescript(SCHEMA_SQL)
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
        return

    row = conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
    current = row["v"] if row else 0

    if current >= SCHEMA_VERSION:
        return

    # 未来的增量 migration 在这里添加
    # if current < 2:
    #     conn.executescript(MIGRATION_V2_SQL)

    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()


def init_db():
    """初始化数据库，用于命令行调用。"""
    conn = get_connection()
    print(f"数据库已初始化: {DB_PATH}", file=sys.stderr)

    # 显示表信息
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    result = {"db_path": DB_PATH, "tables": [r["name"] for r in tables]}

    import json
    print(json.dumps(result, ensure_ascii=False))
    conn.close()


if __name__ == "__main__":
    init_db()
