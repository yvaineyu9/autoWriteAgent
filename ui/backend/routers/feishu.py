"""Feishu integration: send generated typeset images to the configured group."""
import asyncio
import os

from fastapi import APIRouter, HTTPException

from services.db_service import get_content, DATA_CONTENT_DIR, mark_content_published
from services.feishu import FeishuError, upload_image, send_post_message

router = APIRouter()


@router.post("/contents/{content_id}/send-to-feishu")
async def send_content_to_feishu(content_id: str):
    """Upload all page-*.jpg/png files for a content to Feishu and send as one post message."""
    chat_id = os.environ.get("FEISHU_CHAT_ID")
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if not (chat_id and app_id and app_secret):
        raise HTTPException(500, "Feishu credentials not configured")

    content = get_content(content_id)
    if not content:
        raise HTTPException(404, "content not found")

    typeset_dir = os.path.join(DATA_CONTENT_DIR, "typeset", content_id)
    if not os.path.isdir(typeset_dir):
        raise HTTPException(404, "no generated images")

    files = sorted(
        f
        for f in os.listdir(typeset_dir)
        if f.startswith("page-") and (f.endswith(".jpg") or f.endswith(".png"))
    )
    if not files:
        raise HTTPException(404, "no generated images")

    def _do_send() -> str:
        keys = [upload_image(os.path.join(typeset_dir, fname)) for fname in files]
        return send_post_message(chat_id, keys)

    try:
        message_id = await asyncio.to_thread(_do_send)
    except FeishuError as e:
        raise HTTPException(502, str(e))
    except FileNotFoundError as e:
        raise HTTPException(500, f"image file missing: {e}")

    # Message sent successfully -> flip content status to published.
    mark_content_published(content_id, f"sent to feishu (msg {message_id[:8]})")

    return {"ok": True, "message_id": message_id, "image_count": len(files)}
