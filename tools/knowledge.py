#!/usr/bin/env python3
"""
知识检索：在 data/content/knowledge/ 下搜索文件名和全文内容。
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import PROJECT_ROOT

KNOWLEDGE_DIR = os.path.join(PROJECT_ROOT, "data", "content", "knowledge")


def _tokenize(text: str) -> list:
    """将文本拆分为搜索词。"""
    return [w.lower() for w in re.split(r"\s+", text.strip()) if w]


def _snippet(content: str, keywords: list, context_chars: int = 100) -> str:
    """从内容中提取包含关键词的片段。"""
    content_lower = content.lower()
    best_pos = -1
    for kw in keywords:
        pos = content_lower.find(kw)
        if pos >= 0:
            best_pos = pos
            break
    if best_pos < 0:
        return content[:200].strip()
    start = max(0, best_pos - context_chars)
    end = min(len(content), best_pos + context_chars)
    snippet = content[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    return snippet


def search(query: str, scopes: list = None, limit: int = 5) -> list:
    """搜索知识库文件。"""
    keywords = _tokenize(query)
    if not keywords:
        return []

    # 确定搜索目录
    search_dirs = []
    if scopes:
        for scope in scopes:
            d = os.path.join(KNOWLEDGE_DIR, scope.strip())
            if os.path.isdir(d):
                search_dirs.append(d)
    if not search_dirs:
        search_dirs = [KNOWLEDGE_DIR]

    results = []
    for search_dir in search_dirs:
        for root, dirs, files in os.walk(search_dir):
            for fname in files:
                if fname.startswith("."):
                    continue
                fpath = os.path.join(root, fname)
                score = 0.0

                # 文件名匹配
                fname_lower = fname.lower()
                for kw in keywords:
                    if kw in fname_lower:
                        score += 2.0

                # 全文搜索
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except Exception:
                    continue

                content_lower = content.lower()
                for kw in keywords:
                    count = content_lower.count(kw)
                    if count > 0:
                        score += min(count, 10) * 0.5  # cap per keyword

                if score > 0:
                    results.append({
                        "file_path": fpath,
                        "score": score,
                        "snippet": _snippet(content, keywords),
                    })

    # 按分数排序
    results.sort(key=lambda x: x["score"], reverse=True)
    # 移除 score 字段后返回
    for r in results[:limit]:
        del r["score"]
    return results[:limit]


def main():
    parser = argparse.ArgumentParser(description="知识检索")
    parser.add_argument("command", choices=["search"], help="子命令")
    parser.add_argument("query", help="搜索关键词")
    parser.add_argument("--scope", default=None, help="搜索范围（逗号分隔，如 wiki,research）")
    parser.add_argument("--limit", type=int, default=5, help="返回数量上限")
    args = parser.parse_args()

    scopes = [s.strip() for s in args.scope.split(",")] if args.scope else None

    try:
        results = search(args.query, scopes, args.limit)
        print(json.dumps(results, ensure_ascii=False))
        if not results:
            print("未找到匹配结果", file=sys.stderr)
        else:
            print(f"找到 {len(results)} 条结果", file=sys.stderr)
    except Exception as e:
        print(f"搜索失败: {e}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
