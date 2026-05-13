"""HefterPro FastAPI application entry point."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .routers import handwriting, hefter, projects, trading
from .services import demo_portfolio as portfolio_svc
from .services import trading_bot as bot_svc
from .services.session_manager import load_active_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.WARNING)
log = logging.getLogger("hefterpro")


async def _resume_bot_if_saved() -> None:
    """On server start: restore the last active bot session from disk."""
    await asyncio.sleep(3)  # wait for app to be fully ready
    session = load_active_session()
    if not session:
        return
    sid = session["session_id"]
    log.info("Resuming saved bot session: %s", sid)
    try:
        from .models.trading_schemas import BotConfig
        svc = portfolio_svc.get_or_create_session(
            session_id=sid,
            initial_balance=session["initial_balance"],
        )
        config_obj = BotConfig(
            session_id=sid,
            markets=session["markets"],
            min_confidence=session.get("min_confidence", 0.55),
            trade_interval_minutes=session.get("trade_interval_minutes", 8),
            max_position_pct=session.get("max_position_pct", 0.60),
            risk_per_trade_pct=session.get("risk_per_trade_pct", 0.15),
        )
        # No WS broadcast on startup — frontend reconnects via WebSocket later
        bot = bot_svc.create_bot(config_obj)
        bot.start()
        log.info("Bot auto-resumed for session %s", sid)

        from .services.trade_tracker import get_tracker
        tracker = get_tracker(sid)
        tracker.log_activity(
            "start",
            "Server neu gestartet — Bot wurde automatisch fortgesetzt.",
            emoji="🔄",
        )
    except Exception as exc:
        log.error("Failed to resume bot session: %s", exc)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    asyncio.create_task(_resume_bot_if_saved())
    yield


app = FastAPI(
    title="HefterPro",
    description="Text → Handschrift & automatische Hefterblatt-Erstellung.",
    version="2.0.0",
    lifespan=_lifespan,
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
app.include_router(trading.router, prefix="/api/trading", tags=["trading"])


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": app.version}


@app.api_route("/api/ping", methods=["GET", "HEAD"])
def ping() -> dict:
    """Keep-alive endpoint — used by UptimeRobot to prevent Render free tier sleep."""
    return {"pong": True}


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
        # Trading branch: root opens the trading dashboard
        trading_page = _FRONTEND / "trading.html"
        if trading_page.exists():
            return FileResponse(trading_page, headers=_NO_CACHE)
        return FileResponse(_FRONTEND / "handwriting.html", headers=_NO_CACHE)

    @app.get("/{page}.html")
    def page(page: str) -> FileResponse:
        path = _FRONTEND / f"{page}.html"
        if path.exists():
            return FileResponse(path, headers=_NO_CACHE)
        return FileResponse(_FRONTEND / "handwriting.html", headers=_NO_CACHE)
