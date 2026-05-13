"""
Algorithmic trading strategy engine — pure rule-based, no AI/LLM.

Three pattern detectors that scan technical indicators and produce
high-confidence trading signals with named strategies.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from ..models.trading_schemas import (
    MarketAnalysis, OHLCV, SignalStrength, TradeAction, TradingSignal
)
from .technical_analysis import ema_series, sma

log = logging.getLogger("trading.strategy")


@dataclass
class PatternMatch:
    """Result of a strategy pattern check."""
    matched: bool
    action: TradeAction
    confidence: float  # 0.0 - 1.0
    pattern_name: str
    reasoning: str
    target_pct: float  # expected gain (e.g. 0.02 = 2%)
    stop_pct: float    # max loss (e.g. 0.01 = 1%)


def _ema_crossover(closes: list[float], indicators) -> PatternMatch:
    """EMA9 crosses EMA21 → trend reversal signal."""
    if not indicators.ema_9 or not indicators.ema_21 or len(closes) < 25:
        return PatternMatch(False, TradeAction.HOLD, 0, "", "", 0, 0)

    e9 = ema_series(closes, 9)
    e21 = ema_series(closes, 21)
    if len(e9) < 3 or len(e21) < 3:
        return PatternMatch(False, TradeAction.HOLD, 0, "", "", 0, 0)

    # Align series (e9 is longer because period is smaller)
    offset = len(e9) - len(e21)
    e9_aligned = e9[offset:]

    prev_diff = e9_aligned[-2] - e21[-2]
    curr_diff = e9_aligned[-1] - e21[-1]

    # Bullish crossover: EMA9 was below, now above EMA21
    if prev_diff < 0 and curr_diff > 0:
        strength = min(1.0, abs(curr_diff) / (closes[-1] * 0.005))
        return PatternMatch(
            matched=True, action=TradeAction.BUY,
            confidence=0.62 + strength * 0.20,
            pattern_name="EMA-Goldcross",
            reasoning=f"EMA9 (${e9_aligned[-1]:.2f}) hat EMA21 (${e21[-1]:.2f}) von unten gekreuzt — Aufwärtstrend startet",
            target_pct=0.025, stop_pct=0.012,
        )

    # Bearish crossover: EMA9 was above, now below EMA21
    if prev_diff > 0 and curr_diff < 0:
        strength = min(1.0, abs(curr_diff) / (closes[-1] * 0.005))
        return PatternMatch(
            matched=True, action=TradeAction.SELL,
            confidence=0.62 + strength * 0.20,
            pattern_name="EMA-Deathcross",
            reasoning=f"EMA9 (${e9_aligned[-1]:.2f}) hat EMA21 (${e21[-1]:.2f}) von oben gekreuzt — Abwärtstrend startet",
            target_pct=0.025, stop_pct=0.012,
        )

    return PatternMatch(False, TradeAction.HOLD, 0, "", "", 0, 0)


def _rsi_reversal(closes: list[float], indicators) -> PatternMatch:
    """RSI extreme + Bollinger Band touch = mean reversion opportunity."""
    if not indicators.rsi or not indicators.bb_lower or not indicators.bb_upper:
        return PatternMatch(False, TradeAction.HOLD, 0, "", "", 0, 0)

    rsi = indicators.rsi
    price = closes[-1]

    # Oversold + at lower band → BUY
    if rsi < 32 and price <= indicators.bb_lower * 1.005:
        confidence = 0.65 + (32 - rsi) / 100  # lower RSI = higher confidence
        return PatternMatch(
            matched=True, action=TradeAction.BUY,
            confidence=min(0.88, confidence),
            pattern_name="RSI-Umkehr (überverkauft)",
            reasoning=f"RSI bei {rsi:.1f} (überverkauft) und Kurs am unteren Bollinger-Band — Erholung erwartet",
            target_pct=0.022, stop_pct=0.010,
        )

    # Overbought + at upper band → SELL
    if rsi > 68 and price >= indicators.bb_upper * 0.995:
        confidence = 0.65 + (rsi - 68) / 100
        return PatternMatch(
            matched=True, action=TradeAction.SELL,
            confidence=min(0.88, confidence),
            pattern_name="RSI-Umkehr (überkauft)",
            reasoning=f"RSI bei {rsi:.1f} (überkauft) und Kurs am oberen Bollinger-Band — Korrektur erwartet",
            target_pct=0.022, stop_pct=0.010,
        )

    return PatternMatch(False, TradeAction.HOLD, 0, "", "", 0, 0)


def _macd_momentum(closes: list[float], candles: list[OHLCV], indicators) -> PatternMatch:
    """MACD histogram direction change + volume confirmation = momentum breakout."""
    if not indicators.macd or not indicators.macd_signal or len(candles) < 30:
        return PatternMatch(False, TradeAction.HOLD, 0, "", "", 0, 0)

    macd_hist = indicators.macd_histogram or (indicators.macd - indicators.macd_signal)

    # Volume confirmation — current vs 20-bar average
    volumes = [c.volume for c in candles[-21:-1]]
    avg_vol = sum(volumes) / len(volumes) if volumes else 0
    curr_vol = candles[-1].volume
    vol_spike = curr_vol > avg_vol * 1.4 if avg_vol > 0 else False

    if not vol_spike:
        return PatternMatch(False, TradeAction.HOLD, 0, "", "", 0, 0)

    # Need at least small MACD signal
    if abs(macd_hist) < closes[-1] * 0.0001:
        return PatternMatch(False, TradeAction.HOLD, 0, "", "", 0, 0)

    # Bullish: MACD above signal + positive histogram + volume
    if indicators.macd > indicators.macd_signal and macd_hist > 0:
        return PatternMatch(
            matched=True, action=TradeAction.BUY,
            confidence=0.68,
            pattern_name="MACD-Breakout (bullish)",
            reasoning=f"MACD ({indicators.macd:.4f}) über Signal ({indicators.macd_signal:.4f}) mit {curr_vol/avg_vol:.1f}x Volumen — Momentum startet",
            target_pct=0.028, stop_pct=0.013,
        )

    # Bearish
    if indicators.macd < indicators.macd_signal and macd_hist < 0:
        return PatternMatch(
            matched=True, action=TradeAction.SELL,
            confidence=0.68,
            pattern_name="MACD-Breakout (bearish)",
            reasoning=f"MACD ({indicators.macd:.4f}) unter Signal ({indicators.macd_signal:.4f}) mit {curr_vol/avg_vol:.1f}x Volumen — Abverkauf startet",
            target_pct=0.028, stop_pct=0.013,
        )

    return PatternMatch(False, TradeAction.HOLD, 0, "", "", 0, 0)


def evaluate_strategies(
    symbol: str,
    candles: list[OHLCV],
    analysis: MarketAnalysis,
) -> TradingSignal:
    """
    Run all strategies, return the strongest match (or HOLD if none match).
    """
    closes = [c.close for c in candles]
    indicators = analysis.indicators

    patterns = [
        _ema_crossover(closes, indicators),
        _rsi_reversal(closes, indicators),
        _macd_momentum(closes, candles, indicators),
    ]
    matches = [p for p in patterns if p.matched]

    if not matches:
        return TradingSignal(
            symbol=symbol,
            action=TradeAction.HOLD,
            strength=SignalStrength.NEUTRAL,
            confidence=0.0,
            entry_price=analysis.current_price,
            target_price=None,
            stop_loss=None,
            reasoning="Kein klares Muster erkannt — Markt wird beobachtet.",
            key_factors=[],
            risk_reward_ratio=None,
            timeframe="1h",
            timestamp=datetime.now(timezone.utc),
        )

    # Take the strongest match
    best = max(matches, key=lambda p: p.confidence)
    price = analysis.current_price

    if best.action == TradeAction.BUY:
        target = price * (1 + best.target_pct)
        stop = price * (1 - best.stop_pct)
    else:
        target = price * (1 - best.target_pct)
        stop = price * (1 + best.stop_pct)

    strength = SignalStrength.STRONG_BUY if (best.action == TradeAction.BUY and best.confidence > 0.78) else \
               SignalStrength.BUY if best.action == TradeAction.BUY else \
               SignalStrength.STRONG_SELL if (best.action == TradeAction.SELL and best.confidence > 0.78) else \
               SignalStrength.SELL

    return TradingSignal(
        symbol=symbol,
        action=best.action,
        strength=strength,
        confidence=round(best.confidence, 3),
        entry_price=price,
        target_price=round(target, 6),
        stop_loss=round(stop, 6),
        reasoning=best.reasoning,
        key_factors=[best.pattern_name, f"RSI {indicators.rsi:.1f}" if indicators.rsi else "",
                     f"Trend {analysis.trend}"],
        risk_reward_ratio=round(best.target_pct / best.stop_pct, 2),
        timeframe="1h",
        timestamp=datetime.now(timezone.utc),
        strategy=best.pattern_name,
    )
