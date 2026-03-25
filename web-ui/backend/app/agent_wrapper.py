from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import subprocess
from datetime import datetime
from pathlib import Path

from .config import get_settings


settings = get_settings()
PROJECT_ROOT = settings.project_root
SOCIAL_MEDIA_ROOT = PROJECT_ROOT / "social-media"
SOCIAL_CLAUDE_ROOT = SOCIAL_MEDIA_ROOT / ".claude"
CLAUDE_FALLBACK_CWD = Path.home()
LOCAL_PERSONA_BRIEFS: dict[tuple[str, str], str] = {
    (
        "yuejian",
        "xiaohongshu",
    ): """
月见是写关系心理学与文艺情感内容的小红书作者，面向在关系里迷茫但想清醒的年轻女性。语气温柔克制、有画面感、共情但不说教；先讲清关系心理，再把星宿关系、星座、合⭐️盘当辅助翻译，不写成玄学号。禁止鸡汤、PUA、互联网黑话、恐吓和过度网络梗；结尾自然留白，签名用“我是月见，…… 🌙”。
""".strip()
}
LOCAL_PLATFORM_BRIEFS: dict[tuple[str, str], str] = {
    (
        "yuejian",
        "xiaohongshu",
    ): """
小红书成稿用 Markdown 输出。标题要有信息承诺；正文通常用 2-4 个 `##` 分段，开头 3-5 行内切进痛点，至少带 1 个可收藏框架段和 1 个自然互动钩子；短句分行，结尾干脆。需要写简介时再加 `---简介---` 和 3-6 个标签。审核敏感词必须打断成占⭐️、星⭐️盘、合⭐️盘、能⭐️量、运⭐️等；不要出现“说白了就是”“你需要明白的是”这类重 AI 味表达。
""".strip()
}
LOCAL_WRITER_SYSTEM_PROMPT = ""
LOCAL_REVIEWER_SYSTEM_PROMPT = ""


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


def _compact_markdown(text: str, *, skip_heading_keywords: tuple[str, ...] = ()) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    in_code_block = False
    skip_section = False
    heading_pattern = re.compile(r"^#{1,6}\s+")

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if stripped.startswith(">"):
            continue
        if stripped.startswith("|") or stripped.startswith("![]("):
            continue

        if heading_pattern.match(stripped):
            skip_section = any(keyword in stripped for keyword in skip_heading_keywords)
            if skip_section:
                continue
            kept.append(stripped)
            continue

        if skip_section:
            continue
        if not stripped:
            if kept and kept[-1] != "":
                kept.append("")
            continue
        kept.append(stripped)

    compacted = "\n".join(kept)
    compacted = re.sub(r"\n{3,}", "\n\n", compacted)
    return compacted.strip()


def _persona_brief(persona: str, platform: str, persona_path: Path) -> str:
    brief = LOCAL_PERSONA_BRIEFS.get((persona, platform))
    if brief:
        return brief
    return _compact_markdown(_read_text(persona_path))


def _platform_brief(persona: str, platform: str, platform_path: Path) -> str:
    brief = LOCAL_PLATFORM_BRIEFS.get((persona, platform))
    if brief:
        return brief
    return _compact_markdown(
        _read_text(platform_path),
        skip_heading_keywords=("帖子文件结构", "排版工具适配规范", "示例对比"),
    )


async def _run_claude(
    *,
    prompt: str,
    system_prompt: str,
    timeout_seconds: int,
    on_event,
    label: str,
) -> str:
    prompt = prompt.strip()
    if not prompt:
        raise RuntimeError(f"{label} prompt 为空")
    full_prompt = f"{system_prompt.strip()}\n\n{prompt}" if system_prompt.strip() else prompt
    quoted_prompt = shlex.quote(full_prompt)
    command = f"printf %s {quoted_prompt} | claude -p --permission-mode dontAsk --output-format text"
    result_task = asyncio.create_task(
        asyncio.to_thread(
            subprocess.run,
            command,
            cwd=str(CLAUDE_FALLBACK_CWD),
            env=os.environ.copy(),
            shell=True,
            executable="/bin/zsh",
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    )
    elapsed_seconds = 0
    try:
        while True:
            try:
                completed = await asyncio.wait_for(asyncio.shield(result_task), timeout=15)
                break
            except asyncio.TimeoutError:
                elapsed_seconds += 15
                if elapsed_seconds >= timeout_seconds:
                    raise RuntimeError(f"{label} 超时（>{timeout_seconds}s）")
                await on_event("task.progress", {"message": f"{label} 仍在运行（{elapsed_seconds}s）"})
    except RuntimeError:
        if not result_task.done():
            result_task.cancel()
        raise
    except subprocess.TimeoutExpired:
        if not result_task.done():
            result_task.cancel()
        raise RuntimeError(f"{label} 超时（>{timeout_seconds}s）")
    except Exception:
        if not result_task.done():
            result_task.cancel()
        raise

    stdout_text = completed.stdout.strip()
    stderr_text = completed.stderr.strip()
    if stderr_text:
        await on_event("task.output", {"stream": "stderr", "text": f"[{label}] {stderr_text}"})
    if completed.returncode != 0:
        detail = f"\nSTDERR:\n{stderr_text[-2000:]}" if stderr_text else ""
        raise RuntimeError(f"{label} 执行失败，exit={completed.returncode}{detail}")
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
    source_text = source.strip()
    instruction_text = extra_instruction.strip() if extra_instruction else "按以上要求输出最终成稿。"
    if (persona, platform) == ("yuejian", "xiaohongshu"):
        return (
            "你是月见，一个写关系心理学与文艺情感内容的小红书作者，"
            "语气温柔克制，有画面感，共情但不说教，不用鸡汤、PUA话术、互联网黑话和恐吓表达。"
            "你会先讲清关系心理，再自然结合星宿关系、星座、合⭐️盘做辅助翻译，但不要写成玄学号。"
            "标题要有信息承诺，正文适合小红书卡片阅读，短句分行；需要时带 2-4 个 `##` 分段、可收藏框架段、自然互动钩子，结尾用“我是月见，…… 🌙”收束。"
            "审核敏感词必须打断成占⭐️、星⭐️盘、合⭐️盘、能⭐️量、运⭐️等。"
            f"请根据这条素材完成任务：{source_text}。"
            f"具体要求：{instruction_text}"
            "只输出最终结果，不要解释。"
        )
    persona_path, platform_path = _persona_paths(persona, platform)
    persona_text = _persona_brief(persona, platform, persona_path)
    platform_text = _platform_brief(persona, platform, platform_path)
    return (
        f"你现在为 persona `{persona}` 在平台 `{platform}` 写稿。"
        "只根据当前消息完成任务，不要读取文件、不要调用工具、不要引用外部上下文。"
        f"人设要求：{persona_text}。"
        f"平台要求：{platform_text}。"
        f"素材：{source_text}。"
        f"任务：{instruction_text}"
        "优先执行任务要求；如果它只要求短文、标题、简介或局部改写，不必强行输出完整长文结构。"
        "只输出最终结果，不要解释。"
    )


def _review_prompt(*, persona: str, platform: str, draft: str) -> tuple[str, str]:
    draft_text = draft.strip()
    if (persona, platform) == ("yuejian", "xiaohongshu"):
        prompt = (
            "你是内容审核官，请审核这篇月见风格的小红书稿件。"
            "评分只根据当前消息，不要读取文件、不要调用工具、不要引用外部上下文。"
            "重点看 5 个维度：内容质量、人设一致性、平台适配、情感共鸣、传播潜力。"
            "月见风格要温柔克制、有画面感、共情但不说教；小红书稿要有信息承诺、适合卡片排版，并避开重 AI 味和违规词。"
            f"待审核稿件：{draft_text}。"
            "请输出纯 JSON，不要代码块。格式必须为："
            '{"total":数字,"pass":true/false,"scores":{"内容质量":数字,"人设一致性":数字,"平台适配":数字,"情感共鸣":数字,"传播潜力":数字},"feedback":"字符串或null","highlights":"字符串"}'
            "总分 10 分，>=7 为通过。"
        )
        return LOCAL_REVIEWER_SYSTEM_PROMPT, prompt
    persona_path, platform_path = _persona_paths(persona, platform)
    persona_text = _persona_brief(persona, platform, persona_path)
    platform_text = _platform_brief(persona, platform, platform_path)
    prompt = (
        f"请审核 persona `{persona}` 在平台 `{platform}` 的稿件。"
        "只根据当前消息评分，不要读取文件、不要调用工具、不要引用外部上下文。"
        f"人设要求：{persona_text}。"
        f"平台要求：{platform_text}。"
        f"待审核稿件：{draft_text}。"
        "请输出纯 JSON，不要代码块。格式必须为："
        '{"total":数字,"pass":true/false,"scores":{"内容质量":数字,"人设一致性":数字,"平台适配":数字,"情感共鸣":数字,"传播潜力":数字},"feedback":"字符串或null","highlights":"字符串"}'
        "总分 10 分，>=7 为通过。"
    )
    return LOCAL_REVIEWER_SYSTEM_PROMPT, prompt


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
    await on_event("task.progress", {"message": "调用本地 writer 路径生成内容"})
    body = await _run_claude(
        prompt=_writer_prompt(
            persona=persona,
            platform=platform,
            source=source,
            extra_instruction=extra_instruction,
        ),
        system_prompt=LOCAL_WRITER_SYSTEM_PROMPT,
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
    await on_event("task.progress", {"message": "调用 writer 执行修改"})
    revised = await _run_claude(
        prompt=_writer_prompt(
            persona=persona,
            platform=platform,
            source=current_content,
            extra_instruction=instruction,
        ),
        system_prompt=LOCAL_WRITER_SYSTEM_PROMPT,
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
