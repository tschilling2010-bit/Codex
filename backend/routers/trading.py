"""Trading bot API router — REST endpoints + WebSocket."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from ..models.trading_schemas import (
    BotConfig, ManualTradeRequest, MarketSymbol, StartDemoRequest, TradeAction
)
from ..services import demo_portfolio as portfolio_svc
from ..services import trading_bot as bot_svc
from ..services.market_data import (
    fetch_candles, fetch_daily_candles, get_current_price,
    get_market_info, get_symbol_info, list_markets
)
from ..services.technical_analysis import (
    calculate_indicators, determine_trend, find_support_resistance, score_signal
)
from ..services.trade_tracker import get_tracker
from ..services.ai_trader import get_ai_status, set_api_key
from ..services.session_manager import clear_active_session, load_active_session, save_active_session
from ..services.trading_bot import build_market_analysis, get_ai_signal

log = logging.getLogger("trading.router")
router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(session_id, []).append(ws)

    def disconnect(self, session_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(session_id, [])
        try:
            conns.remove(ws)
        except ValueError:
            pass

    async def broadcast(self, session_id: str, event_type: str, data: dict) -> None:
        msg = json.dumps({
            "type": event_type, "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        dead = []
        for ws in list(self._connections.get(session_id, [])):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(session_id, ws)


ws_manager = ConnectionManager()


# ─── Config ───────────────────────────────────────────────────────────────────

@router.get("/config/status")
async def config_status():
    """Return AI configuration and health status."""
    return get_ai_status()


@router.post("/config/key")
async def set_key(body: dict):
    """Set Anthropic API key at runtime (stored in memory, not persisted)."""
    key = body.get("key", "").strip()
    if not key:
        raise HTTPException(400, "Kein API-Key angegeben")
    ok = set_api_key(key)
    if not ok:
        raise HTTPException(400, "Ungültiger API-Key (muss mit sk-ant- beginnen)")
    # Update persisted session with new key so it survives restarts
    saved = load_active_session()
    if saved:
        save_active_session(**{**saved, "api_key": key})
    return {"success": True, "message": "API-Key gesetzt — KI ist jetzt aktiv"}


# ─── Markets ──────────────────────────────────────────────────────────────────

@router.get("/markets", response_model=list[MarketSymbol])
async def get_markets():
    return list_markets()


@router.get("/market/{symbol}/candles")
async def get_market_candles(symbol: str, interval: str = "1h", period: str = "5d"):
    candles = await fetch_candles(symbol, period=period, interval=interval)
    if not candles:
        candles = await fetch_daily_candles(symbol, days=90)
    if not candles:
        raise HTTPException(404, f"Keine Daten für {symbol}")
    return {"symbol": symbol, "interval": interval, "candles": [c.model_dump(mode="json") for c in candles]}


@router.get("/market/{symbol}/analysis")
async def get_market_analysis(symbol: str):
    market_data = await build_market_analysis(symbol)
    if not market_data:
        raise HTTPException(404, f"Analyse für {symbol} nicht möglich")
    signal = await get_ai_signal(symbol, market_data)
    market_data.signal = signal
    return market_data.model_dump(mode="json")


@router.get("/market/{symbol}/price")
async def get_price(symbol: str):
    price = await get_current_price(symbol)
    if price is None:
        raise HTTPException(404, f"Kurs nicht verfügbar für {symbol}")
    info = await get_market_info(symbol)
    return {"symbol": symbol, "price": price, **info}


# ─── Demo Session ─────────────────────────────────────────────────────────────

@router.post("/demo/start")
async def start_demo(req: StartDemoRequest):
    """
    Create a new demo trading session.
    If auto_start_bot=True (default), the bot begins scanning markets immediately.
    """
    svc = portfolio_svc.get_or_create_session(initial_balance=req.initial_balance)
    sid = svc.session_id

    bot_started = False
    if req.auto_start_bot:
        # Start bot immediately — it will do its first scan right away
        config = BotConfig(
            session_id=sid,
            markets=req.markets,
            min_confidence=0.60,
            trade_interval_minutes=15,
            max_position_pct=0.30,
            risk_per_trade_pct=0.03,
        )
        async def broadcast_cb(event_type: str, data: dict):
            await ws_manager.broadcast(sid, event_type, data)

        bot = bot_svc.create_bot(config, broadcast_cb)
        bot.start()
        bot_started = True

        tracker = get_tracker(sid)
        tracker.log_activity(
            "start",
            f"Demo-Session gestartet mit €{req.initial_balance:.2f} virtuellem Kapital.",
            detail=f"Bot überwacht {len(req.markets)} Märkte: {', '.join(req.markets)}",
            emoji="🚀",
        )

        # Persist session (incl. API key) so it survives server restarts
        from ..services.ai_trader import get_ai_status
        ai_st = get_ai_status()
        from ..services import ai_trader as _at
        save_active_session(
            session_id=sid,
            initial_balance=req.initial_balance,
            markets=req.markets,
            min_confidence=config.min_confidence,
            trade_interval_minutes=config.trade_interval_minutes,
            max_position_pct=config.max_position_pct,
            risk_per_trade_pct=config.risk_per_trade_pct,
            api_key=_at._runtime_key or "",
        )

    return {
        "session_id": sid,
        "initial_balance": req.initial_balance,
        "currency": req.currency,
        "bot_started": bot_started,
        "markets": req.markets,
        "message": (
            f"Demo-Session erstellt mit €{req.initial_balance:.2f}. "
            f"Der Bot startet sofort und analysiert {len(req.markets)} Märkte."
        ),
    }


@router.get("/demo/{session_id}/portfolio")
async def get_portfolio(session_id: str):
    svc = portfolio_svc.get_session(session_id)
    if not svc:
        raise HTTPException(404, "Session nicht gefunden")
    prices: dict[str, float] = {}
    p = svc._portfolio
    if p:
        for pos in p.positions:
            price = await get_current_price(pos.symbol)
            if price:
                prices[pos.symbol] = price
    return svc.get_portfolio(prices).model_dump(mode="json")


@router.post("/demo/trade")
async def execute_manual_trade(req: ManualTradeRequest):
    svc = portfolio_svc.get_session(req.session_id)
    if not svc:
        raise HTTPException(404, "Session nicht gefunden")

    current_price = await get_current_price(req.symbol)
    if not current_price:
        raise HTTPException(400, f"Kurs nicht abrufbar für {req.symbol}")

    sym_info = get_symbol_info(req.symbol)
    success, message, trade = svc.execute_trade(
        symbol=req.symbol, name=sym_info.name,
        market_type=sym_info.market_type, action=req.action,
        amount_eur=req.amount_eur, current_price=current_price,
    )
    if not success:
        raise HTTPException(400, message)

    # Track outcome for manual buys
    if req.action == TradeAction.BUY and trade:
        tracker = get_tracker(req.session_id)
        tracker.record_trade_open(trade, req.amount_eur)
        tracker.log_activity("trade", f"Manueller KAUF {req.symbol}: €{req.amount_eur:.2f}", symbol=req.symbol, emoji="🖐️")

    await ws_manager.broadcast(req.session_id, "trade", {
        "trade": trade.model_dump(mode="json"), "message": message,
    })
    return {"success": True, "message": message, "trade": trade.model_dump(mode="json")}


@router.get("/demo/{session_id}/trades")
async def get_trade_history(session_id: str):
    svc = portfolio_svc.get_session(session_id)
    if not svc:
        raise HTTPException(404, "Session nicht gefunden")
    return {"session_id": session_id, "trades": [t.model_dump(mode="json") for t in svc.get_trades()]}


@router.get("/demo/{session_id}/outcomes")
async def get_outcomes(session_id: str, limit: int = 30):
    """Get all trade outcomes with 'was wäre passiert' explanations."""
    tracker = get_tracker(session_id)
    outcomes = tracker.get_outcomes(limit)
    return {
        "session_id": session_id,
        "outcomes": [o.model_dump(mode="json") for o in outcomes],
        "summary": tracker.get_performance_summary(),
    }


@router.get("/demo/{session_id}/activity")
async def get_activity(session_id: str, limit: int = 50):
    """Get bot activity log."""
    tracker = get_tracker(session_id)
    return {
        "session_id": session_id,
        "activity": [a.model_dump(mode="json") for a in tracker.get_activity(limit)],
    }


@router.get("/demo/{session_id}/performance")
async def get_performance(session_id: str):
    """Get comprehensive performance stats."""
    svc = portfolio_svc.get_session(session_id)
    if not svc:
        raise HTTPException(404, "Session nicht gefunden")

    tracker = get_tracker(session_id)
    summary = tracker.get_performance_summary()
    p = svc._portfolio

    prices: dict[str, float] = {}
    if p:
        for pos in p.positions:
            price = await get_current_price(pos.symbol)
            if price:
                prices[pos.symbol] = price
    portfolio = svc.get_portfolio(prices)

    return {
        "session_id": session_id,
        "initial_balance": portfolio.initial_balance,
        "current_value": portfolio.total_value,
        "total_pnl": portfolio.total_pnl,
        "total_pnl_pct": portfolio.total_pnl_pct,
        "trade_stats": summary,
        "portfolio": portfolio.model_dump(mode="json"),
    }


@router.delete("/demo/{session_id}")
async def reset_demo(session_id: str):
    await bot_svc.stop_bot(session_id)
    clear_active_session()
    svc = portfolio_svc.get_or_create_session(initial_balance=10.0)
    return {"session_id": svc.session_id, "message": "Neue Demo-Session erstellt"}


# ─── Bot Control ──────────────────────────────────────────────────────────────

@router.post("/bot/start")
async def start_bot(config: BotConfig):
    svc = portfolio_svc.get_session(config.session_id)
    if not svc:
        raise HTTPException(404, "Session nicht gefunden")

    existing = bot_svc.get_bot(config.session_id)
    if existing and existing.is_running():
        return {"message": "Bot läuft bereits", "session_id": config.session_id}

    async def broadcast_cb(event_type: str, data: dict):
        await ws_manager.broadcast(config.session_id, event_type, data)

    bot = bot_svc.create_bot(config, broadcast_cb)
    bot.start()
    return {
        "message": "Trading Bot gestartet",
        "session_id": config.session_id,
        "markets": config.markets,
    }


@router.post("/bot/{session_id}/stop")
async def stop_bot(session_id: str):
    stopped = await bot_svc.stop_bot(session_id)
    return {"message": "Bot gestoppt" if stopped else "Kein Bot aktiv", "session_id": session_id}


@router.get("/bot/{session_id}/status")
async def get_bot_status(session_id: str):
    bot = bot_svc.get_bot(session_id)
    if not bot:
        return {"running": False, "session_id": session_id}
    return {
        "running": bot.is_running(),
        "session_id": session_id,
        "scan_count": bot.scan_count,
        "last_scan": bot.last_scan.isoformat() if bot.last_scan else None,
        "markets": bot.config.markets,
        "last_signals": {sym: sig.model_dump(mode="json") for sym, sig in bot.last_signals.items()},
    }


# ─── Quick Scan ───────────────────────────────────────────────────────────────

@router.get("/scan/{symbol}")
async def quick_scan(symbol: str):
    market_data = await build_market_analysis(symbol)
    if not market_data:
        raise HTTPException(404, f"Analyse für {symbol} nicht möglich")
    signal = await get_ai_signal(symbol, market_data)
    tech_score, tech_factors = score_signal(
        market_data.analysis.indicators, market_data.analysis.current_price
    )
    return {
        "symbol": symbol,
        "name": market_data.name,
        "current_price": market_data.analysis.current_price,
        "trend": market_data.analysis.trend,
        "technical_score": tech_score,
        "technical_factors": tech_factors,
        "signal": signal.model_dump(mode="json"),
        "indicators": market_data.analysis.indicators.model_dump(mode="json"),
    }


# ─── WebSocket ────────────────────────────────────────────────────────────────

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await ws_manager.connect(session_id, websocket)
    log.info("WS connected: %s", session_id)
    try:
        await websocket.send_text(json.dumps({
            "type": "connected",
            "data": {"session_id": session_id},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg = json.loads(raw)
                cmd = msg.get("command")
                if cmd == "ping":
                    await websocket.send_text(json.dumps({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()}))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "heartbeat", "timestamp": datetime.now(timezone.utc).isoformat()}))
    except WebSocketDisconnect:
        ws_manager.disconnect(session_id, websocket)
    except Exception as exc:
        log.error("WS error %s: %s", session_id, exc)
        ws_manager.disconnect(session_id, websocket)
