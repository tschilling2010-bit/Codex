"""
Trading Bot Orchestrator — autonomous demo trader.

The bot behaves exactly like a real trader with real money, but uses virtual funds.
It scans markets, generates AI signals, executes trades, and tracks outcomes.
After each closed trade it explains: "Das wäre passiert, wenn du echtes Geld investiert hättest."
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from ..models.trading_schemas import (
    BotConfig, MarketDataResponse, TradeAction, TradingSignal
)
from .ai_trader import analyze_market, get_ai_status, _fallback_signal
from .demo_portfolio import DemoPortfolioService, get_session
from .market_data import (
    fetch_candles, fetch_daily_candles, fetch_news_headlines,
    get_current_price, get_market_info, get_symbol_info
)
from .technical_analysis import (
    calculate_indicators, determine_trend, find_support_resistance, score_signal
)
from .trade_tracker import TradeTracker, get_tracker

log = logging.getLogger("trading.bot")


async def build_market_analysis(symbol: str, interval: str = "1h") -> Optional[MarketDataResponse]:
    """Fetch data and build full market analysis for a symbol."""
    try:
        from ..models.trading_schemas import MarketAnalysis
        sym_info = get_symbol_info(symbol)

        candles_1h = await fetch_candles(symbol, period="5d", interval=interval)
        candles_daily = await fetch_daily_candles(symbol, days=90)

        if not candles_1h and not candles_daily:
            return None

        analysis_candles = candles_1h if len(candles_1h) >= 30 else candles_daily
        indicators = calculate_indicators(analysis_candles)

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
    analysis = market_data.analysis
    technical_score, technical_factors = score_signal(analysis.indicators, analysis.current_price)
    news = await fetch_news_headlines(symbol)
    return await analyze_market(
        symbol=symbol, name=market_data.name, analysis=analysis,
        news_headlines=news, technical_score=technical_score,
        technical_factors=technical_factors,
    )


def _get_technical_signal(symbol: str, market_data: MarketDataResponse) -> tuple[TradingSignal, float, list[str]]:
    """Compute technical-only signal without calling Claude. Returns (signal, score, factors)."""
    analysis = market_data.analysis
    technical_score, technical_factors = score_signal(analysis.indicators, analysis.current_price)
    signal = _fallback_signal(symbol, analysis, technical_score, technical_factors)
    return signal, technical_score, technical_factors


class TradingBotRunner:
    """
    Autonomous trading bot — acts exactly like a real trader with real money,
    but uses virtual funds and tracks every outcome.
    """

    def __init__(self, config: BotConfig, portfolio: DemoPortfolioService):
        self.config = config
        self.portfolio = portfolio
        self.tracker: TradeTracker = get_tracker(config.session_id)
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._broadcast_cb: Optional[Callable] = None
        self.last_signals: dict[str, TradingSignal] = {}
        self.scan_count = 0
        self.last_scan: Optional[datetime] = None
        self._first_scan = True  # Execute immediately on first run

    def set_broadcast(self, cb: Callable) -> None:
        self._broadcast_cb = cb

    async def _broadcast(self, event_type: str, data: dict) -> None:
        if self._broadcast_cb:
            try:
                await self._broadcast_cb(event_type, data)
            except Exception:
                pass

    async def _scan_and_trade(self, symbol: str) -> None:
        """Core logic: algorithm pre-filter → (optional) AI analysis → decide → trade → track."""
        try:
            market_data = await build_market_analysis(symbol)
            if not market_data or market_data.analysis.current_price <= 0:
                return

            # ── Step 1: Algorithmus-Vorfilter ──────────────────────────────
            tech_signal, tech_score, tech_factors = _get_technical_signal(symbol, market_data)

            # Skip sideways markets — save API calls and reduce noise
            if abs(tech_score) < 0.35:
                self.tracker.log_activity(
                    "scan", symbol=symbol,
                    message=f"{symbol}: Seitwärts (Score {tech_score:+.2f}) — übersprungen",
                    emoji="⏭",
                )
                return

            # ── Step 2: KI-Analyse nur bei echtem Signal ───────────────────
            ai_status = get_ai_status()
            if ai_status["key_configured"]:
                analysis = market_data.analysis
                news = await fetch_news_headlines(symbol)
                signal = await analyze_market(
                    symbol=symbol, name=market_data.name, analysis=analysis,
                    news_headlines=news, technical_score=tech_score,
                    technical_factors=tech_factors,
                )
                source_label = "KI"
            else:
                signal = tech_signal
                source_label = "Algo"

            market_data.signal = signal
            self.last_signals[symbol] = signal

            self.tracker.log_activity(
                event_type="signal",
                symbol=symbol,
                message=f"{symbol} [{source_label}]: {signal.strength.replace('_', ' ').upper()} (Konfidenz {signal.confidence:.0%}, Score {tech_score:+.2f})",
                detail=signal.reasoning,
                emoji=self._signal_emoji(signal),
            )

            await self._broadcast("signal", {
                "symbol": symbol,
                "signal": signal.model_dump(mode="json"),
                "analysis": market_data.analysis.model_dump(mode="json"),
                "source": source_label,
            })

            # ── Step 3: Trade ausführen wenn Konfidenz hoch genug ──────────
            if signal.confidence >= self.config.min_confidence and signal.action != TradeAction.HOLD:
                await self._execute_signal(symbol, market_data, signal)

            # Check open outcomes (did previous trades hit target/stop?)
            p = self.portfolio._portfolio
            if p:
                outcome_updates = await self.tracker.check_open_outcomes(p.positions)
                for update in outcome_updates:
                    outcome = update.get("outcome", {})
                    await self._broadcast("outcome", {
                        "update_type": update["type"],
                        "outcome": outcome,
                    })
                    # If target/stop hit, close the position in portfolio
                    if update["type"] in ("target_hit", "stop_hit"):
                        await self._close_triggered_position(symbol, outcome, market_data)

        except Exception as exc:
            log.error("scan_and_trade %s: %s", symbol, exc)

    async def _execute_signal(
        self, symbol: str, market_data: MarketDataResponse, signal: TradingSignal
    ) -> None:
        p = self.portfolio._portfolio
        if not p:
            return

        current_price = market_data.analysis.current_price
        sym_info = get_symbol_info(symbol)
        existing = next((pos for pos in p.positions if pos.symbol == symbol), None)

        if signal.action == TradeAction.BUY:
            # Position sizing: risk-based
            max_invest = p.initial_balance * self.config.max_position_pct
            already_invested = existing.invested_amount if existing else 0.0
            available = min(
                max_invest - already_invested,
                p.cash_balance * 0.85,
                p.initial_balance * self.config.risk_per_trade_pct * 3,
            )
            if available < 0.5:
                self.tracker.log_activity(
                    "skip", f"{symbol}: Übersprungen (zu wenig freies Kapital für neue Position)", symbol=symbol, emoji="⏭"
                )
                return

            success, msg, trade = self.portfolio.execute_trade(
                symbol=symbol, name=market_data.name,
                market_type=sym_info.market_type, action=TradeAction.BUY,
                amount_eur=available, current_price=current_price, signal=signal,
            )
            if success and trade:
                # Register for outcome tracking
                self.tracker.record_trade_open(trade, available)
                self.tracker.log_activity(
                    "trade", f"KAUF {symbol}: €{available:.2f} @ ${current_price:.4f}",
                    symbol=symbol,
                    detail=f"Ziel: ${signal.target_price:.4f} | Stop: ${signal.stop_loss:.4f}\n{signal.reasoning}" if signal.target_price else signal.reasoning,
                    emoji="📈",
                )
                await self._broadcast("trade", {"trade": trade.model_dump(mode="json"), "message": msg})

        elif signal.action == TradeAction.SELL and existing:
            sell_amount = existing.current_value * 0.9
            buy_trade = self.portfolio.get_buy_trade_by_symbol(symbol)

            success, msg, trade = self.portfolio.execute_trade(
                symbol=symbol, name=market_data.name,
                market_type=sym_info.market_type, action=TradeAction.SELL,
                amount_eur=sell_amount, current_price=current_price, signal=signal,
            )
            if success and trade:
                # Record outcome for the corresponding buy
                if buy_trade:
                    self.tracker.record_trade_close(
                        buy_trade.id, current_price,
                        trade.realized_pnl or 0, existing.invested_amount,
                    )
                self.tracker.log_activity(
                    "trade", f"VERK {symbol}: {msg}",
                    symbol=symbol, emoji="📉",
                )
                await self._broadcast("trade", {"trade": trade.model_dump(mode="json"), "message": msg})

    async def _close_triggered_position(self, symbol: str, outcome: dict, market_data: MarketDataResponse) -> None:
        """Close a position when target or stop was hit."""
        p = self.portfolio._portfolio
        if not p:
            return
        existing = next((pos for pos in p.positions if pos.symbol == symbol), None)
        if not existing:
            return

        exit_price = outcome.get("exit_price", market_data.analysis.current_price)
        sym_info = get_symbol_info(symbol)
        self.portfolio.execute_trade(
            symbol=symbol, name=market_data.name,
            market_type=sym_info.market_type, action=TradeAction.SELL,
            amount_eur=existing.current_value, current_price=exit_price,
        )

    def _signal_emoji(self, signal: TradingSignal) -> str:
        return {
            "strong_buy": "🚀", "buy": "📈",
            "neutral": "⏸", "hold": "⏸",
            "sell": "📉", "strong_sell": "⚠️",
        }.get(signal.strength, "📊")

    async def _portfolio_refresh(self) -> None:
        """Fetch current prices and broadcast updated portfolio."""
        prices: dict[str, float] = {}
        for symbol in self.config.markets:
            price = await get_current_price(symbol)
            if price:
                prices[symbol] = price
        p = self.portfolio._portfolio
        if p:
            for pos in p.positions:
                if pos.symbol not in prices:
                    price = await get_current_price(pos.symbol)
                    if price:
                        prices[pos.symbol] = price
        portfolio = self.portfolio.get_portfolio(prices)
        await self._broadcast("portfolio_update", {"portfolio": portfolio.model_dump(mode="json")})

    async def _run_loop(self) -> None:
        log.info("Bot started for session %s", self.config.session_id)

        # First scan immediately, then wait for interval
        delay = 0 if self._first_scan else self.config.trade_interval_minutes * 60
        self._first_scan = False

        while self._running:
            if delay > 0:
                await asyncio.sleep(delay)
            if not self._running:
                break

            self.scan_count += 1
            self.last_scan = datetime.now(timezone.utc)

            self.tracker.log_activity(
                "scan",
                f"Scan #{self.scan_count}: Analysiere {len(self.config.markets)} Märkte...",
                emoji="🔍",
            )
            await self._broadcast("scan_start", {
                "scan_count": self.scan_count,
                "markets": self.config.markets,
            })

            for symbol in self.config.markets:
                if not self._running:
                    break
                await self._scan_and_trade(symbol)
                await asyncio.sleep(1.5)  # small delay between markets

            await self._portfolio_refresh()
            await self._broadcast("scan_complete", {
                "scan_count": self.scan_count,
                "next_scan_in_seconds": self.config.trade_interval_minutes * 60,
                "activity": [a.model_dump(mode="json") for a in self.tracker.get_activity(5)],
                "ai_active": get_ai_status()["active"],
            })
            log.info("Bot scan #%d done, next in %d min", self.scan_count, self.config.trade_interval_minutes)

            delay = self.config.trade_interval_minutes * 60

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

    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()


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
    bot = _bots.pop(session_id, None)
    if bot:
        await bot.stop()
        return True
    return False
