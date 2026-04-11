from fastapi import APIRouter, HTTPException
from models import CreateArticleRequest, ReviseContentRequest, CollectIdeasRequest, ExpandIdeaRequest, TaskStatus
from services.db_service import get_idea, get_content
from services.agent_runner import start_create, start_revise, start_collect, start_expand, get_all_tasks, get_task, has_running_task, retry_task

router = APIRouter()


@router.post("/tasks/create", status_code=202)
async def create_article(req: CreateArticleRequest):
    idea = get_idea(req.idea_id)
    if not idea:
        raise HTTPException(404, "idea not found")
    if idea["status"] != "pending":
        raise HTTPException(400, "idea status is '{}', expected 'pending'".format(idea["status"]))

    if has_running_task():
        raise HTTPException(409, "max concurrent tasks reached (3), please wait")

    try:
        task_id = await start_create(req.idea_id, req.platform, req.persona_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {"task_id": task_id}


@router.post("/tasks/revise", status_code=202)
async def revise_content(req: ReviseContentRequest):
    content = get_content(req.content_id)
    if not content:
        raise HTTPException(404, "content not found")
    if content["status"] not in ("final", "revising"):
        raise HTTPException(400, "content status is '{}', cannot revise".format(content["status"]))

    if has_running_task():
        raise HTTPException(409, "max concurrent tasks reached (3), please wait")

    try:
        task_id = await start_revise(req.content_id, req.feedback)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {"task_id": task_id}


@router.post("/tasks/expand", status_code=202)
async def expand_idea(req: ExpandIdeaRequest):
    idea = get_idea(req.idea_id)
    if not idea:
        raise HTTPException(404, "idea not found")
    if not req.instruction.strip():
        raise HTTPException(400, "instruction is required")
    if has_running_task():
        raise HTTPException(409, "max concurrent tasks reached (3), please wait")

    task_id = await start_expand(req.idea_id, req.instruction.strip())
    return {"task_id": task_id}


@router.post("/tasks/collect", status_code=202)
async def collect_ideas(req: CollectIdeasRequest):
    if not req.source.strip():
        raise HTTPException(400, "source is required")

    if has_running_task():
        raise HTTPException(409, "max concurrent tasks reached (3), please wait")

    task_id = await start_collect(req.source.strip())
    return {"task_id": task_id}


@router.get("/tasks", response_model=list)
def list_tasks():
    return get_all_tasks()


@router.get("/tasks/{task_id}")
def get_task_status(task_id: str):
    t = get_task(task_id)
    if not t:
        raise HTTPException(404, "task not found")
    return t


@router.post("/tasks/{task_id}/retry", status_code=202)
async def retry_task_endpoint(task_id: str):
    if has_running_task():
        raise HTTPException(409, "max concurrent tasks reached (3), please wait")
    try:
        new_task_id = await retry_task(task_id)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"task_id": new_task_id}
