"""Trading bot API router — REST endpoints + WebSocket for real-time updates."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

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
from ..services.trading_bot import build_market_analysis, get_ai_signal

log = logging.getLogger("trading.router")
router = APIRouter()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, ws: WebSocket) -> None:
        await ws.accept()
        if session_id not in self._connections:
            self._connections[session_id] = []
        self._connections[session_id].append(ws)

    def disconnect(self, session_id: str, ws: WebSocket) -> None:
        if session_id in self._connections:
            self._connections[session_id].discard(ws) if hasattr(self._connections[session_id], 'discard') else None
            try:
                self._connections[session_id].remove(ws)
            except ValueError:
                pass

    async def broadcast(self, session_id: str, event_type: str, data: dict) -> None:
        msg = json.dumps({"type": event_type, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()})
        dead = []
        for ws in self._connections.get(session_id, []):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(session_id, ws)


ws_manager = ConnectionManager()


# ─── Markets ──────────────────────────────────────────────────────────────────

@router.get("/markets", response_model=list[MarketSymbol])
async def get_markets():
    """List all available trading markets."""
    return list_markets()


@router.get("/market/{symbol}/candles")
async def get_market_candles(symbol: str, interval: str = "1h", period: str = "5d"):
    """Get OHLCV candle data for a symbol."""
    candles = await fetch_candles(symbol, period=period, interval=interval)
    if not candles:
        candles = await fetch_daily_candles(symbol, days=90)
    if not candles:
        raise HTTPException(status_code=404, detail=f"No data available for {symbol}")
    return {"symbol": symbol, "interval": interval, "candles": [c.model_dump(mode="json") for c in candles]}


@router.get("/market/{symbol}/analysis")
async def get_market_analysis(symbol: str):
    """Get full market analysis including technical indicators and AI signal."""
    market_data = await build_market_analysis(symbol)
    if not market_data:
        raise HTTPException(status_code=404, detail=f"Cannot analyze {symbol}")

    signal = await get_ai_signal(symbol, market_data)
    market_data.signal = signal

    return market_data.model_dump(mode="json")


@router.get("/market/{symbol}/price")
async def get_price(symbol: str):
    """Get current price for a symbol."""
    price = await get_current_price(symbol)
    if price is None:
        raise HTTPException(status_code=404, detail=f"Price unavailable for {symbol}")
    info = await get_market_info(symbol)
    return {"symbol": symbol, "price": price, **info}


# ─── Demo Portfolio ────────────────────────────────────────────────────────────

@router.post("/demo/start")
async def start_demo(req: StartDemoRequest):
    """Create a new demo trading session."""
    svc = portfolio_svc.get_or_create_session(initial_balance=req.initial_balance)
    p = svc._portfolio
    return {
        "session_id": svc.session_id,
        "initial_balance": p.initial_balance,
        "currency": req.currency,
        "message": f"Demo session created with €{p.initial_balance:.2f} virtual funds",
        "created_at": p.created_at.isoformat(),
    }


@router.get("/demo/{session_id}/portfolio")
async def get_portfolio(session_id: str):
    """Get current demo portfolio state with real-time prices."""
    svc = portfolio_svc.get_session(session_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Session not found")

    # Fetch current prices for all positions
    prices: dict[str, float] = {}
    p = svc._portfolio
    if p:
        for pos in p.positions:
            price = await get_current_price(pos.symbol)
            if price:
                prices[pos.symbol] = price

    portfolio = svc.get_portfolio(prices)
    return portfolio.model_dump(mode="json")


@router.post("/demo/trade")
async def execute_manual_trade(req: ManualTradeRequest):
    """Execute a manual trade in the demo portfolio."""
    svc = portfolio_svc.get_session(req.session_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Session not found")

    current_price = await get_current_price(req.symbol)
    if not current_price:
        raise HTTPException(status_code=400, detail=f"Cannot get price for {req.symbol}")

    sym_info = get_symbol_info(req.symbol)
    success, message, trade = svc.execute_trade(
        symbol=req.symbol,
        name=sym_info.name,
        market_type=sym_info.market_type,
        action=req.action,
        amount_eur=req.amount_eur,
        current_price=current_price,
    )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    # Broadcast to WebSocket
    await ws_manager.broadcast(req.session_id, "trade", {
        "trade": trade.model_dump(mode="json"),
        "message": message,
    })

    return {"success": True, "message": message, "trade": trade.model_dump(mode="json")}


@router.get("/demo/{session_id}/trades")
async def get_trade_history(session_id: str):
    """Get trade history for a demo session."""
    svc = portfolio_svc.get_session(session_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Session not found")
    trades = svc.get_trades()
    return {"session_id": session_id, "trades": [t.model_dump(mode="json") for t in trades]}


@router.delete("/demo/{session_id}")
async def reset_demo(session_id: str, initial_balance: float = 10.0):
    """Reset a demo session (start fresh)."""
    # Stop bot if running
    await bot_svc.stop_bot(session_id)
    # Create new session with same ID concept (just create new)
    svc = portfolio_svc.get_or_create_session(initial_balance=initial_balance)
    return {"session_id": svc.session_id, "message": "New demo session created"}


# ─── Bot Control ──────────────────────────────────────────────────────────────

@router.post("/bot/start")
async def start_bot(config: BotConfig):
    """Start the autonomous trading bot for a session."""
    svc = portfolio_svc.get_session(config.session_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Session not found")

    existing_bot = bot_svc.get_bot(config.session_id)
    if existing_bot and existing_bot.is_running():
        return {"message": "Bot already running", "session_id": config.session_id}

    async def broadcast_cb(event_type: str, data: dict):
        await ws_manager.broadcast(config.session_id, event_type, data)

    bot = bot_svc.create_bot(config, broadcast_cb)
    bot.start()

    return {
        "message": "Trading bot started",
        "session_id": config.session_id,
        "markets": config.markets,
        "scan_interval_minutes": config.trade_interval_minutes,
    }


@router.post("/bot/{session_id}/stop")
async def stop_bot(session_id: str):
    """Stop the autonomous trading bot."""
    stopped = await bot_svc.stop_bot(session_id)
    return {"message": "Bot stopped" if stopped else "No bot running", "session_id": session_id}


@router.get("/bot/{session_id}/status")
async def get_bot_status(session_id: str):
    """Get bot status and last signals."""
    bot = bot_svc.get_bot(session_id)
    if not bot:
        return {"running": False, "session_id": session_id}
    return {
        "running": bot.is_running(),
        "session_id": session_id,
        "scan_count": bot.scan_count,
        "last_scan": bot.last_scan.isoformat() if bot.last_scan else None,
        "markets": bot.config.markets,
        "last_signals": {
            sym: sig.model_dump(mode="json")
            for sym, sig in bot.last_signals.items()
        },
    }


# ─── Quick Scan ───────────────────────────────────────────────────────────────

@router.get("/scan/{symbol}")
async def quick_scan(symbol: str):
    """Quick AI analysis scan for a single symbol — no portfolio required."""
    market_data = await build_market_analysis(symbol)
    if not market_data:
        raise HTTPException(status_code=404, detail=f"Cannot analyze {symbol}")

    signal = await get_ai_signal(symbol, market_data)
    tech_score, tech_factors = score_signal(
        market_data.analysis.indicators,
        market_data.analysis.current_price,
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
    """Real-time updates via WebSocket for a trading session."""
    await ws_manager.connect(session_id, websocket)
    log.info("WebSocket connected for session %s", session_id)
    try:
        # Send initial portfolio state
        svc = portfolio_svc.get_session(session_id)
        if svc and svc._portfolio:
            await websocket.send_text(json.dumps({
                "type": "connected",
                "data": {"session_id": session_id, "message": "Connected to trading stream"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))

        # Keep alive and handle incoming messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg = json.loads(data)
                cmd = msg.get("command")
                if cmd == "ping":
                    await websocket.send_text(json.dumps({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()}))
                elif cmd == "get_portfolio":
                    svc = portfolio_svc.get_session(session_id)
                    if svc:
                        portfolio = svc.get_portfolio({})
                        await websocket.send_text(json.dumps({
                            "type": "portfolio_update",
                            "data": {"portfolio": portfolio.model_dump(mode="json")},
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }))
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_text(json.dumps({"type": "heartbeat", "timestamp": datetime.now(timezone.utc).isoformat()}))
    except WebSocketDisconnect:
        ws_manager.disconnect(session_id, websocket)
        log.info("WebSocket disconnected for session %s", session_id)
    except Exception as exc:
        log.error("WebSocket error for %s: %s", session_id, exc)
        ws_manager.disconnect(session_id, websocket)
