#!/usr/bin/env python3
"""
初始化月见账号 + 导入已发布内容到 distribution.db

用法：
    VAULT_PATH=~/Desktop/vault python3 init_yuejian.py

功能：
    1. 添加月见的小红书账号
    2. 扫描 60_Published/social-media/yuejian/ 下所有 .md 文件
    3. 从 frontmatter + 文件名提取信息
    4. 为每篇创建 publications 记录
"""

import re
import sys
from pathlib import Path
from datetime import datetime
from db import get_conn, add_account, create_publication

import os

VAULT_PATH = Path(os.getenv("VAULT_PATH", "~/Desktop/vault")).expanduser()
PUBLISHED_DIR = VAULT_PATH / "60_Published" / "social-media"


def parse_frontmatter(content: str) -> dict:
    """解析 Markdown frontmatter"""
    fm = {}
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if match:
        for line in match.group(1).strip().split('\n'):
            if ':' in line:
                key, val = line.split(':', 1)
                fm[key.strip()] = val.strip()
    return fm


def extract_title_from_content(content: str) -> str:
    """从 Markdown 正文提取 # 标题"""
    for line in content.split('\n'):
        line = line.strip()
        if line.startswith('# ') and not line.startswith('## '):
            return line[2:].strip()
    return ""


def parse_filename(filename: str) -> dict:
    """从文件名提取日期和标题：2026-03-12_标题_小红书.md"""
    name = filename.replace('.md', '')
    parts = name.split('_', 1)
    result = {}
    if len(parts) >= 1 and re.match(r'\d{4}-\d{2}-\d{2}', parts[0]):
        result['date'] = parts[0]
    if len(parts) >= 2:
        # 去掉末尾的 _小红书
        title_part = parts[1]
        if title_part.endswith('_小红书'):
            title_part = title_part[:-4]
        elif title_part.endswith('_公众号'):
            title_part = title_part[:-4]
        elif title_part.endswith('_Twitter'):
            title_part = title_part[:-8]
        result['title'] = title_part
    return result


def extract_tags_from_content(content: str) -> list:
    """从正文中提取 #标签"""
    tags = re.findall(r'#([^\s#]+)', content)
    # 过滤掉 Markdown 标题
    return [t for t in tags if not t.startswith(' ')]


def main():
    conn = get_conn()

    # ─── Step 1：添加月见小红书账号（幂等） ───

    existing = conn.execute(
        "SELECT id FROM accounts WHERE persona_id = 'yuejian' AND platform = 'xiaohongshu'"
    ).fetchone()

    if existing:
        account_id = existing['id']
        print(f"月见小红书账号已存在 (ID: {account_id})")
    else:
        add_account("yuejian", "xiaohongshu", "月见-关系小精灵")
        account_id = conn.execute(
            "SELECT id FROM accounts WHERE persona_id = 'yuejian' AND platform = 'xiaohongshu'"
        ).fetchone()['id']
        print(f"已添加月见小红书账号 (ID: {account_id})")

    # ─── Step 2：扫描已发布内容 ───

    published_dirs = [
        PUBLISHED_DIR / "yuejian",     # yuejian 子目录
        PUBLISHED_DIR,                  # 根目录（早期帖子）
    ]

    md_files = []
    for d in published_dirs:
        if d.exists():
            for f in sorted(d.glob("*.md")):
                md_files.append(f)

    if not md_files:
        print("未找到已发布的 .md 文件")
        return

    print(f"\n找到 {len(md_files)} 个已发布文件")

    # ─── Step 3：逐个导入 ───

    imported = 0
    skipped = 0

    for md_file in md_files:
        content = md_file.read_text(encoding='utf-8')
        fm = parse_frontmatter(content)
        file_info = parse_filename(md_file.name)

        # 提取标题
        title = extract_title_from_content(content) or file_info.get('title', md_file.stem)

        # 提取日期
        pub_date = fm.get('date', file_info.get('date', ''))
        if pub_date:
            published_at = f"{pub_date} 12:00:00"
        else:
            published_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 判断平台
        platform_hint = fm.get('platform', '')
        if '小红书' not in platform_hint and '小红书' not in md_file.name:
            # 非小红书内容跳过（如 Twitter、公众号）
            print(f"  跳过非小红书: {md_file.name}")
            skipped += 1
            continue

        # content_path 用相对于 vault 的路径
        content_path = str(md_file.relative_to(VAULT_PATH))

        # 检查去重
        existing_pub = conn.execute(
            "SELECT id FROM publications WHERE content_path = ?",
            (content_path,)
        ).fetchone()

        if existing_pub:
            print(f"  已存在: {md_file.name} (#{existing_pub['id']})")
            skipped += 1
            continue

        # 提取标签
        tags = extract_tags_from_content(content)
        tags_str = ','.join(tags[:10]) if tags else None

        # 创建记录
        pub_id = create_publication(
            account_id=account_id,
            title=title,
            content_path=content_path,
            tags=tags_str,
            status="published",
            published_at=published_at,
        )
        imported += 1
        print(f"  ✅ 导入: {title} (#{pub_id})")

    # ─── 汇总 ───

    print(f"\n{'='*50}")
    print(f"导入完成: {imported} 条新增, {skipped} 条跳过")

    total = conn.execute(
        """SELECT COUNT(*) as cnt FROM publications pub
           JOIN accounts a ON pub.account_id = a.id
           WHERE a.persona_id = 'yuejian'"""
    ).fetchone()['cnt']
    print(f"月见总发布记录: {total} 条")


if __name__ == "__main__":
    main()
