"""Trading bot REST API endpoints."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from ..services.ai_signal import get_signal
from ..services.market_data import SUPPORTED_PAIRS, get_klines, get_multi_ticker, get_ticker
from ..services.paper_trader import trader
from ..services.technical_analysis import compute_all

log = logging.getLogger("trading")
router = APIRouter()

# ------------------------------------------------------------------ #
#  Background bot loop                                                 #
# ------------------------------------------------------------------ #

_bot_task: Optional[asyncio.Task] = None


async def _bot_loop() -> None:
    log.info("Trading bot started")
    while trader.state.running:
        for symbol in list(trader.state.selected_symbols):
            try:
                await _run_cycle(symbol)
            except Exception as exc:
                log.warning("Cycle error for %s: %s", symbol, exc)
                trader.state.error = str(exc)
        # wait based on interval
        interval = trader.state.interval
        sleep_map = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
        await asyncio.sleep(sleep_map.get(interval, 3600))
    log.info("Trading bot stopped")


async def _run_cycle(symbol: str) -> None:
    interval = trader.state.interval
    klines = await get_klines(symbol, interval, limit=150)
    indicators = compute_all(klines)
    price = indicators["price"]

    # check existing position exits first
    closed = trader.check_exits(symbol, price)
    if closed:
        log.info("Position closed: %s", closed)

    # get AI signal
    signal = await get_signal(symbol, indicators, interval)
    trader.state.last_analysis[symbol] = indicators
    trader.state.last_signal[symbol] = {**signal, "ts": int(time.time()), "price": price}
    trader.state.error = None

    # act on signal if no open position
    if symbol not in trader.positions:
        action = signal.get("action", "HOLD")
        confidence = signal.get("confidence", 0)
        if action == "BUY" and confidence >= 55:
            trader.open_position(
                symbol=symbol,
                side="long",
                price=price,
                stop_loss_pct=signal.get("stop_loss_pct", 1.5),
                take_profit_pct=signal.get("take_profit_pct", 3.0),
            )
            log.info("Opened LONG %s @ %s (confidence %s%%)", symbol, price, confidence)
        elif action == "SELL" and confidence >= 55:
            trader.open_position(
                symbol=symbol,
                side="short",
                price=price,
                stop_loss_pct=signal.get("stop_loss_pct", 1.5),
                take_profit_pct=signal.get("take_profit_pct", 3.0),
            )
            log.info("Opened SHORT %s @ %s (confidence %s%%)", symbol, price, confidence)


# ------------------------------------------------------------------ #
#  Request/response models                                             #
# ------------------------------------------------------------------ #

class BotConfig(BaseModel):
    symbols: List[str] = ["BTCUSDT"]
    interval: str = "1h"


class ManualTradeRequest(BaseModel):
    symbol: str
    side: str   # "long" | "short"
    stop_loss_pct: float = 1.5
    take_profit_pct: float = 3.0


# ------------------------------------------------------------------ #
#  Endpoints                                                           #
# ------------------------------------------------------------------ #

@router.get("/markets")
async def list_markets() -> Dict[str, Any]:
    tickers = await get_multi_ticker(SUPPORTED_PAIRS)
    return {"pairs": SUPPORTED_PAIRS, "tickers": tickers}


@router.get("/analysis/{symbol}")
async def analyze(symbol: str, interval: str = "1h") -> Dict[str, Any]:
    try:
        klines = await get_klines(symbol.upper(), interval, limit=150)
        indicators = compute_all(klines)
        signal = await get_signal(symbol.upper(), indicators, interval)
        ticker = await get_ticker(symbol.upper())
        return {
            "symbol": symbol.upper(),
            "interval": interval,
            "ticker": ticker,
            "indicators": indicators,
            "signal": {**signal, "ts": int(time.time())},
            "candles": klines[-50:],  # last 50 candles for chart
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/bot/start")
async def start_bot(cfg: BotConfig, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    global _bot_task
    if trader.state.running:
        return {"status": "already_running"}

    valid = [s.upper() for s in cfg.symbols if s.upper() in SUPPORTED_PAIRS]
    if not valid:
        raise HTTPException(status_code=400, detail="No valid symbols provided")

    trader.state.running = True
    trader.state.selected_symbols = valid
    trader.state.interval = cfg.interval

    # run first cycle immediately, then schedule background loop
    background_tasks.add_task(_start_bot_background)
    return {"status": "started", "symbols": valid, "interval": cfg.interval}


async def _start_bot_background() -> None:
    global _bot_task
    if _bot_task and not _bot_task.done():
        return
    _bot_task = asyncio.create_task(_bot_loop())


@router.post("/bot/stop")
async def stop_bot() -> Dict[str, Any]:
    trader.state.running = False
    return {"status": "stopped"}


@router.get("/bot/status")
async def bot_status() -> Dict[str, Any]:
    # Build live prices dict for portfolio snapshot
    live_prices: Dict[str, float] = {}
    if trader.positions or trader.state.last_signal:
        symbols_to_fetch = list(set(list(trader.positions.keys()) + list(trader.state.last_signal.keys())))
        try:
            tickers = await get_multi_ticker(symbols_to_fetch)
            live_prices = {t["symbol"]: t["price"] for t in tickers}
        except Exception:
            pass

    portfolio = trader.portfolio_snapshot(live_prices)
    return {
        "running": trader.state.running,
        "interval": trader.state.interval,
        "selected_symbols": trader.state.selected_symbols,
        "error": trader.state.error,
        "portfolio": portfolio,
        "last_signals": trader.state.last_signal,
        "log": trader.get_log(20),
    }


@router.get("/portfolio")
async def portfolio() -> Dict[str, Any]:
    symbols_to_fetch = list(trader.positions.keys())
    live_prices: Dict[str, float] = {}
    if symbols_to_fetch:
        try:
            tickers = await get_multi_ticker(symbols_to_fetch)
            live_prices = {t["symbol"]: t["price"] for t in tickers}
        except Exception:
            pass
    return trader.portfolio_snapshot(live_prices)


@router.get("/trades")
async def trade_history() -> Dict[str, Any]:
    return {"trades": trader.get_trades()}


@router.post("/trade/open")
async def manual_open(req: ManualTradeRequest) -> Dict[str, Any]:
    symbol = req.symbol.upper()
    if symbol not in SUPPORTED_PAIRS:
        raise HTTPException(status_code=400, detail=f"Unsupported symbol: {symbol}")
    try:
        ticker = await get_ticker(symbol)
        price = ticker["price"]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    result = trader.open_position(
        symbol=symbol,
        side=req.side,
        price=price,
        stop_loss_pct=req.stop_loss_pct,
        take_profit_pct=req.take_profit_pct,
    )
    if result is None:
        raise HTTPException(status_code=409, detail="Position already open or insufficient balance")
    return {"status": "opened", "position": result}


@router.post("/trade/close/{symbol}")
async def manual_close(symbol: str) -> Dict[str, Any]:
    symbol = symbol.upper()
    try:
        ticker = await get_ticker(symbol)
        price = ticker["price"]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    result = trader.close_position(symbol, price, reason="manual")
    if result is None:
        raise HTTPException(status_code=404, detail="No open position for this symbol")
    return {"status": "closed", "trade": result}


@router.post("/reset")
async def reset_bot() -> Dict[str, Any]:
    trader.reset()
    return {"status": "reset", "balance_eur": 10.0}
