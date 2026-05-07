"""Trading bot orchestrator — coordinates market data, analysis, AI signals, and execution."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from ..models.trading_schemas import (
    BotConfig, MarketAnalysis, MarketDataResponse, MarketType,
    TradeAction, TradingSignal
)
from .ai_trader import analyze_market
from .demo_portfolio import DemoPortfolioService, get_session
from .market_data import (
    fetch_candles, fetch_daily_candles, fetch_news_headlines,
    get_current_price, get_market_info, get_symbol_info
)
from .technical_analysis import (
    calculate_indicators, determine_trend, find_support_resistance, score_signal
)

log = logging.getLogger("trading.bot")


async def build_market_analysis(symbol: str, interval: str = "1h") -> Optional[MarketDataResponse]:
    """Fetch data and build full market analysis for a symbol."""
    try:
        sym_info = get_symbol_info(symbol)

        # Use daily candles for better indicator calculation on longer timeframes
        candles_1h = await fetch_candles(symbol, period="5d", interval=interval)
        candles_daily = await fetch_daily_candles(symbol, days=90)

        if not candles_1h and not candles_daily:
            log.warning("No candles available for %s", symbol)
            return None

        # Use hourly for recent analysis, supplement with daily for SMA200
        analysis_candles = candles_1h if len(candles_1h) >= 30 else candles_daily
        indicators = calculate_indicators(analysis_candles)

        # Fill SMA200 from daily if we have enough daily data
        if candles_daily and len(candles_daily) >= 200:
            from .technical_analysis import sma, _closes
            indicators.sma_200 = sma(_closes(candles_daily), 200)

        market_info = await get_market_info(symbol)
        trend = determine_trend(analysis_candles)
        support, resistance = find_support_resistance(analysis_candles)

        analysis = MarketAnalysis(
            symbol=symbol,
            current_price=market_info["current_price"],
            price_change_24h=market_info["price_change_24h"],
            price_change_pct_24h=market_info["price_change_pct_24h"],
            volume_24h=market_info["volume_24h"],
            market_cap=market_info.get("market_cap"),
            indicators=indicators,
            trend=trend,
            support_level=support,
            resistance_level=resistance,
            timestamp=datetime.now(timezone.utc),
        )

        return MarketDataResponse(
            symbol=symbol,
            name=sym_info.name,
            market_type=sym_info.market_type,
            candles=candles_1h[-100:] if candles_1h else candles_daily[-100:],
            analysis=analysis,
            signal=None,
        )
    except Exception as exc:
        log.error("build_market_analysis %s: %s", symbol, exc)
        return None


async def get_ai_signal(symbol: str, market_data: MarketDataResponse) -> TradingSignal:
    """Generate AI trading signal for a market."""
    analysis = market_data.analysis
    technical_score, technical_factors = score_signal(analysis.indicators, analysis.current_price)
    news = await fetch_news_headlines(symbol)

    signal = await analyze_market(
        symbol=symbol,
        name=market_data.name,
        analysis=analysis,
        news_headlines=news,
        technical_score=technical_score,
        technical_factors=technical_factors,
    )
    return signal


class TradingBotRunner:
    """Autonomous trading bot that scans markets and executes trades."""

    def __init__(self, config: BotConfig, portfolio: DemoPortfolioService):
        self.config = config
        self.portfolio = portfolio
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._broadcast_cb: Optional[Callable] = None
        self.last_signals: dict[str, TradingSignal] = {}
        self.scan_count = 0
        self.last_scan: Optional[datetime] = None

    def set_broadcast(self, cb: Callable) -> None:
        self._broadcast_cb = cb

    async def _broadcast(self, event_type: str, data: dict) -> None:
        if self._broadcast_cb:
            try:
                await self._broadcast_cb(event_type, data)
            except Exception:
                pass

    async def _scan_market(self, symbol: str) -> Optional[TradingSignal]:
        """Analyze one market and optionally execute a trade."""
        try:
            market_data = await build_market_analysis(symbol)
            if not market_data:
                return None

            signal = await get_ai_signal(symbol, market_data)
            market_data.signal = signal
            self.last_signals[symbol] = signal

            await self._broadcast("signal", {
                "symbol": symbol,
                "signal": signal.model_dump(mode="json"),
                "analysis": market_data.analysis.model_dump(mode="json"),
            })

            # Auto-execute if confidence meets threshold
            if signal.confidence >= self.config.min_confidence:
                await self._maybe_execute(symbol, market_data, signal)

            return signal
        except Exception as exc:
            log.error("scan_market %s: %s", symbol, exc)
            return None

    async def _maybe_execute(
        self, symbol: str, market_data: MarketDataResponse, signal: TradingSignal
    ) -> None:
        """Execute a trade based on signal, respecting position limits."""
        p = self.portfolio._portfolio
        if not p:
            return

        current_price = market_data.analysis.current_price
        if current_price <= 0:
            return

        sym_info = get_symbol_info(symbol)
        max_position_value = p.initial_balance * self.config.max_position_pct
        risk_amount = p.initial_balance * self.config.risk_per_trade_pct

        existing = next((pos for pos in p.positions if pos.symbol == symbol), None)

        if signal.action == TradeAction.BUY:
            # Don't buy if already at max position size
            current_position_value = existing.current_value if existing else 0.0
            available_to_invest = min(
                max_position_value - current_position_value,
                p.cash_balance * 0.9,
                risk_amount * 3,
            )
            if available_to_invest < 0.5:
                return

            success, msg, trade = self.portfolio.execute_trade(
                symbol=symbol,
                name=market_data.name,
                market_type=sym_info.market_type,
                action=TradeAction.BUY,
                amount_eur=available_to_invest,
                current_price=current_price,
                signal=signal,
            )
            if success and trade:
                log.info("BOT BUY %s: %s", symbol, msg)
                await self._broadcast("trade", {"trade": trade.model_dump(mode="json"), "message": msg})

        elif signal.action == TradeAction.SELL and existing:
            # Sell if signal says sell and we have a position
            sell_amount = existing.current_value * 0.8  # Sell 80% of position
            success, msg, trade = self.portfolio.execute_trade(
                symbol=symbol,
                name=market_data.name,
                market_type=sym_info.market_type,
                action=TradeAction.SELL,
                amount_eur=sell_amount,
                current_price=current_price,
                signal=signal,
            )
            if success and trade:
                log.info("BOT SELL %s: %s", symbol, msg)
                await self._broadcast("trade", {"trade": trade.model_dump(mode="json"), "message": msg})

        # Check stop-loss
        if existing and signal.stop_loss:
            if current_price <= signal.stop_loss:
                success, msg, trade = self.portfolio.execute_trade(
                    symbol=symbol,
                    name=market_data.name,
                    market_type=sym_info.market_type,
                    action=TradeAction.SELL,
                    amount_eur=existing.current_value,
                    current_price=current_price,
                    signal=signal,
                )
                if success:
                    log.info("BOT STOP-LOSS %s: %s", symbol, msg)
                    await self._broadcast("stop_loss", {"symbol": symbol, "message": msg})

    async def _run_loop(self) -> None:
        log.info("Bot started for session %s", self.config.session_id)
        interval_seconds = self.config.trade_interval_minutes * 60

        while self._running:
            self.scan_count += 1
            self.last_scan = datetime.now(timezone.utc)
            await self._broadcast("scan_start", {
                "scan_count": self.scan_count,
                "markets": self.config.markets,
            })

            for symbol in self.config.markets:
                if not self._running:
                    break
                await self._scan_market(symbol)
                await asyncio.sleep(2)  # Rate limiting between market scans

            # Broadcast portfolio update after each scan
            prices = {}
            for symbol in self.config.markets:
                price = await get_current_price(symbol)
                if price:
                    prices[symbol] = price

            portfolio = self.portfolio.get_portfolio(prices)
            await self._broadcast("portfolio_update", {
                "portfolio": portfolio.model_dump(mode="json")
            })

            await self._broadcast("scan_complete", {
                "scan_count": self.scan_count,
                "next_scan_in": interval_seconds,
            })

            log.info("Bot scan %d complete. Sleeping %ds", self.scan_count, interval_seconds)
            await asyncio.sleep(interval_seconds)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        log.info("Bot stopped for session %s", self.config.session_id)

    def is_running(self) -> bool:
        return self._running


# Global bot registry
_bots: dict[str, TradingBotRunner] = {}


def get_bot(session_id: str) -> Optional[TradingBotRunner]:
    return _bots.get(session_id)


def create_bot(config: BotConfig, broadcast_cb: Optional[Callable] = None) -> TradingBotRunner:
    portfolio = get_session(config.session_id)
    if not portfolio:
        raise ValueError(f"Session {config.session_id} not found")
    bot = TradingBotRunner(config, portfolio)
    if broadcast_cb:
        bot.set_broadcast(broadcast_cb)
    _bots[config.session_id] = bot
    return bot


async def stop_bot(session_id: str) -> bool:
    bot = _bots.get(session_id)
    if bot:
        await bot.stop()
        del _bots[session_id]
        return True
    return False
