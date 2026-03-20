from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from .config import get_settings


settings = get_settings()


async def run_content_task(
    *,
    content_id: str,
    persona: str,
    platform: str,
    input_text: str | None,
    input_path: str | None,
    on_event,
) -> dict[str, object]:
    await on_event("task.progress", {"message": "准备写作任务"})
    source = input_text or ""
    if input_path:
        source_path = settings.project_root / input_path
        if source_path.exists():
            source = source_path.read_text(encoding="utf-8")
    await on_event("task.output", {"stream": "system", "text": f"persona={persona} platform={platform}"})

    command = [
        "claude",
        "-p",
        f"{source}\n\n--account {persona} --platform {platform}",
    ]
    env = os.environ.copy()
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(settings.project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError:
        await on_event("task.output", {"stream": "stderr", "text": "claude 命令不可用，任务包装层已就绪但未执行真实生成。"})
        return {
            "title": "待生成内容",
            "body": source.strip() or "请安装并配置 claude CLI 后重试。",
            "review_score": None,
        }

    stdout, stderr = await process.communicate()
    if stdout:
        await on_event("task.output", {"stream": "stdout", "text": stdout.decode("utf-8", errors="ignore")})
    if stderr:
        await on_event("task.output", {"stream": "stderr", "text": stderr.decode("utf-8", errors="ignore")})
    if process.returncode != 0:
        raise RuntimeError(f"claude content task failed with exit code {process.returncode}")

    body = stdout.decode("utf-8", errors="ignore").strip()
    title = _extract_title(body) or "未命名内容"
    return {"title": title, "body": body, "review_score": None}


async def run_revision_task(*, instruction: str, current_content: str, on_event) -> str:
    await on_event("task.progress", {"message": "准备修改任务"})
    command = [
        "claude",
        "-p",
        f"请根据以下指令修改内容：\n指令：{instruction}\n\n当前内容：\n{current_content}",
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(settings.project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
    except FileNotFoundError:
        await on_event("task.output", {"stream": "stderr", "text": "claude 命令不可用，返回原始内容。"})
        return current_content

    stdout, stderr = await process.communicate()
    if stdout:
        await on_event("task.output", {"stream": "stdout", "text": stdout.decode("utf-8", errors="ignore")})
    if stderr:
        await on_event("task.output", {"stream": "stderr", "text": stderr.decode("utf-8", errors="ignore")})
    if process.returncode != 0:
        raise RuntimeError(f"claude revision task failed with exit code {process.returncode}")
    return stdout.decode("utf-8", errors="ignore").strip() or current_content


async def run_selection_recommendation(*, goal: str, candidates: list[dict[str, object]], on_event) -> dict[str, object]:
    await on_event("task.progress", {"message": "生成选稿建议"})
    prompt = {
        "goal": goal,
        "candidates": candidates,
    }
    command = ["claude", "-p", f"请根据以下 JSON 输出推荐列表和理由，返回 JSON。\n{json.dumps(prompt, ensure_ascii=False)}"]
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(settings.project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
    except FileNotFoundError:
        return {
            "recommendations": [
                {"content_id": item["content_id"], "title": item["title"], "reason": "claude CLI 不可用，按最近定稿排序兜底。"}
                for item in candidates[: min(5, len(candidates))]
            ]
        }

    stdout, stderr = await process.communicate()
    if stderr:
        await on_event("task.output", {"stream": "stderr", "text": stderr.decode("utf-8", errors="ignore")})
    if process.returncode != 0:
        raise RuntimeError(f"claude selection task failed with exit code {process.returncode}")
    text = stdout.decode("utf-8", errors="ignore").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _extract_title(body: str) -> str | None:
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return None
