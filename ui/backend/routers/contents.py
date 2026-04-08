import asyncio
import os
import sys
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from models import ContentOut, ContentBodyOut, SaveContentBodyRequest, TypesetRequest
from services.db_service import list_contents, get_content, read_content_body, write_content_body, delete_content, DATA_CONTENT_DIR

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
XHS_CLI_V1 = os.path.join(PROJECT_ROOT, "tools", "xhs-cli", "xhs-gen.js")
XHS_CLI_V2 = os.path.join(PROJECT_ROOT, "tools", "xhs-cli", "xhs-gen-v2.js")
XHS_ASSETS = os.path.join(PROJECT_ROOT, "tools", "xhs-cli", "assets")

router = APIRouter()


@router.get("/contents", response_model=list)
def get_contents(status: Optional[str] = Query(None), platform: Optional[str] = Query(None)):
    return list_contents(status, platform)


@router.get("/contents/{content_id}/body")
def get_content_body(content_id: str):
    content = get_content(content_id)
    if not content:
        raise HTTPException(404, "content not found")
    body = read_content_body(content["file_path"])
    if body is None:
        raise HTTPException(404, "content file not found on disk")
    return ContentBodyOut(
        content_id=content["content_id"],
        title=content["title"],
        body=body,
        platform=content["platform"],
    )


@router.put("/contents/{content_id}/body")
def save_content_body(content_id: str, req: SaveContentBodyRequest):
    content = get_content(content_id)
    if not content:
        raise HTTPException(404, "content not found")
    write_content_body(content["file_path"], req.body)
    return {"content_id": content_id, "saved": True}


@router.delete("/contents/{content_id}")
def remove_content(content_id: str):
    content = get_content(content_id)
    if not content:
        raise HTTPException(404, "content not found")
    if content["status"] == "published":
        raise HTTPException(400, "cannot delete published content")
    if not delete_content(content_id):
        raise HTTPException(500, "delete failed")
    return {"deleted": True}


@router.get("/typeset/covers")
def list_covers():
    if not os.path.isdir(XHS_ASSETS):
        return []
    covers = [f for f in os.listdir(XHS_ASSETS) if f.endswith((".jpg", ".png")) and "cover" in f]
    return sorted(covers)


@router.get("/typeset/covers/{filename}")
def get_cover_image(filename: str):
    file_path = os.path.join(XHS_ASSETS, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(404, "cover not found")
    media = "image/jpeg" if filename.endswith(".jpg") else "image/png"
    return FileResponse(file_path, media_type=media)


@router.post("/contents/{content_id}/typeset")
async def typeset_content(content_id: str, req: TypesetRequest):
    content = get_content(content_id)
    if not content:
        raise HTTPException(404, "content not found")
    body = read_content_body(content["file_path"])
    if body is None:
        raise HTTPException(404, "content file not found on disk")

    output_dir = os.path.join(DATA_CONTENT_DIR, "typeset", content_id)
    os.makedirs(output_dir, exist_ok=True)

    for f in os.listdir(output_dir):
        if f.endswith((".jpg", ".png")) and f.startswith("page-"):
            os.remove(os.path.join(output_dir, f))

    tmp_input = os.path.join(output_dir, "_input.md")
    with open(tmp_input, "w", encoding="utf-8") as f:
        f.write(body)

    cli_script = XHS_CLI_V1 if req.tool == "v1" else XHS_CLI_V2
    cmd = ["node", cli_script, "-i", tmp_input, "-o", output_dir]

    if req.cover_url:
        if req.cover_url.startswith("asset:"):
            asset_name = req.cover_url.replace("asset:", "")
            asset_path = os.path.join(XHS_ASSETS, asset_name)
            if os.path.isfile(asset_path):
                cmd += ["--cover", asset_path]
        else:
            import urllib.request
            cover_path = os.path.join(output_dir, "_cover_input.jpg")
            try:
                urllib.request.urlretrieve(req.cover_url, cover_path)
                cmd += ["--cover", cover_path]
            except Exception:
                pass

    if req.avatar_url:
        import urllib.request
        avatar_path = os.path.join(output_dir, "_avatar_input.jpg")
        try:
            urllib.request.urlretrieve(req.avatar_url, avatar_path)
            cmd += ["--author-avatar", avatar_path]
        except Exception:
            pass

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=PROJECT_ROOT,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise HTTPException(500, "typeset failed: {}".format(stderr.decode()))

    images = sorted([f for f in os.listdir(output_dir) if (f.endswith(".jpg") or f.endswith(".png")) and f.startswith("page-")])
    return {"content_id": content_id, "images": images, "count": len(images), "tool": req.tool}


@router.get("/contents/{content_id}/typeset/{filename}")
def get_typeset_image(content_id: str, filename: str):
    file_path = os.path.join(DATA_CONTENT_DIR, "typeset", content_id, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(404, "image not found")
    media = "image/jpeg" if filename.endswith(".jpg") else "image/png"
    return FileResponse(file_path, media_type=media)
