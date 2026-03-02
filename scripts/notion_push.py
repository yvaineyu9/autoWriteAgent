#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notion 推送工具
自动创建数据库 + 推送内容到对应平台数据库

注意：需要设置环境变量 NOTION_API_KEY
初始化时还需要 NOTION_PAGE_ID 或 --page-id 参数

Notion 推送与本地仓库的协作方式待进一步研究和探索。
当前状态：脚本可用，但尚未深度集成到内容工厂的自动化流程中。
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from notion_client import Client

CONFIG_DIR = os.path.expanduser("~/.config/social_media")
CONFIG_FILE = os.path.join(CONFIG_DIR, "notion_databases.json")

# ── 数据库 schema 定义 ────────────────────────────────────────

DATABASES = {
    "xiaohongshu": {
        "title": "小红书内容库",
        "icon": "📕",
        "properties": {
            "标题": {"title": {}},
            "内容": {"rich_text": {}},
            "话题标签": {"multi_select": {}},
            "状态": {
                "select": {
                    "options": [
                        {"name": "草稿", "color": "gray"},
                        {"name": "已发布", "color": "green"},
                    ]
                }
            },
            "来源": {
                "select": {
                    "options": [
                        {"name": "播客", "color": "blue"},
                        {"name": "短想法", "color": "yellow"},
                        {"name": "文章", "color": "purple"},
                        {"name": "润色", "color": "orange"},
                    ]
                }
            },
            "创建时间": {"date": {}},
        },
    },
    "wechat": {
        "title": "公众号内容库",
        "icon": "💚",
        "properties": {
            "标题": {"title": {}},
            "内容": {"rich_text": {}},
            "摘要": {"rich_text": {}},
            "状态": {
                "select": {
                    "options": [
                        {"name": "草稿", "color": "gray"},
                        {"name": "已发布", "color": "green"},
                    ]
                }
            },
            "来源": {
                "select": {
                    "options": [
                        {"name": "播客", "color": "blue"},
                        {"name": "短想法", "color": "yellow"},
                        {"name": "文章", "color": "purple"},
                        {"name": "润色", "color": "orange"},
                    ]
                }
            },
            "创建时间": {"date": {}},
        },
    },
    "twitter": {
        "title": "Twitter 内容库",
        "icon": "🐦",
        "properties": {
            "内容": {"title": {}},
            "Thread": {"rich_text": {}},
            "Hashtags": {"multi_select": {}},
            "状态": {
                "select": {
                    "options": [
                        {"name": "草稿", "color": "gray"},
                        {"name": "已发布", "color": "green"},
                    ]
                }
            },
            "来源": {
                "select": {
                    "options": [
                        {"name": "播客", "color": "blue"},
                        {"name": "短想法", "color": "yellow"},
                        {"name": "文章", "color": "purple"},
                        {"name": "润色", "color": "orange"},
                    ]
                }
            },
            "创建时间": {"date": {}},
        },
    },
    "podcast": {
        "title": "播客笔记",
        "icon": "🎙️",
        "properties": {
            "标题": {"title": {}},
            "播客名": {"rich_text": {}},
            "链接": {"url": {}},
            "转录文本": {"rich_text": {}},
            "总结": {"rich_text": {}},
            "创建时间": {"date": {}},
        },
    },
}


# ── 配置管理 ──────────────────────────────────────────────────

def load_config():
    """加载已保存的数据库 ID"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(config):
    """保存数据库 ID 到配置文件"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_client():
    """获取 Notion client"""
    api_key = os.environ.get("NOTION_API_KEY", "")
    if not api_key:
        print("错误: 未设置 NOTION_API_KEY 环境变量", file=sys.stderr)
        sys.exit(1)
    return Client(auth=api_key)


# ── 数据库创建 ────────────────────────────────────────────────

def init_databases(page_id=None):
    """创建所有平台数据库"""
    if not page_id:
        page_id = os.environ.get("NOTION_PAGE_ID", "")
    if not page_id:
        print("错误: 未指定父页面 ID（设置 NOTION_PAGE_ID 环境变量或用 --page-id 参数）",
              file=sys.stderr)
        sys.exit(1)

    client = get_client()
    config = load_config()

    for platform, schema in DATABASES.items():
        if platform in config:
            print(f"[跳过] {schema['title']} 已存在 (ID: {config[platform]})")
            continue

        print(f"[创建] {schema['title']}...")
        db = client.databases.create(
            parent={"type": "page_id", "page_id": page_id},
            title=[{"type": "text", "text": {"content": schema["title"]}}],
            icon={"type": "emoji", "emoji": schema["icon"]},
            properties=schema["properties"],
        )
        config[platform] = db["id"]
        print(f"     完成: {db['id']}")

    save_config(config)
    print(f"\n数据库配置已保存到: {CONFIG_FILE}")
    return config


# ── Notion rich_text 工具 ─────────────────────────────────────

def make_rich_text(text, max_length=2000):
    """
    将文本转为 Notion rich_text 数组。
    Notion API 限制单个 rich_text 块最多 2000 字符。
    """
    if not text:
        return []
    chunks = []
    for i in range(0, len(text), max_length):
        chunks.append({
            "type": "text",
            "text": {"content": text[i:i + max_length]},
        })
    return chunks


# ── 推送内容 ──────────────────────────────────────────────────

def push_content(platform, title, content, source=None, tags=None,
                 summary=None, podcast_name=None, podcast_url=None,
                 transcript=None):
    """推送内容到指定平台的 Notion 数据库"""
    config = load_config()
    if platform not in config:
        print(f"错误: {platform} 数据库尚未创建，请先运行 --init", file=sys.stderr)
        sys.exit(1)

    client = get_client()
    db_id = config[platform]
    now = datetime.now(timezone.utc).isoformat()

    # 构建 properties
    properties = {}

    if platform == "xiaohongshu":
        properties["标题"] = {"title": make_rich_text(title)}
        properties["内容"] = {"rich_text": make_rich_text(content)}
        if tags:
            properties["话题标签"] = {
                "multi_select": [{"name": t.strip()} for t in tags.split(",")]
            }
        if source:
            properties["来源"] = {"select": {"name": source}}
        properties["状态"] = {"select": {"name": "草稿"}}
        properties["创建时间"] = {"date": {"start": now}}

    elif platform == "wechat":
        properties["标题"] = {"title": make_rich_text(title)}
        properties["内容"] = {"rich_text": make_rich_text(content)}
        if summary:
            properties["摘要"] = {"rich_text": make_rich_text(summary)}
        if source:
            properties["来源"] = {"select": {"name": source}}
        properties["状态"] = {"select": {"name": "草稿"}}
        properties["创建时间"] = {"date": {"start": now}}

    elif platform == "twitter":
        properties["内容"] = {"title": make_rich_text(title)}
        if content and content != title:
            properties["Thread"] = {"rich_text": make_rich_text(content)}
        if tags:
            properties["Hashtags"] = {
                "multi_select": [{"name": t.strip()} for t in tags.split(",")]
            }
        if source:
            properties["来源"] = {"select": {"name": source}}
        properties["状态"] = {"select": {"name": "草稿"}}
        properties["创建时间"] = {"date": {"start": now}}

    elif platform == "podcast":
        properties["标题"] = {"title": make_rich_text(title)}
        if podcast_name:
            properties["播客名"] = {"rich_text": make_rich_text(podcast_name)}
        if podcast_url:
            properties["链接"] = {"url": podcast_url}
        if content:
            properties["总结"] = {"rich_text": make_rich_text(content)}
        if transcript:
            properties["转录文本"] = {"rich_text": make_rich_text(transcript)}
        properties["创建时间"] = {"date": {"start": now}}

    # 创建页面
    page = client.pages.create(
        parent={"database_id": db_id},
        properties=properties,
    )

    page_url = page.get("url", "")
    print(f"[推送成功] {DATABASES[platform]['title']}: {title[:30]}...")
    print(f"     URL: {page_url}")
    return page_url


# ── CLI ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Notion 推送工具")

    parser.add_argument("--init", action="store_true",
                        help="初始化：创建所有平台数据库")
    parser.add_argument("--page-id", default=None,
                        help="Notion 父页面 ID（创建数据库用）")

    parser.add_argument("--platform", choices=["xiaohongshu", "wechat", "twitter", "podcast"],
                        help="目标平台")
    parser.add_argument("--title", default="", help="标题")
    parser.add_argument("--content", default="", help="正文内容")
    parser.add_argument("--file", default=None, help="从文件读取正文内容")
    parser.add_argument("--source", default=None, help="内容来源（播客/短想法/文章/润色）")
    parser.add_argument("--tags", default=None, help="标签，逗号分隔")
    parser.add_argument("--summary", default=None, help="摘要（公众号用）")
    parser.add_argument("--podcast-name", default=None, help="播客名称")
    parser.add_argument("--podcast-url", default=None, help="播客链接")
    parser.add_argument("--transcript-file", default=None, help="转录文本文件路径（播客笔记用）")

    args = parser.parse_args()

    if args.init:
        init_databases(args.page_id)
        return

    if not args.platform:
        print("错误: 请指定 --platform", file=sys.stderr)
        sys.exit(1)

    # 读取内容
    content = args.content
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()

    if not args.title and not content:
        print("错误: 请提供 --title 或 --content", file=sys.stderr)
        sys.exit(1)

    # 读取转录文本
    transcript = None
    if args.transcript_file:
        with open(args.transcript_file, "r", encoding="utf-8") as f:
            transcript = f.read()

    push_content(
        platform=args.platform,
        title=args.title,
        content=content,
        source=args.source,
        tags=args.tags,
        summary=args.summary,
        podcast_name=args.podcast_name,
        podcast_url=args.podcast_url,
        transcript=transcript,
    )


if __name__ == "__main__":
    main()
