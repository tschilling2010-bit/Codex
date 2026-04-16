"""HefterPro FastAPI application entry point.

This module wires the routers together, serves the static frontend, and
configures logging.  There is no authentication of any kind by design.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .routers import handwriting, hefter, projects, settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("hefterpro")

app = FastAPI(
    title="HefterPro",
    description="Text → Handschrift & automatische Hefterblatt-Erstellung.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error for %s", request.url)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": str(exc)},
    )


app.include_router(handwriting.router, prefix="/api/handwriting", tags=["handwriting"])
app.include_router(hefter.router, prefix="/api/hefter", tags=["hefter"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": app.version}


# Serve generated exports so the frontend can link to them directly.
app.mount(
    "/files/exports",
    StaticFiles(directory=str(config.EXPORTS_DIR)),
    name="exports",
)
app.mount(
    "/files/templates",
    StaticFiles(directory=str(config.TEMPLATES_DIR)),
    name="templates",
)

# Static frontend.
_FRONTEND = Path(config.FRONTEND_DIR)
if _FRONTEND.exists():
    _assets = _FRONTEND / "assets"
    _assets.mkdir(exist_ok=True)
    app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")
    app.mount("/css", StaticFiles(directory=str(_FRONTEND / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(_FRONTEND / "js")), name="js")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_FRONTEND / "index.html")

    @app.get("/{page}.html")
    def page(page: str) -> FileResponse:
        path = _FRONTEND / f"{page}.html"
        if path.exists():
            return FileResponse(path)
        return FileResponse(_FRONTEND / "index.html")
