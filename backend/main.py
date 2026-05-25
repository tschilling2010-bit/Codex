"""HefterPro FastAPI application entry point."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .routers import handwriting, hefter, projects

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("hefterpro")

app = FastAPI(
    title="HefterPro",
    description="Text → Handschrift & automatische Hefterblatt-Erstellung.",
    version="2.0.0",
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


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": app.version}


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

_FRONTEND = Path(config.FRONTEND_DIR)
if _FRONTEND.exists():
    _assets = _FRONTEND / "assets"
    _assets.mkdir(exist_ok=True)
    app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    _css = _FRONTEND / "css"
    if _css.exists():
        app.mount("/css", StaticFiles(directory=str(_css)), name="css")

    _js = _FRONTEND / "js"
    if _js.exists():
        app.mount("/js", StaticFiles(directory=str(_js)), name="js")

    _NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_FRONTEND / "dashboard.html", headers=_NO_CACHE)

    @app.get("/{page}.html")
    def page(page: str) -> FileResponse:
        path = _FRONTEND / f"{page}.html"
        if path.exists():
            return FileResponse(path, headers=_NO_CACHE)
        return FileResponse(_FRONTEND / "handwriting.html", headers=_NO_CACHE)
