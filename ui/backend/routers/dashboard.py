from typing import Optional

from fastapi import APIRouter, Query
from services.db_service import dashboard_stats

router = APIRouter()


@router.get("/dashboard")
def get_dashboard(persona_id: Optional[str] = Query(None)):
    return dashboard_stats(persona_id)
