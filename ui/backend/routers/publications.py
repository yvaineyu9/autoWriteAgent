from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from models import PublicationOut, RecordMetricsRequest, MetricsOut, UpdatePublicationRequest
from services.db_service import list_publications, get_publication, upsert_metrics, update_publication

router = APIRouter()


@router.get("/publications", response_model=list)
def get_publications(status: Optional[str] = Query(None), persona_id: Optional[str] = Query(None)):
    return list_publications(status, persona_id)


@router.patch("/publications/{pub_id}")
def patch_publication(pub_id: int, req: UpdatePublicationRequest):
    if req.status not in ("draft", "published"):
        raise HTTPException(400, "status must be 'draft' or 'published'")
    result = update_publication(pub_id, req.status, req.post_url)
    if not result:
        raise HTTPException(404, "publication not found")
    return result


@router.put("/publications/{pub_id}/metrics")
def record_metrics(pub_id: int, req: RecordMetricsRequest):
    pub = get_publication(pub_id)
    if not pub:
        raise HTTPException(404, "publication not found")
    row = upsert_metrics(pub_id, req.views, req.likes, req.collects, req.comments, req.shares)
    return row
