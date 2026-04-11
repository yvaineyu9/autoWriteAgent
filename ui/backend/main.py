import os
import sys

# Add project tools/ to sys.path so we can import db module
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "tools"))

# Load PROJECT_ROOT/.env into os.environ before importing routers.
# .env is gitignored and only present on the deployment host.
_env_path = os.path.join(PROJECT_ROOT, ".env")
if os.path.isfile(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            _v = _v.strip().strip('"').strip("'")
            os.environ.setdefault(_k.strip(), _v)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from routers import ideas, contents, publications, tasks, personas, dashboard, select, feishu

app = FastAPI(title="autoWriteAgent UI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ideas.router, prefix="/api")
app.include_router(contents.router, prefix="/api")
app.include_router(publications.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(personas.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(select.router, prefix="/api")
app.include_router(feishu.router, prefix="/api")

# Serve frontend static files
DIST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")

if os.path.isdir(DIST_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Try static file first, fallback to index.html (SPA)
        file_path = os.path.join(DIST_DIR, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(DIST_DIR, "index.html"))
