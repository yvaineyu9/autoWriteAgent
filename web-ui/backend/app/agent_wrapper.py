from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path

from .config import get_settings


settings = get_settings()
PROJECT_ROOT = settings.project_root
SOCIAL_MEDIA_ROOT = PROJECT_ROOT / "social-media"
SOCIAL_CLAUDE_ROOT = SOCIAL_MEDIA_ROOT / ".claude"
LOCAL_PERSONA_BRIEFS: dict[tuple[str, str], str] = {
    (
        "yuejian",
        "xiaohongshu",
    ): """
月见：关系心理学 × 文艺情感写作。
- 核心：先讲清关系心理，再用占⭐️/合⭐️盘/星宿关系做辅助翻译，不写成玄学号。
- 受众：18-26 岁、在关系里迷茫但想清醒的年轻女性。
- 语气：温柔、克制、画面感先行，共情但不沉溺，像深夜低声说话。
- 表达：用“你”直接带入；先给真实场景，再解释心理机制；短句有节奏，但不装腔。
- 禁止：说教、PUA 话术、互联网黑话、鸡汤、恐吓、过度网络梗、中英文混用。
- 结尾：留白式收束，不硬讲道理；签名用“我是月见，…… 🌙”且每篇不同。
- 软引导：可自然提到“如果你想更清楚看到自己的关系模式，我可以陪你一起看”；也可轻提除了星宿关系，还能结合星座、合⭐️盘一起看。
""".strip()
}
LOCAL_PLATFORM_BRIEFS: dict[tuple[str, str], str] = {
    (
        "yuejian",
        "xiaohongshu",
    ): """
小红书成稿规则：
- 输出完整 Markdown 成稿，不解释。
- 标题放最前，25 字内，要有信息承诺，不要纯情绪空话。
- 正文用 2-4 个 `##` 分段，每段一个清晰观点。
- 开头直接切痛点，3-5 行内进入正题，不要空洞铺陈。
- 必须至少有 1 个可收藏框架段：3个信号 / 自检清单 / 对比分类。
- 行文短句分行，每 2-4 行留一个空行，适合卡片排版。
- 中段或结尾前埋 1 个自然互动钩子。
- 结尾要干脆，不要祝福体、说教体、万能金句。
- 签名单独一行，以“我是月见，…… 🌙”收尾。
- 如需简介区，用 `---简介---` 后补一段口语化搜索描述和 3-6 个标签。
- 如果当前任务是短文、单段、标题或局部改写，不必强行套完整长文结构。
- 审核敏感词必须打断：占⭐️、星⭐️盘、合⭐️盘、能⭐️量、运⭐️等。
- 禁止高风险表达：让我们一起探索、首先其次最后、你需要明白的是、说白了就是、别骗自己了。
""".strip()
}
LOCAL_WRITER_SYSTEM_PROMPT = """
你是本项目的本地社媒写手 fallback。

执行边界：
- 只依据当前消息里提供的人设、平台规则、素材和修改要求工作。
- 不要尝试读取文件、搜索知识库、调用工具、引用外部上下文。
- 如果修改要求和默认平台长文规则冲突，优先服从修改要求。

输出要求：
- 只输出最终结果，不要解释、不要分析、不要加前后说明。
- 若要求输出 Markdown，就直接输出最终 Markdown。
""".strip()
LOCAL_REVIEWER_SYSTEM_PROMPT = """
你是本项目的本地审核 fallback。

执行边界：
- 只依据当前消息里提供的人设、平台规则和待审核稿件评分。
- 不要尝试读取文件、调用工具或引用外部上下文。

输出要求：
- 只输出合法 JSON，不要代码块，不要解释。
""".strip()


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
    command = [
        "claude",
        "-p",
        "--permission-mode",
        "dontAsk",
        "--output-format",
        "text",
    ]
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(PROJECT_ROOT),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
    )
    communicate_task = asyncio.create_task(process.communicate(full_prompt.encode("utf-8")))
    elapsed_seconds = 0
    try:
        while True:
            try:
                stdout, stderr = await asyncio.wait_for(asyncio.shield(communicate_task), timeout=15)
                break
            except asyncio.TimeoutError:
                elapsed_seconds += 15
                if elapsed_seconds >= timeout_seconds:
                    process.kill()
                    await process.communicate()
                    raise RuntimeError(f"{label} 超时（>{timeout_seconds}s）")
                await on_event("task.progress", {"message": f"{label} 仍在运行（{elapsed_seconds}s）"})
    except RuntimeError:
        if not communicate_task.done():
            communicate_task.cancel()
        raise
    except Exception:
        process.kill()
        await process.communicate()
        if not communicate_task.done():
            communicate_task.cancel()
        raise

    stdout_text = stdout.decode("utf-8", errors="ignore").strip()
    stderr_text = stderr.decode("utf-8", errors="ignore").strip()
    if stderr_text:
        await on_event("task.output", {"stream": "stderr", "text": f"[{label}] {stderr_text}"})
    if process.returncode != 0:
        detail = f"\nSTDERR:\n{stderr_text[-2000:]}" if stderr_text else ""
        raise RuntimeError(f"{label} 执行失败，exit={process.returncode}{detail}")
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
    persona_text = _persona_brief(persona, platform, persona_path)
    platform_text = _platform_brief(persona, platform, platform_path)
    task_line = "请严格按照人设和平台规则输出最终结果。"
    if extra_instruction:
        task_line = "优先执行修改要求；如果修改要求只要短文、标题、简介或局部改写，不必强行输出完整长文结构。"
    prompt = [
        f"persona_id: {persona}",
        f"platform: {platform}",
        "",
        "## 执行边界",
        "你现在已经拿到了写作所需的全部信息。",
        "不要再尝试读取文件、搜索知识库或参考其他帖子。",
        "只基于下面提供的人设、平台规则、素材和修改要求完成输出。",
        "",
        "## 人设档案",
        persona_text,
        "",
        "## 平台规则",
        platform_text,
        "",
        "## 素材",
        source,
        "",
        "## 任务",
        task_line,
        "只输出成稿，不要解释。",
    ]
    if extra_instruction:
        prompt.extend(["", "## 修改要求", extra_instruction])
    return "\n".join(prompt)


def _review_prompt(*, persona: str, platform: str, draft: str) -> tuple[str, str]:
    persona_path, platform_path = _persona_paths(persona, platform)
    persona_text = _persona_brief(persona, platform, persona_path)
    platform_text = _platform_brief(persona, platform, platform_path)
    prompt = "\n".join(
        [
            f"persona_id: {persona}",
            f"platform: {platform}",
            "",
            "## 执行边界",
            "你现在已经拿到了审核所需的全部信息。",
            "不要再尝试读取文件或调用工具。",
            "",
            "## 人设档案",
            persona_text,
            "",
            "## 平台规则",
            platform_text,
            "",
            "## 待审核稿件",
            draft,
            "",
            "请输出纯 JSON，不要代码块。格式必须为：",
            '{"total":数字,"pass":true/false,"scores":{"内容质量":数字,"人设一致性":数字,"平台适配":数字,"情感共鸣":数字,"传播潜力":数字},"feedback":"字符串或null","highlights":"字符串"}',
            "总分 10 分，>=7 为通过。",
        ]
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
