from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app import agent_wrapper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="本地内容生成包装脚本，供 Codex/自动化调用")
    parser.add_argument("--content-id", help="可选内容 ID，仅用于外层追踪", default=None)
    parser.add_argument("--persona", required=True, help="人设 ID，例如 yuejian")
    parser.add_argument("--platform", required=True, help="平台 ID，例如 xiaohongshu")
    parser.add_argument("--input", dest="input_text", help="直接传入素材文本", default=None)
    parser.add_argument("--input-path", help="素材文件路径，可为 VAULT 相对路径或绝对路径", default=None)
    parser.add_argument("--instruction", help="额外生成指令", default=None)
    parser.add_argument("--output-file", help="将成稿额外写入指定文件", default=None)
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="stdout 输出格式，默认 markdown",
    )
    return parser


async def _emit(event: str, payload: dict[str, object]) -> None:
    print(json.dumps({"event": event, "payload": payload}, ensure_ascii=False), file=sys.stderr, flush=True)


async def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.input_text and not args.input_path:
        parser.error("必须提供 --input 或 --input-path 之一")

    result = await agent_wrapper.run_content_task_local(
        persona=args.persona,
        platform=args.platform,
        input_text=args.input_text,
        input_path=args.input_path,
        instruction=args.instruction,
        on_event=_emit,
    )

    body = str(result["body"]).strip() + "\n"
    if args.output_file:
        output_path = Path(args.output_file).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(body, encoding="utf-8")
        await _emit("task.output_file", {"path": str(output_path)})

    if args.format == "json":
        print(
            json.dumps(
                {
                    "content_id": args.content_id,
                    "title": result["title"],
                    "body": result["body"],
                    "source_label": result.get("source_label"),
                    "output_file": args.output_file,
                },
                ensure_ascii=False,
            )
        )
    else:
        print(body, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
