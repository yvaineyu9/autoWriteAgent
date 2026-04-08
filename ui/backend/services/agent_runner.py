"""
Async agent runner: manages long-running claude CLI calls for create/revise.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TOOLS_DIR = os.path.join(PROJECT_ROOT, "tools")
sys.path.insert(0, TOOLS_DIR)

# Import validate_review with future annotations to handle str | None on Python 3.9
import importlib
import types
_vr_spec = importlib.util.spec_from_file_location(
    "validate_review",
    os.path.join(TOOLS_DIR, "validate_review.py"),
)
_vr_mod = importlib.util.module_from_spec(_vr_spec)
# Inject future annotations to handle str | None syntax
_vr_mod.__annotations__ = {}
try:
    _vr_spec.loader.exec_module(_vr_mod)
    validate_review = _vr_mod.validate
except TypeError:
    # Python 3.9 can't parse str | None - inline a simple validator
    def validate_review(data):
        required = ["total", "pass", "scores", "feedback", "highlights"]
        for field in required:
            if field not in data:
                return "missing field: {}".format(field)
        scores = data.get("scores", {})
        if not isinstance(scores, dict) or len(scores) != 5:
            return "scores must have exactly 5 dimensions"
        for k, v in scores.items():
            if not isinstance(v, (int, float)) or v < 0 or v > 2:
                return "scores[{}] out of range 0-2".format(k)
        if data["total"] != sum(scores.values()):
            return "total != sum(scores)"
        if data["pass"] != (data["total"] >= 7):
            return "pass value mismatch"
        if not data["pass"] and data["feedback"] is None:
            return "feedback required when pass=false"
        return None

PERSONAS_DIR = os.path.join(PROJECT_ROOT, "personas")
AGENTS_DIR = os.path.join(PROJECT_ROOT, "agents")
DATA_CONTENT_DIR = os.path.join(PROJECT_ROOT, "data", "content")
TMP_DIR = "/tmp/autowrite"

VALID_PLATFORMS = ("xiaohongshu", "wechat")
MAX_ROUNDS = 3


@dataclass
class TaskState:
    task_id: str
    task_type: str  # "create" or "revise"
    status: str = "running"  # running / completed / failed
    current_step: str = ""
    result: Optional[dict] = None
    error: Optional[str] = None
    started_at: str = ""
    updated_at: str = ""


# In-memory task registry
_tasks: dict[str, TaskState] = {}
_running_lock = asyncio.Lock()
_has_running_task = False


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_all_tasks() -> list[dict]:
    return [
        {
            "task_id": t.task_id,
            "task_type": t.task_type,
            "status": t.status,
            "current_step": t.current_step,
            "result": t.result,
            "error": t.error,
            "started_at": t.started_at,
            "updated_at": t.updated_at,
        }
        for t in _tasks.values()
    ]


def get_task(task_id: str):
    t = _tasks.get(task_id)
    if not t:
        return None
    return {
        "task_id": t.task_id,
        "task_type": t.task_type,
        "status": t.status,
        "current_step": t.current_step,
        "result": t.result,
        "error": t.error,
        "started_at": t.started_at,
        "updated_at": t.updated_at,
    }


def has_running_task() -> bool:
    return _has_running_task


def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _get_env():
    """Get environment with expanded PATH and proxy for claude."""
    env = os.environ.copy()
    extra = "/opt/homebrew/bin:/usr/local/bin"
    env["PATH"] = extra + ":" + env.get("PATH", "/usr/bin:/bin")
    # Proxy required on Mac Mini for claude to reach Anthropic API
    proxy = "http://127.0.0.1:10808"
    env["CLAUDE_PROXY_URL"] = proxy
    env["http_proxy"] = proxy
    env["https_proxy"] = proxy
    env["HTTP_PROXY"] = proxy
    env["HTTPS_PROXY"] = proxy
    env["ALL_PROXY"] = proxy
    return env


async def _run_claude(input_text, allowed_tools=None):
    """Run claude -p with input text, return stdout."""
    cmd = "claude -p"
    if allowed_tools is not None:
        cmd += ' --allowedTools "{}"'.format(allowed_tools)

    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=PROJECT_ROOT,
        env=_get_env(),
    )
    stdout, stderr = await proc.communicate(input=input_text.encode("utf-8"))
    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"claude exited with code {proc.returncode}: {err_msg}")
    return stdout.decode("utf-8", errors="replace")


def _assemble_writer_input(
    writer_md: str,
    platform_ctx: str,
    materials: str,
    feedback: str | None = None,
) -> str:
    parts = [writer_md, "\n---\n", platform_ctx, "\n---\n", "## materials\n\n", materials]
    if feedback:
        parts.append(f"\n---\n## previous review feedback (revision mode)\n\n{feedback}")
    return "".join(parts)


def _assemble_reviewer_input(reviewer_md: str, platform_ctx: str, draft: str) -> str:
    return f"{reviewer_md}\n---\n{platform_ctx}\n---\n## content to review\n\n{draft}"


async def run_create_pipeline(task_id: str, idea_id: str, platform: str, persona_id: str = "yuejian"):
    """Full create pipeline: writer -> reviewer -> iterate -> archive."""
    global _has_running_task
    t = _tasks[task_id]

    try:
        # Load files
        t.current_step = "Loading context..."
        t.updated_at = _now()

        platform_ctx = _read_file(os.path.join(PERSONAS_DIR, persona_id, "platforms", f"{platform}.md"))
        writer_md = _read_file(os.path.join(AGENTS_DIR, "writer.md"))
        reviewer_md = _read_file(os.path.join(AGENTS_DIR, "reviewer.md"))

        # Read idea content
        from db import get_connection

        conn = get_connection()
        idea_row = conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        conn.close()
        if not idea_row:
            raise RuntimeError(f"Idea not found: {idea_id}")

        idea_body = _read_file(os.path.join(DATA_CONTENT_DIR, idea_row["file_path"]))
        materials = f"### Idea: {idea_row['title']}\n\n{idea_body}"

        # Working dir
        work_dir = os.path.join(TMP_DIR, task_id)
        os.makedirs(work_dir, exist_ok=True)

        draft = ""
        review_data = None
        feedback = None

        for round_num in range(1, MAX_ROUNDS + 1):
            # Writer
            t.current_step = f"Writing draft (round {round_num}/{MAX_ROUNDS})..."
            t.updated_at = _now()

            writer_input = _assemble_writer_input(writer_md, platform_ctx, materials, feedback)
            draft = await _run_claude(writer_input, allowed_tools="Read,WebFetch")

            # Save draft
            with open(os.path.join(work_dir, f"draft_r{round_num}.md"), "w", encoding="utf-8") as f:
                f.write(draft)

            # Reviewer
            t.current_step = f"Reviewing draft (round {round_num}/{MAX_ROUNDS})..."
            t.updated_at = _now()

            reviewer_input = _assemble_reviewer_input(reviewer_md, platform_ctx, draft)
            review_raw = await _run_claude(reviewer_input, allowed_tools="")

            # Parse and validate review
            try:
                # Strip possible markdown code block
                raw = review_raw.strip()
                if raw.startswith("```"):
                    lines = raw.split("\n")
                    lines = lines[1:]  # remove first ```json
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    raw = "\n".join(lines)
                review_data = json.loads(raw)
                err = validate_review(review_data)
                if err:
                    raise ValueError(err)
            except (json.JSONDecodeError, ValueError) as e:
                # Review parse failed, use draft as-is
                review_data = None
                break

            with open(os.path.join(work_dir, f"review_r{round_num}.json"), "w", encoding="utf-8") as f:
                json.dump(review_data, f, ensure_ascii=False, indent=2)

            if review_data.get("pass"):
                break

            feedback = review_data.get("feedback", "")

        # Archive
        t.current_step = "Archiving..."
        t.updated_at = _now()

        # Save final draft to temp file for archive.py
        final_draft_path = os.path.join(work_dir, "final.md")
        with open(final_draft_path, "w", encoding="utf-8") as f:
            f.write(draft)

        # Extract title from draft (first # heading or first line)
        title = idea_row["title"]
        for line in draft.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                title = line[2:].strip()
                break

        # Save review json if exists
        review_json_path = None
        if review_data:
            review_json_path = os.path.join(work_dir, "review.json")
            with open(review_json_path, "w", encoding="utf-8") as f:
                json.dump(review_data, f, ensure_ascii=False, indent=2)

        # Call archive.py
        archive_cmd = [
            sys.executable, os.path.join(TOOLS_DIR, "archive.py"),
            "--persona", persona_id,
            "--platform", platform,
            "--title", title,
            "--file", final_draft_path,
        ]
        if review_json_path:
            archive_cmd += ["--review-json", review_json_path]
        archive_cmd += ["--source-idea", idea_id]

        proc = await asyncio.create_subprocess_exec(
            *archive_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=PROJECT_ROOT,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode not in (0, 2):
            raise RuntimeError(f"archive.py failed: {stderr.decode()}")

        archive_result = json.loads(stdout.decode())

        # Update idea status to used
        from services.db_service import update_idea_status
        update_idea_status(idea_id, "used")

        t.status = "completed"
        t.current_step = "Done"
        t.result = archive_result
        t.updated_at = _now()

    except Exception as e:
        t.status = "failed"
        t.error = str(e)
        t.current_step = "Failed"
        t.updated_at = _now()
    finally:
        _has_running_task = False


async def run_revise_pipeline(task_id: str, content_id: str, feedback: str):
    """Revise existing content with user feedback."""
    global _has_running_task
    t = _tasks[task_id]

    try:
        t.current_step = "Loading content..."
        t.updated_at = _now()

        # Load existing content
        from services.db_service import get_content, read_content_body, update_content_after_revise

        content = get_content(content_id)
        if not content:
            raise RuntimeError(f"Content not found: {content_id}")

        platform = content["platform"]
        persona_id = content.get("persona_id", "yuejian")
        body = read_content_body(content["file_path"])
        if not body:
            raise RuntimeError(f"Content file not found: {content['file_path']}")

        platform_ctx = _read_file(os.path.join(PERSONAS_DIR, persona_id, "platforms", f"{platform}.md"))
        writer_md = _read_file(os.path.join(AGENTS_DIR, "writer.md"))
        reviewer_md = _read_file(os.path.join(AGENTS_DIR, "reviewer.md"))

        work_dir = os.path.join(TMP_DIR, task_id)
        os.makedirs(work_dir, exist_ok=True)

        materials = f"## existing content (to be revised)\n\n{body}"
        current_feedback = feedback
        draft = ""
        review_data = None

        for round_num in range(1, MAX_ROUNDS + 1):
            t.current_step = f"Revising (round {round_num}/{MAX_ROUNDS})..."
            t.updated_at = _now()

            writer_input = _assemble_writer_input(writer_md, platform_ctx, materials, current_feedback)
            draft = await _run_claude(writer_input, allowed_tools="Read,WebFetch")

            with open(os.path.join(work_dir, f"draft_r{round_num}.md"), "w", encoding="utf-8") as f:
                f.write(draft)

            t.current_step = f"Reviewing revision (round {round_num}/{MAX_ROUNDS})..."
            t.updated_at = _now()

            reviewer_input = _assemble_reviewer_input(reviewer_md, platform_ctx, draft)
            review_raw = await _run_claude(reviewer_input, allowed_tools="")

            try:
                raw = review_raw.strip()
                if raw.startswith("```"):
                    lines = raw.split("\n")
                    lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    raw = "\n".join(lines)
                review_data = json.loads(raw)
                err = validate_review(review_data)
                if err:
                    raise ValueError(err)
            except (json.JSONDecodeError, ValueError):
                review_data = None
                break

            if review_data.get("pass"):
                break

            current_feedback = review_data.get("feedback", "")

        # Overwrite content file
        t.current_step = "Saving revision..."
        t.updated_at = _now()

        abs_path = os.path.join(DATA_CONTENT_DIR, content["file_path"])
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(draft)

        # Update DB
        review_score = review_data.get("total") if review_data else None
        review_json_str = json.dumps(review_data, ensure_ascii=False) if review_data else None
        update_content_after_revise(content_id, review_score, review_json_str)

        t.status = "completed"
        t.current_step = "Done"
        t.result = {"content_id": content_id, "review_score": review_score}
        t.updated_at = _now()

    except Exception as e:
        t.status = "failed"
        t.error = str(e)
        t.current_step = "Failed"
        t.updated_at = _now()
    finally:
        _has_running_task = False


async def start_create(idea_id: str, platform: str, persona_id: str = "yuejian") -> str:
    """Start a create task. Returns task_id."""
    global _has_running_task

    if platform not in VALID_PLATFORMS:
        raise ValueError(f"Invalid platform: {platform}. Must be one of {VALID_PLATFORMS}")

    if _has_running_task:
        raise RuntimeError("A task is already running")

    task_id = str(uuid.uuid4())[:8]
    now = _now()
    _tasks[task_id] = TaskState(
        task_id=task_id,
        task_type="create",
        started_at=now,
        updated_at=now,
        current_step="Starting...",
    )
    _has_running_task = True
    asyncio.create_task(run_create_pipeline(task_id, idea_id, platform, persona_id))
    return task_id


async def run_collect_pipeline(task_id: str, source: str):
    """Collect ideas from a source using the collector agent."""
    global _has_running_task
    t = _tasks[task_id]

    try:
        t.current_step = "Loading collector agent..."
        t.updated_at = _now()

        collector_md = _read_file(os.path.join(AGENTS_DIR, "collector.md"))
        prompt = "{}\n---\n## source\n\n{}".format(collector_md, source)

        t.current_step = "AI collecting ideas..."
        t.updated_at = _now()

        result_raw = await _run_claude(prompt, allowed_tools="Read,WebFetch,WebSearch")

        # Parse JSON array from result
        raw = result_raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines)

        t.current_step = "Saving ideas..."
        t.updated_at = _now()

        ideas_list = json.loads(raw)
        if not isinstance(ideas_list, list):
            ideas_list = [ideas_list]

        # Save each idea via inbox.py
        saved = 0
        for idea in ideas_list:
            title = idea.get("title", "").strip()
            if not title:
                continue
            summary = idea.get("summary", "")
            angle = idea.get("angle", "")
            tags_list = idea.get("tags", [])
            tags_str = ",".join(tags_list) if isinstance(tags_list, list) else str(tags_list)
            body = "## {}\n\n{}\n\n### angle\n{}\n\n### source\n{}".format(
                title, summary, angle, idea.get("source", source)
            )

            inbox_cmd = [
                sys.executable, os.path.join(TOOLS_DIR, "inbox.py"),
                "--title", title,
                "--content", body,
                "--tags", tags_str,
            ]
            proc = await asyncio.create_subprocess_exec(
                *inbox_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=PROJECT_ROOT,
            )
            await proc.communicate()
            if proc.returncode == 0:
                saved += 1

        t.status = "completed"
        t.current_step = "Done"
        t.result = {"collected": len(ideas_list), "saved": saved}
        t.updated_at = _now()

    except Exception as e:
        t.status = "failed"
        t.error = str(e)
        t.current_step = "Failed"
        t.updated_at = _now()
    finally:
        _has_running_task = False


async def run_expand_pipeline(task_id: str, idea_id: str, instruction: str):
    """Expand/refine a single idea with AI based on user instruction."""
    global _has_running_task
    t = _tasks[task_id]

    try:
        t.current_step = "Loading idea..."
        t.updated_at = _now()

        from services.db_service import get_idea, read_idea_body, DATA_CONTENT_DIR as _DCD
        idea = get_idea(idea_id)
        if not idea:
            raise RuntimeError("Idea not found: {}".format(idea_id))
        body = read_idea_body(idea["file_path"]) or ""

        t.current_step = "AI expanding idea..."
        t.updated_at = _now()

        prompt = (
            "You are a research assistant. Below is an existing idea note and a user instruction.\n"
            "Based on the instruction, research, expand, and refine the idea.\n"
            "Output the COMPLETE updated idea note (not just the additions).\n"
            "Write in the same language as the original note.\n\n"
            "---\n## Existing idea\n\n{}\n\n"
            "---\n## User instruction\n\n{}"
        ).format(body, instruction)

        result = await _run_claude(prompt, allowed_tools="Read,WebFetch,WebSearch")

        t.current_step = "Saving..."
        t.updated_at = _now()

        # Overwrite idea file
        abs_path = os.path.join(_DCD, idea["file_path"])
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(result)

        t.status = "completed"
        t.current_step = "Done"
        t.result = {"idea_id": idea_id}
        t.updated_at = _now()

    except Exception as e:
        t.status = "failed"
        t.error = str(e)
        t.current_step = "Failed"
        t.updated_at = _now()
    finally:
        _has_running_task = False


async def start_expand(idea_id: str, instruction: str) -> str:
    """Start an expand task. Returns task_id."""
    global _has_running_task

    if _has_running_task:
        raise RuntimeError("A task is already running")

    task_id = str(uuid.uuid4())[:8]
    now = _now()
    _tasks[task_id] = TaskState(
        task_id=task_id,
        task_type="expand",
        started_at=now,
        updated_at=now,
        current_step="Starting...",
    )
    _has_running_task = True
    asyncio.create_task(run_expand_pipeline(task_id, idea_id, instruction))
    return task_id


async def start_collect(source: str) -> str:
    """Start a collect task. Returns task_id."""
    global _has_running_task

    if _has_running_task:
        raise RuntimeError("A task is already running")

    task_id = str(uuid.uuid4())[:8]
    now = _now()
    _tasks[task_id] = TaskState(
        task_id=task_id,
        task_type="collect",
        started_at=now,
        updated_at=now,
        current_step="Starting...",
    )
    _has_running_task = True
    asyncio.create_task(run_collect_pipeline(task_id, source))
    return task_id


async def run_recommend_pipeline(task_id: str, persona_id: str):
    """Use Selector Agent to recommend contents for publishing."""
    global _has_running_task
    t = _tasks[task_id]

    try:
        t.current_step = "Loading candidates..."
        t.updated_at = _now()

        from services.db_service import list_contents, get_content, read_content_body

        contents = list_contents(status="final", persona_id=persona_id)

        if not contents:
            t.status = "completed"
            t.result = {"recommendations": [], "notes": "No final contents available"}
            t.current_step = "Done"
            t.updated_at = _now()
            return

        # Build candidate list with summaries
        candidates = []
        for c in contents:
            entry = {
                "content_id": c["content_id"],
                "title": c["title"],
                "platform": c["platform"],
                "review_score": c.get("review_score"),
                "created_at": c["created_at"],
            }
            # Try to get first 200 chars as summary
            full = get_content(c["content_id"])
            if full and full.get("file_path"):
                body = read_content_body(full["file_path"])
                if body:
                    entry["summary"] = body[:200]
            candidates.append(entry)

        t.current_step = "AI recommending..."
        t.updated_at = _now()

        selector_md = _read_file(os.path.join(AGENTS_DIR, "selector.md"))
        candidates_json = json.dumps(candidates, ensure_ascii=False, indent=2)
        prompt = "{}\n---\n## 候选列表\n\n```json\n{}\n```\n\n## 发布目标\n\n从以上候选中推荐适合发布的内容，优先选择评分高、时效性好的文章。".format(
            selector_md, candidates_json
        )

        result_raw = await _run_claude(prompt, allowed_tools="")

        # Parse JSON
        raw = result_raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines)

        result = json.loads(raw)

        t.status = "completed"
        t.result = result
        t.current_step = "Done"
        t.updated_at = _now()

    except Exception as e:
        t.status = "failed"
        t.error = str(e)
        t.current_step = "Failed"
        t.updated_at = _now()
    finally:
        _has_running_task = False


async def start_recommend(persona_id: str) -> str:
    """Start a recommend task. Returns task_id."""
    global _has_running_task

    if _has_running_task:
        raise RuntimeError("A task is already running")

    task_id = str(uuid.uuid4())[:8]
    now = _now()
    _tasks[task_id] = TaskState(
        task_id=task_id,
        task_type="recommend",
        started_at=now,
        updated_at=now,
        current_step="Starting...",
    )
    _has_running_task = True
    asyncio.create_task(run_recommend_pipeline(task_id, persona_id))
    return task_id


async def start_revise(content_id: str, feedback: str) -> str:
    """Start a revise task. Returns task_id."""
    global _has_running_task

    if _has_running_task:
        raise RuntimeError("A task is already running")

    task_id = str(uuid.uuid4())[:8]
    now = _now()
    _tasks[task_id] = TaskState(
        task_id=task_id,
        task_type="revise",
        started_at=now,
        updated_at=now,
        current_step="Starting...",
    )
    _has_running_task = True
    asyncio.create_task(run_revise_pipeline(task_id, content_id, feedback))
    return task_id
