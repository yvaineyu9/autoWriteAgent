from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import agent_wrapper, storage
from .models import (
    DraftRequest,
    InspirationCreate,
    InspirationUpdate,
    PublicationMarkPublished,
    PublicationMetricCreate,
    ReviseRequest,
    SelectionConfirmRequest,
    SelectionRequest,
    TaskEnvelope,
)
from .task_registry import registry


@asynccontextmanager
async def lifespan(_: FastAPI):
    storage.migrate()
    yield


app = FastAPI(title="Claude Workflows Web UI", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/inspirations")
def get_inspirations():
    return storage.list_inspirations()


@app.post("/api/inspirations")
def post_inspiration(payload: InspirationCreate):
    return storage.create_inspiration(payload.model_dump())


@app.put("/api/inspirations/{path:path}")
def put_inspiration(path: str, payload: InspirationUpdate):
    return storage.update_inspiration(path, payload.model_dump(exclude_unset=True))


@app.delete("/api/inspirations/{path:path}")
def remove_inspiration(path: str):
    storage.delete_inspiration(path)
    return {"ok": True}


@app.post("/api/contents/{content_id}/draft")
async def draft_content(content_id: str, payload: DraftRequest):
    task = registry.create("draft", content_id)
    task.status = "running"
    task.started_at = task.started_at or datetime.utcnow()

    async def runner():
        await registry.emit(task, "task.started", {"task_type": "draft"})
        previous = storage.read_content(content_id)
        previous_status = previous["status"] if previous else "idea"
        try:
            storage.transition_content_status(content_id=content_id, to_status="drafting", operator="agent:content-creation", note="发起写作")
            result = await agent_wrapper.run_content_task(
                content_id=content_id,
                persona=payload.persona,
                platform=payload.platform,
                input_text=payload.input_text,
                input_path=payload.input_path,
                on_event=lambda event, event_payload: registry.emit(task, event, event_payload),
            )
            output_path = storage.write_output_markdown(
                content_id=content_id,
                title=str(result["title"]),
                persona=payload.persona,
                platform=payload.platform,
                body=str(result["body"]),
                review_score=result.get("review_score"),
            )
            storage.transition_content_status(content_id=content_id, to_status="draft", operator="agent:content-creation", note=f"草稿已输出到 {output_path}")
            await registry.finish(task, "succeeded")
        except Exception as exc:
            await registry.emit(task, "task.failed", {"error": str(exc)})
            storage.transition_content_status(
                content_id=content_id,
                to_status=previous_status,
                operator="agent:content-creation",
                note=f"写作失败: {exc}",
            )
            await registry.finish(task, "failed")

    asyncio.create_task(runner())
    return TaskEnvelope(task_id=task.task_id, content_id=content_id, task_type=task.task_type, status=task.status, started_at=task.started_at)


@app.post("/api/contents/{content_id}/revise")
async def revise_content(content_id: str, payload: ReviseRequest):
    task = registry.create("revise", content_id)
    task.status = "running"
    task.started_at = task.started_at or datetime.utcnow()
    content = storage.read_content(content_id)
    if not content or not content.get("output_path"):
        raise HTTPException(status_code=404, detail="content output not found")
    output_file = storage.settings.vault_path / str(content["output_path"])
    current_body = output_file.read_text(encoding="utf-8")

    async def runner():
        await registry.emit(task, "task.started", {"task_type": "revise"})
        try:
            storage.transition_content_status(content_id=content_id, to_status="revising", operator="agent:revision", note="发起修改")
            revised = await agent_wrapper.run_revision_task(
                instruction=payload.instruction,
                current_content=current_body,
                on_event=lambda event, event_payload: registry.emit(task, event, event_payload),
            )
            output_file.write_text(revised.strip() + "\n", encoding="utf-8")
            storage.transition_content_status(content_id=content_id, to_status="final", operator="agent:revision", note="修改完成")
            await registry.finish(task, "succeeded")
        except Exception as exc:
            await registry.emit(task, "task.failed", {"error": str(exc)})
            await registry.finish(task, "failed")

    asyncio.create_task(runner())
    return TaskEnvelope(task_id=task.task_id, content_id=content_id, task_type=task.task_type, status=task.status, started_at=task.started_at)


@app.post("/api/contents/{content_id}/finalize")
def finalize_content(content_id: str):
    storage.finalize_content(content_id)
    return {"ok": True}


@app.post("/api/selection/recommend")
async def selection_recommend(payload: SelectionRequest):
    task = registry.create("selection", None)
    task.status = "running"
    task.started_at = task.started_at or datetime.utcnow()
    candidates = storage.list_final_contents(persona=payload.persona, platform=payload.platform, limit=payload.limit)
    if not candidates:
        return {"recommendations": []}

    async def runner():
        await registry.emit(task, "task.started", {"task_type": "selection"})
        try:
            result = await agent_wrapper.run_selection_recommendation(
                goal=payload.goal,
                candidates=candidates,
                on_event=lambda event, event_payload: registry.emit(task, event, event_payload),
            )
            await registry.emit(task, "task.completed", result)
            await registry.finish(task, "succeeded")
        except Exception as exc:
            await registry.emit(task, "task.failed", {"error": str(exc)})
            await registry.finish(task, "failed")

    asyncio.create_task(runner())
    return TaskEnvelope(task_id=task.task_id, content_id=None, task_type=task.task_type, status=task.status, started_at=task.started_at)


@app.post("/api/selection/confirm")
def selection_confirm(payload: SelectionConfirmRequest):
    publication_ids = storage.create_publications_for_contents(payload.content_ids)
    return {"publication_ids": publication_ids}


@app.get("/api/publications")
def get_publications():
    return storage.list_publications()


@app.post("/api/publications/{publication_id}/publish")
def publish_publication(publication_id: int, payload: PublicationMarkPublished):
    storage.mark_publication_published(publication_id, payload.post_url, payload.published_at)
    return {"ok": True}


@app.post("/api/publications/{publication_id}/metrics")
def create_publication_metric(publication_id: int, payload: PublicationMetricCreate):
    storage.create_metric(publication_id, payload.model_dump())
    return {"ok": True}


@app.get("/api/tasks/{task_id}/events")
async def stream_task_events(task_id: str):
    task = registry.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")

    async def event_source():
        for item in task.events:
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        while not task.queue.empty():
            try:
                task.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        while True:
            item = await task.queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
