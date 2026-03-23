from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from .config import get_settings


settings = get_settings()
PROJECT_ROOT = settings.project_root
SOCIAL_MEDIA_ROOT = PROJECT_ROOT / "social-media"
SOCIAL_CLAUDE_ROOT = SOCIAL_MEDIA_ROOT / ".claude"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _persona_paths(persona: str, platform: str) -> tuple[Path, Path]:
    persona_path = SOCIAL_CLAUDE_ROOT / "personas" / persona / "persona.md"
    platform_path = SOCIAL_CLAUDE_ROOT / "personas" / persona / "platforms" / f"{platform}.md"
    if not persona_path.exists():
        raise FileNotFoundError(f"persona 不存在: {persona_path}")
    if not platform_path.exists():
        raise FileNotFoundError(f"platform 配置不存在: {platform_path}")
    return persona_path, platform_path


async def _run_claude(
    *,
    prompt: str,
    system_prompt: str,
    timeout_seconds: int,
    on_event,
    label: str,
) -> str:
    command = [
        "claude",
        "-p",
        "--permission-mode",
        "dontAsk",
        "--output-format",
        "text",
        "--append-system-prompt",
        system_prompt,
        prompt,
    ]
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(PROJECT_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        raise RuntimeError(f"{label} 超时（>{timeout_seconds}s）")

    stdout_text = stdout.decode("utf-8", errors="ignore").strip()
    stderr_text = stderr.decode("utf-8", errors="ignore").strip()
    if stderr_text:
        await on_event("task.output", {"stream": "stderr", "text": f"[{label}] {stderr_text}"})
    if process.returncode != 0:
        raise RuntimeError(f"{label} 执行失败，exit={process.returncode}")
    if stdout_text:
        await on_event("task.output", {"stream": "stdout", "text": f"[{label}] {stdout_text[:4000]}"})
    return stdout_text


def _candidate_publish_roots(persona: str, platform: str) -> list[Path]:
    return [settings.vault_path / "60_Published" / "social-media" / persona / platform]


def _latest_content_file(persona: str, platform: str, started_at: datetime) -> Path | None:
    candidates: list[Path] = []
    for root in _candidate_publish_roots(persona, platform):
        if root.exists():
            candidates.extend(root.glob("*/content.md"))
    if not candidates:
        return None
    candidates = [path for path in candidates if datetime.fromtimestamp(path.stat().st_mtime) >= started_at]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _extract_title(body: str) -> str | None:
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _parse_review_result(raw: str) -> dict[str, object]:
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = next((part for part in parts if "{" in part and "}" in part), text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("reviewer 未返回合法 JSON")
    return json.loads(text[start : end + 1])


def _writer_prompt(*, persona: str, platform: str, source: str, extra_instruction: str | None = None) -> str:
    persona_path, platform_path = _persona_paths(persona, platform)
    prompt = [
        f"persona_id: {persona}",
        f"platform: {platform}",
        "",
        "## 人设档案",
        _read_text(persona_path),
        "",
        "## 平台规则",
        _read_text(platform_path),
        "",
        "## 素材",
        source,
        "",
        "## 任务",
        "请严格按照人设和平台规则输出完整 Markdown 成稿。",
        "只输出成稿，不要解释。",
    ]
    if extra_instruction:
        prompt.extend(["", "## 修改要求", extra_instruction])
    return "\n".join(prompt)


def _review_prompt(*, persona: str, platform: str, draft: str) -> tuple[str, str]:
    persona_path, platform_path = _persona_paths(persona, platform)
    system_prompt = _read_text(SOCIAL_CLAUDE_ROOT / "agents" / "reviewer" / "reviewer.md")
    prompt = "\n".join(
        [
            f"persona_id: {persona}",
            f"platform: {platform}",
            "",
            "## 人设档案",
            _read_text(persona_path),
            "",
            "## 平台规则",
            _read_text(platform_path),
            "",
            "## 待审核稿件",
            draft,
            "",
            "请输出纯 JSON，不要代码块。格式必须为：",
            '{"total":数字,"pass":true/false,"scores":{"内容质量":数字,"人设一致性":数字,"平台适配":数字,"情感共鸣":数字,"传播潜力":数字},"feedback":"字符串或null","highlights":"字符串"}',
            "总分 10 分，>=7 为通过。",
        ]
    )
    return system_prompt, prompt


async def run_content_task(
    *,
    content_id: str,
    persona: str,
    platform: str,
    input_text: str | None,
    input_path: str | None,
    on_event,
) -> dict[str, object]:
    source = input_text or ""
    if input_path:
        source_path = settings.vault_path / input_path
        if not source_path.exists():
            raise FileNotFoundError(f"素材文件不存在: {source_path}")
        source = str(source_path)
    if not source.strip():
        raise ValueError("素材为空，无法发起写作")
    await on_event("task.progress", {"message": "调用真实 /content-creation workflow"})
    started_at = datetime.now()
    slash_command = f"/content-creation {source} --account {persona} --platform {platform}"
    debug_dir = settings.vault_path / "50_Resources" / "web-ui-debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_file = debug_dir / f"content_creation_{content_id}.log"
    command = ["claude", "-p", "--debug-file", str(debug_file), slash_command]
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(SOCIAL_MEDIA_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=600)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        raise RuntimeError("真实 content-creation workflow 超时（>600s）")
    raw = stdout.decode("utf-8", errors="ignore").strip()
    stderr_text = stderr.decode("utf-8", errors="ignore").strip()
    if stderr_text:
        await on_event("task.output", {"stream": "stderr", "text": f"[content-creation] {stderr_text}"})
    if process.returncode != 0:
        debug_tail = ""
        if debug_file.exists():
            debug_tail = debug_file.read_text(encoding="utf-8", errors="ignore")[-4000:]
        raise RuntimeError(
            f"真实 content-creation workflow 失败，exit={process.returncode}"
            + (f"\nDEBUG:\n{debug_tail}" if debug_tail else "")
        )
    if raw:
        await on_event("task.output", {"stream": "stdout", "text": f"[content-creation] {raw[:4000]}"})
    latest_file = _latest_content_file(persona, platform, started_at)
    if not latest_file or not latest_file.exists():
        raise RuntimeError("workflow 已执行，但未找到新生成的 content.md")
    body = latest_file.read_text(encoding="utf-8")
    title = _extract_title(body) or latest_file.parent.name.split("_", 1)[-1]
    return {
        "title": title,
        "body": body,
        "output_file": str(latest_file),
        "review_score": None,
        "raw": raw,
    }


async def run_content_task_local(
    *,
    persona: str,
    platform: str,
    input_text: str | None,
    input_path: str | None,
    instruction: str | None,
    on_event,
) -> dict[str, object]:
    source = input_text or ""
    source_label = input_path
    if input_path:
        path_value = Path(input_path)
        source_path = path_value if path_value.is_absolute() else settings.vault_path / path_value
        if not source_path.exists():
            raise FileNotFoundError(f"素材文件不存在: {source_path}")
        source = source_path.read_text(encoding="utf-8")
        source_label = str(source_path)
    if not source.strip():
        raise ValueError("素材为空，无法发起写作")

    extra_instruction = instruction or (
        "请把这份素材扩写或改写成一篇完整成稿。"
        "严格遵守当前人设和平台规则。"
        "只输出最终 Markdown 成稿，不要解释。"
    )
    writer_system = _read_text(SOCIAL_CLAUDE_ROOT / "agents" / "writer" / "writer.md")
    await on_event("task.progress", {"message": "调用本地 writer 路径生成内容"})
    body = await _run_claude(
        prompt=_writer_prompt(
            persona=persona,
            platform=platform,
            source=source,
            extra_instruction=extra_instruction,
        ),
        system_prompt=writer_system,
        timeout_seconds=240,
        on_event=on_event,
        label="writer-local-draft",
    )
    title = _extract_title(body) or "未命名"
    return {
        "title": title,
        "body": body,
        "output_file": None,
        "review_score": None,
        "raw": None,
        "source_label": source_label,
    }


async def run_revision_task(*, persona: str, platform: str, instruction: str, current_content: str, on_event) -> str:
    writer_system = _read_text(SOCIAL_CLAUDE_ROOT / "agents" / "writer" / "writer.md")
    await on_event("task.progress", {"message": "调用 writer 执行修改"})
    revised = await _run_claude(
        prompt=_writer_prompt(
            persona=persona,
            platform=platform,
            source=current_content,
            extra_instruction=instruction,
        ),
        system_prompt=writer_system,
        timeout_seconds=180,
        on_event=on_event,
        label="writer-revise",
    )
    if not revised.strip():
        raise RuntimeError("修改结果为空")
    return revised


async def run_selection_recommendation(*, goal: str, candidates: list[dict[str, object]], on_event) -> dict[str, object]:
    await on_event("task.progress", {"message": "调用 Claude 生成选稿建议"})
    prompt = "\n".join(
        [
            "你是选稿编辑，请根据发布目标推荐内容。",
            "",
            "## 发布目标",
            goal,
            "",
            "## 候选内容",
            json.dumps(candidates, ensure_ascii=False, indent=2),
            "",
            "请输出纯 JSON，格式为：",
            '{"recommendations":[{"content_id":"...","title":"...","reason":"..."}],"schedule":"可为空字符串"}',
        ]
    )
    raw = await _run_claude(
        prompt=prompt,
        system_prompt="你是严格的选稿编辑，只输出 JSON。",
        timeout_seconds=120,
        on_event=on_event,
        label="selection",
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"选稿结果不是合法 JSON: {exc}") from exc
