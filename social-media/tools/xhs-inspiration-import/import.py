from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv

    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    PROJECT_ROOT = Path(__file__).resolve().parents[3]


VAULT_PATH = Path(os.getenv("VAULT_PATH", "~/Desktop/vault")).expanduser()
DEFAULT_TARGET = VAULT_PATH / "00_Inbox" / "小红书" / "采集"


@dataclass
class NoteRecord:
    note_id: str | None
    title: str
    author: str | None
    source_url: str | None
    content: str
    likes: int | None
    collects: int | None
    comments: int | None
    shares: int | None
    publish_time: str | None
    comments_excerpt: list[str]
    raw: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将公开小红书采集结果导入 claude-workflows 灵感池")
    parser.add_argument("--input", required=True, help="输入 JSON / JSONL 文件或目录")
    parser.add_argument("--persona", default="yuejian", help="默认关联人设")
    parser.add_argument("--target-dir", default=str(DEFAULT_TARGET), help="导入目标目录")
    parser.add_argument("--source-name", default="agent:xhs-public-import", help="frontmatter source 字段")
    parser.add_argument("--limit", type=int, default=None, help="最多导入多少条")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写文件")
    return parser.parse_args()


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value.strip()).strip("-").lower()
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    cleaned = cleaned[:80].strip("-")
    return cleaned or "untitled"


def _pick(obj: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = obj.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _as_int(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    try:
        return int(str(value).replace(",", ""))
    except ValueError:
        return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _extract_author(raw: dict[str, Any]) -> str | None:
    user = raw.get("user") or raw.get("author") or raw.get("nickname")
    if isinstance(user, dict):
        return _pick(user, "nickname", "name", "user_name", "author_name")
    if isinstance(user, str):
        return user
    return None


def _extract_comments(raw: dict[str, Any]) -> list[str]:
    comments = _pick(raw, "comments", "comment_list", "commentList", "top_comments", "topComments")
    excerpts: list[str] = []
    for item in _as_list(comments):
        if isinstance(item, dict):
            content = _pick(item, "content", "text", "comment", "desc")
        else:
            content = str(item)
        if content:
            excerpts.append(str(content).strip())
        if len(excerpts) >= 5:
            break
    return excerpts


def _extract_content(raw: dict[str, Any]) -> str:
    blocks = [
        _pick(raw, "desc", "content", "note_content", "noteContent", "text"),
        _pick(raw, "title"),
    ]
    parts = [str(item).strip() for item in blocks if item]
    merged = "\n\n".join(dict.fromkeys(parts))
    return merged or "（采集结果未提供正文）"


def _extract_note(record: dict[str, Any]) -> NoteRecord:
    title = str(_pick(record, "title", "note_title", "noteTitle", "display_title") or "未命名笔记").strip()
    return NoteRecord(
        note_id=_pick(record, "note_id", "noteId", "id"),
        title=title,
        author=_extract_author(record),
        source_url=_pick(record, "note_url", "url", "noteUrl", "source_url"),
        content=_extract_content(record),
        likes=_as_int(_pick(record, "liked_count", "like_count", "likes", "digg_count")),
        collects=_as_int(_pick(record, "collected_count", "collect_count", "favorites", "favorite_count")),
        comments=_as_int(_pick(record, "comment_count", "comments_count", "comments")),
        shares=_as_int(_pick(record, "share_count", "shares")),
        publish_time=_pick(record, "time", "publish_time", "publishTime", "create_time", "createTime"),
        comments_excerpt=_extract_comments(record),
        raw=record,
    )


def _load_json_path(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        data = json.loads(text)
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            for key in ("data", "items", "list", "notes"):
                value = data.get(key)
                if isinstance(value, list):
                    rows = value
                    break
            else:
                rows = [data]
        else:
            rows = []
    return [row for row in rows if isinstance(row, dict)]


def load_records(input_path: Path) -> list[NoteRecord]:
    if not input_path.exists():
        raise FileNotFoundError(f"输入不存在: {input_path}")

    files: list[Path] = []
    if input_path.is_dir():
        files.extend(sorted(input_path.rglob("*.json")))
        files.extend(sorted(input_path.rglob("*.jsonl")))
    else:
        files.append(input_path)

    notes: list[NoteRecord] = []
    for file in files:
        for row in _load_json_path(file):
            notes.append(_extract_note(row))
    return notes


def _existing_markers(target_dir: Path) -> set[str]:
    markers: set[str] = set()
    if not target_dir.exists():
        return markers
    for path in target_dir.rglob("*.md"):
        raw = path.read_text(encoding="utf-8", errors="ignore")
        for marker in ("xhs_note_id:", "source_url:"):
            for line in raw.splitlines():
                if line.startswith(marker):
                    markers.add(line.split(":", 1)[1].strip())
    return markers


def _frontmatter_value(value: str) -> str:
    if re.search(r"[:\[\]#,{}]", value):
        return json.dumps(value, ensure_ascii=False)
    return value


def _render_frontmatter(note: NoteRecord, source_name: str, persona: str) -> str:
    created = datetime.now().strftime("%Y-%m-%d")
    tags = ["小红书采集", "公开数据"]
    if note.author:
        tags.append(note.author)
    lines = [
        "---",
        f"title: {_frontmatter_value(note.title)}",
        f"source: {_frontmatter_value(source_name)}",
        f"persona: {_frontmatter_value(persona)}",
        "platform: xiaohongshu",
        f"tags: [{', '.join(json.dumps(tag, ensure_ascii=False) for tag in tags)}]",
        f"created: {created}",
    ]
    if note.note_id:
        lines.append(f"xhs_note_id: {_frontmatter_value(note.note_id)}")
    if note.source_url:
        lines.append(f"source_url: {_frontmatter_value(note.source_url)}")
    if note.author:
        lines.append(f"author: {_frontmatter_value(note.author)}")
    lines.extend(
        [
            f"likes: {note.likes if note.likes is not None else ''}",
            f"collects: {note.collects if note.collects is not None else ''}",
            f"comments: {note.comments if note.comments is not None else ''}",
            f"shares: {note.shares if note.shares is not None else ''}",
            "---",
        ]
    )
    return "\n".join(lines)


def _render_body(note: NoteRecord) -> str:
    lines = [
        "# 采集标题",
        note.title,
        "",
        "# 来源账号",
        note.author or "未知作者",
        "",
        "# 原博正文",
        note.content.strip(),
        "",
        "# 公开互动数据",
        f"- 点赞：{note.likes if note.likes is not None else '未知'}",
        f"- 收藏：{note.collects if note.collects is not None else '未知'}",
        f"- 评论：{note.comments if note.comments is not None else '未知'}",
        f"- 分享：{note.shares if note.shares is not None else '未知'}",
    ]
    if note.publish_time:
        lines.append(f"- 发布时间：{note.publish_time}")
    if note.source_url:
        lines.extend(["", "# 原文链接", note.source_url])
    if note.comments_excerpt:
        lines.extend(["", "# 评论摘录"])
        for item in note.comments_excerpt:
            lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "# 可提炼灵感",
            "- 这条笔记最打动人的切口是什么？",
            "- 读者在评论区最在意的情绪或问题是什么？",
            "- 如果要改写成月见的人设口吻，最适合从哪一句切进去？",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def import_notes(notes: list[NoteRecord], target_dir: Path, persona: str, source_name: str, dry_run: bool) -> list[Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    existing = _existing_markers(target_dir)
    created: list[Path] = []
    date_prefix = datetime.now().strftime("%Y-%m-%d")

    for note in notes:
        marker_candidates = [item for item in (note.note_id, note.source_url) if item]
        if any(item in existing for item in marker_candidates):
            continue

        filename = f"{date_prefix}_{_slugify(note.title)}.md"
        path = target_dir / filename
        suffix = 1
        while path.exists():
            path = target_dir / f"{date_prefix}_{_slugify(note.title)}-{suffix}.md"
            suffix += 1

        content = _render_frontmatter(note, source_name=source_name, persona=persona) + "\n\n" + _render_body(note)
        if dry_run:
            print(f"[DRY-RUN] {path}")
        else:
            path.write_text(content, encoding="utf-8")
        created.append(path)
        existing.update(marker_candidates)
    return created


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser()
    target_dir = Path(args.target_dir).expanduser()
    records = load_records(input_path)
    if args.limit is not None:
        records = records[: args.limit]

    created = import_notes(
        notes=records,
        target_dir=target_dir,
        persona=args.persona,
        source_name=args.source_name,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "loaded": len(records),
                "imported": len(created),
                "target_dir": str(target_dir),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
