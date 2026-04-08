from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from models import IdeaOut, CreateIdeaRequest, UpdateIdeaRequest
from services.db_service import list_ideas, get_idea, read_idea_body, delete_idea, create_idea, update_idea

router = APIRouter()


@router.get("/ideas", response_model=list)
def get_ideas(status: Optional[str] = Query(None)):
    return list_ideas(status)


@router.get("/ideas/{idea_id}/body")
def get_idea_body(idea_id: str):
    idea = get_idea(idea_id)
    if not idea:
        raise HTTPException(404, "idea not found")
    body = read_idea_body(idea["file_path"])
    if body is None:
        raise HTTPException(404, "idea file not found on disk")
    return {"id": idea["id"], "title": idea["title"], "body": body}


@router.post("/ideas")
def add_idea(req: CreateIdeaRequest):
    if not req.title.strip():
        raise HTTPException(400, "title is required")
    return create_idea(req.title.strip(), req.content, req.tags)


@router.put("/ideas/{idea_id}")
def edit_idea(idea_id: str, req: UpdateIdeaRequest):
    if not req.title.strip():
        raise HTTPException(400, "title is required")
    result = update_idea(idea_id, req.title.strip(), req.content, req.tags)
    if not result:
        raise HTTPException(404, "idea not found")
    return result


@router.delete("/ideas/{idea_id}")
def remove_idea(idea_id: str):
    if not delete_idea(idea_id):
        raise HTTPException(404, "idea not found")
    return {"deleted": True}
