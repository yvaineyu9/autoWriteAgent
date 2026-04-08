from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from models import SelectPublishRequest
from services.db_service import list_contents, get_content

router = APIRouter()


@router.post("/select/recommend", status_code=202)
async def select_recommend(persona_id: str = Query("yuejian")):
    """Start AI recommendation task for final contents."""
    from services.agent_runner import start_recommend, has_running_task

    if has_running_task():
        raise HTTPException(409, "a task is already running, please wait")
    task_id = await start_recommend(persona_id)
    return {"task_id": task_id}


@router.post("/select/publish")
def select_publish(req: SelectPublishRequest):
    """Batch create publication records for selected contents."""
    from db import get_connection

    if not req.content_ids:
        raise HTTPException(400, "content_ids is required")

    conn = get_connection()
    try:
        created = []
        for cid in req.content_ids:
            content = get_content(cid)
            if not content:
                continue
            if content["status"] != "final":
                continue
            # Create publication record
            conn.execute(
                "INSERT INTO publications (content_id, persona_id, platform, status) VALUES (?, ?, ?, 'draft')",
                (cid, req.persona_id, content["platform"]),
            )
            # Update content status to publishing
            conn.execute(
                "UPDATE contents SET status='publishing', updated_at=datetime('now','localtime') WHERE content_id=?",
                (cid,),
            )
            conn.execute(
                "INSERT INTO status_log (content_id, from_status, to_status, operator, note) VALUES (?, 'final', 'publishing', 'ui-select', 'Selected for publishing')",
                (cid,),
            )
            created.append(cid)
        conn.commit()
        return {"published": len(created), "content_ids": created}
    finally:
        conn.close()
