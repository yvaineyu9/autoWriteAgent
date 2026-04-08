from fastapi import APIRouter
from services.db_service import list_personas

router = APIRouter()


@router.get("/personas")
def get_personas():
    return list_personas()
