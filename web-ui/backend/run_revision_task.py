from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app import agent_wrapper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="本地内容修改包装脚本，供 Codex/自动化调用")
    parser.add_argument("--content-id", help="可选内容 ID，仅用于外层追踪", default=None)
    parser.add_argument("--persona", required=True, help="人设 ID，例如 yuejian")
    parser.add_argument("--platform", required=True, help="平台 ID，例如 xiaohongshu")
    parser.add_argument("--instruction", required=True, help="修改指令")
    parser.add_argument("--input-file", required=True, help="当前稿件文件路径")
    parser.add_argument("--output-file", help="将修改结果写入指定文件；默认覆盖 input-file", default=None)
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

    input_file = Path(args.input_file).expanduser()
    if not input_file.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_file}")
    current_content = input_file.read_text(encoding="utf-8")

    revised = await agent_wrapper.run_revision_task(
        persona=args.persona,
        platform=args.platform,
        instruction=args.instruction,
        current_content=current_content,
        on_event=_emit,
    )

    output_path = Path(args.output_file).expanduser() if args.output_file else input_file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(revised.strip() + "\n", encoding="utf-8")
    await _emit("task.output_file", {"path": str(output_path)})

    if args.format == "json":
        print(
            json.dumps(
                {
                    "content_id": args.content_id,
                    "output_file": str(output_path),
                    "body": revised,
                },
                ensure_ascii=False,
            )
        )
    else:
        print(revised.strip() + "\n", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
