#!/usr/bin/env python3
"""
灵感入库：将灵感记录到 inbox 文件和 ideas 表。
"""

import argparse
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_connection, PROJECT_ROOT

INBOX_DIR = os.path.join(PROJECT_ROOT, "data", "content", "inbox")


def main():
    parser = argparse.ArgumentParser(description="灵感入库")
    parser.add_argument("--title", required=True, help="灵感标题")
    parser.add_argument("--content", required=True, help="灵感内容")
    parser.add_argument("--tags", required=True, help="标签（逗号分隔）")
    args = parser.parse_args()

    idea_id = str(uuid.uuid4())
    os.makedirs(INBOX_DIR, exist_ok=True)
    abs_path = os.path.join(INBOX_DIR, f"{idea_id}.md")
    # 数据库存相对路径（相对于 data/content/）
    rel_path = f"inbox/{idea_id}.md"

    conn = None
    try:
        # 写入文件
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(args.content)

        # 写入数据库
        conn = get_connection()
        conn.execute(
            """INSERT INTO ideas (id, title, tags, file_path)
               VALUES (?, ?, ?, ?)""",
            (idea_id, args.title, args.tags, rel_path),
        )
        conn.commit()

        print(f"灵感已入库: {idea_id}", file=sys.stderr)
        result = {"idea_id": idea_id, "file_path": rel_path}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)

    except Exception as e:
        print(f"灵感入库失败: {e}", file=sys.stderr)
        sys.exit(3)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
