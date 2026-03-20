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

    prompt = (
        "请基于以下素材生成社媒内容。\n\n"
        f"目标人设: {persona}\n"
        f"目标平台: {platform}\n\n"
        "素材如下：\n"
        f"{source}\n\n"
        f"请按参数理解为 --account {persona} --platform {platform}。"
    )
    command = ["claude", "-p", prompt]
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
        fallback_body = (
            f"# {persona} / {platform} 待生成内容\n\n"
            f"{source.strip() or '请安装并配置 claude CLI 后重试。'}"
        )
        return {"title": "待生成内容", "body": fallback_body, "review_score": None}

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        await on_event("task.output", {"stream": "stderr", "text": "claude 执行超时，已回退到本地测试内容。"})
        return _fallback_content(source=source, persona=persona, platform=platform)
    if stdout:
        await on_event("task.output", {"stream": "stdout", "text": stdout.decode("utf-8", errors="ignore")})
    if stderr:
        await on_event("task.output", {"stream": "stderr", "text": stderr.decode("utf-8", errors="ignore")})
    if process.returncode != 0:
        await on_event("task.output", {"stream": "stderr", "text": f"claude 执行失败，已回退到本地测试内容。exit={process.returncode}"})
        return _fallback_content(source=source, persona=persona, platform=platform)

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

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        await on_event("task.output", {"stream": "stderr", "text": "claude 修改超时，回退到本地改写结果。"})
        return f"{current_content.rstrip()}\n\n> 修改指令：{instruction}\n"
    if stdout:
        await on_event("task.output", {"stream": "stdout", "text": stdout.decode("utf-8", errors="ignore")})
    if stderr:
        await on_event("task.output", {"stream": "stderr", "text": stderr.decode("utf-8", errors="ignore")})
    if process.returncode != 0:
        await on_event("task.output", {"stream": "stderr", "text": f"claude 修改失败，回退到本地改写结果。exit={process.returncode}"})
        return f"{current_content.rstrip()}\n\n> 修改指令：{instruction}\n"
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

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        return {
            "recommendations": [
                {"content_id": item["content_id"], "title": item["title"], "reason": "Claude 推荐超时，按最近定稿排序兜底。"}
                for item in candidates[: min(5, len(candidates))]
            ]
        }
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


def _fallback_content(*, source: str, persona: str, platform: str) -> dict[str, object]:
    title = "待人工确认标题"
    body = (
        f"# {title}\n\n"
        f"这是 {persona} 面向 {platform} 的本地测试草稿。\n\n"
        "## 核心观点\n"
        f"{source.strip() or '当前未提供素材。'}\n\n"
        "## 下一步\n"
        "请确认 Claude CLI 配置后，再替换为真实生成内容。"
    )
    return {"title": title, "body": body, "review_score": 0}
