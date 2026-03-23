from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app import agent_wrapper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="本地内容审核包装脚本，供 Codex/自动化调用")
    parser.add_argument("--persona", required=True, help="人设 ID，例如 yuejian")
    parser.add_argument("--platform", required=True, help="平台 ID，例如 xiaohongshu")
    parser.add_argument("--input-file", required=True, help="待审核稿件文件路径")
    parser.add_argument("--output-file", help="将审核 JSON 写入指定文件", default=None)
    return parser


async def _emit(event: str, payload: dict[str, object]) -> None:
    print(json.dumps({"event": event, "payload": payload}, ensure_ascii=False), file=sys.stderr, flush=True)


async def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    input_file = Path(args.input_file).expanduser()
    if not input_file.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_file}")
    body = input_file.read_text(encoding="utf-8")

    system_prompt, prompt = agent_wrapper._review_prompt(
        persona=args.persona,
        platform=args.platform,
        draft=body,
    )
    last_error: Exception | None = None
    raw = None
    for attempt in range(1, 4):
        try:
            raw = await agent_wrapper._run_claude(
                prompt=prompt,
                system_prompt=system_prompt,
                timeout_seconds=180,
                on_event=_emit,
                label="reviewer-local",
            )
            break
        except RuntimeError as exc:
            last_error = exc
            await _emit("task.retry", {"attempt": attempt, "error": str(exc)})
            if attempt == 3:
                raise
            await asyncio.sleep(3 * attempt)
    if raw is None:
        raise RuntimeError(str(last_error or "内容审核失败"))
    result = agent_wrapper._parse_review_result(raw)

    if args.output_file:
        output_path = Path(args.output_file).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        await _emit("task.output_file", {"path": str(output_path)})

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
