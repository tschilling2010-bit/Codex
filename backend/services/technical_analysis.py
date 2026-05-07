"""Technical analysis service — calculates RSI, MACD, Bollinger Bands, EMA, ATR, etc."""
from __future__ import annotations

import math
from typing import Optional

from ..models.trading_schemas import OHLCV, TechnicalIndicators


def _closes(candles: list[OHLCV]) -> list[float]:
    return [c.close for c in candles]


def _highs(candles: list[OHLCV]) -> list[float]:
    return [c.high for c in candles]


def _lows(candles: list[OHLCV]) -> list[float]:
    return [c.low for c in candles]


def _volumes(candles: list[OHLCV]) -> list[float]:
    return [c.volume for c in candles]


def sma(values: list[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / period


def ema(values: list[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    k = 2.0 / (period + 1)
    ema_val = sum(values[:period]) / period
    for v in values[period:]:
        ema_val = v * k + ema_val * (1 - k)
    return ema_val


def ema_series(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    k = 2.0 / (period + 1)
    result = [sum(values[:period]) / period]
    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def rsi(values: list[float], period: int = 14) -> Optional[float]:
    if len(values) < period + 1:
        return None
    deltas = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram) or (None, None, None)."""
    if len(values) < slow + signal:
        return None, None, None
    ema_fast = ema_series(values, fast)
    ema_slow_s = ema_series(values, slow)
    min_len = min(len(ema_fast), len(ema_slow_s))
    if min_len < signal:
        return None, None, None
    macd_line = [ema_fast[-(min_len - i)] - ema_slow_s[-(min_len - i)] for i in range(min_len)]
    signal_series = ema_series(macd_line, signal)
    if not signal_series:
        return None, None, None
    macd_val = macd_line[-1]
    sig_val = signal_series[-1]
    hist = macd_val - sig_val
    return macd_val, sig_val, hist


def bollinger_bands(values: list[float], period: int = 20, std_dev: float = 2.0):
    """Returns (upper, middle, lower) or (None, None, None)."""
    if len(values) < period:
        return None, None, None
    window = values[-period:]
    middle = sum(window) / period
    variance = sum((v - middle) ** 2 for v in window) / period
    std = math.sqrt(variance)
    return middle + std_dev * std, middle, middle - std_dev * std


def atr(candles: list[OHLCV], period: int = 14) -> Optional[float]:
    """Average True Range."""
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        high = candles[i].high
        low = candles[i].low
        prev_close = candles[i - 1].close
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def stochastic(candles: list[OHLCV], k_period: int = 14, d_period: int = 3):
    """Returns (%K, %D) or (None, None)."""
    if len(candles) < k_period + d_period:
        return None, None
    k_values = []
    for i in range(k_period - 1, len(candles)):
        window = candles[i - k_period + 1:i + 1]
        lowest = min(c.low for c in window)
        highest = max(c.high for c in window)
        if highest == lowest:
            k_values.append(50.0)
        else:
            k_values.append((candles[i].close - lowest) / (highest - lowest) * 100)
    if len(k_values) < d_period:
        return None, None
    k = k_values[-1]
    d = sum(k_values[-d_period:]) / d_period
    return k, d


def vwap(candles: list[OHLCV]) -> Optional[float]:
    """Volume Weighted Average Price (intraday)."""
    total_vol = sum(c.volume for c in candles)
    if total_vol == 0:
        return None
    typical_x_vol = sum(((c.high + c.low + c.close) / 3) * c.volume for c in candles)
    return typical_x_vol / total_vol


def find_support_resistance(candles: list[OHLCV]) -> tuple[Optional[float], Optional[float]]:
    """Simple pivot-based support and resistance."""
    if len(candles) < 10:
        return None, None
    recent = candles[-20:]
    highs = [c.high for c in recent]
    lows = [c.low for c in recent]
    resistance = max(highs)
    support = min(lows)
    return support, resistance


def determine_trend(candles: list[OHLCV]) -> str:
    """Determine trend direction using EMA crossover."""
    closes = _closes(candles)
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    ema50 = ema(closes, 50)
    current = closes[-1] if closes else 0

    if ema9 and ema21 and ema50:
        if ema9 > ema21 > ema50 and current > ema9:
            return "strong_uptrend"
        elif ema9 > ema21 and current > ema9:
            return "uptrend"
        elif ema9 < ema21 < ema50 and current < ema9:
            return "strong_downtrend"
        elif ema9 < ema21:
            return "downtrend"
    return "sideways"


def calculate_indicators(candles: list[OHLCV]) -> TechnicalIndicators:
    """Calculate all technical indicators from a list of OHLCV candles."""
    if not candles:
        return TechnicalIndicators()

    closes = _closes(candles)
    macd_val, macd_sig, macd_hist = macd(closes)
    bb_upper, bb_mid, bb_lower = bollinger_bands(closes)
    stoch_k, stoch_d = stochastic(candles)

    vol_sma = sma(_volumes(candles), 20)

    return TechnicalIndicators(
        rsi=rsi(closes, 14),
        macd=macd_val,
        macd_signal=macd_sig,
        macd_histogram=macd_hist,
        bb_upper=bb_upper,
        bb_middle=bb_mid,
        bb_lower=bb_lower,
        ema_9=ema(closes, 9),
        ema_21=ema(closes, 21),
        ema_50=ema(closes, 50),
        sma_200=sma(closes, 200),
        atr=atr(candles, 14),
        stoch_k=stoch_k,
        stoch_d=stoch_d,
        volume_sma=vol_sma,
        vwap=vwap(candles),
    )


def score_signal(indicators: TechnicalIndicators, current_price: float) -> tuple[float, list[str]]:
    """
    Score a trading signal from -1.0 (strong sell) to +1.0 (strong buy).
    Returns (score, list_of_factors).
    """
    score = 0.0
    factors: list[str] = []
    weight_sum = 0.0

    # RSI analysis
    if indicators.rsi is not None:
        rsi_val = indicators.rsi
        if rsi_val < 30:
            score += 1.0 * 0.20
            factors.append(f"RSI oversold ({rsi_val:.1f}) → bullish reversal signal")
        elif rsi_val < 45:
            score += 0.4 * 0.20
            factors.append(f"RSI approaching oversold zone ({rsi_val:.1f})")
        elif rsi_val > 70:
            score -= 1.0 * 0.20
            factors.append(f"RSI overbought ({rsi_val:.1f}) → bearish reversal signal")
        elif rsi_val > 55:
            score -= 0.3 * 0.20
            factors.append(f"RSI in overbought territory ({rsi_val:.1f})")
        else:
            factors.append(f"RSI neutral ({rsi_val:.1f})")
        weight_sum += 0.20

    # MACD analysis
    if indicators.macd is not None and indicators.macd_signal is not None:
        macd_diff = indicators.macd - indicators.macd_signal
        if macd_diff > 0 and indicators.macd_histogram and indicators.macd_histogram > 0:
            score += 0.8 * 0.20
            factors.append("MACD bullish crossover with positive histogram")
        elif macd_diff > 0:
            score += 0.4 * 0.20
            factors.append("MACD above signal line (bullish)")
        elif macd_diff < 0 and indicators.macd_histogram and indicators.macd_histogram < 0:
            score -= 0.8 * 0.20
            factors.append("MACD bearish crossover with negative histogram")
        else:
            score -= 0.3 * 0.20
            factors.append("MACD below signal line (bearish)")
        weight_sum += 0.20

    # Bollinger Bands
    if all(v is not None for v in [indicators.bb_upper, indicators.bb_lower, indicators.bb_middle]):
        bb_range = indicators.bb_upper - indicators.bb_lower
        if bb_range > 0:
            position = (current_price - indicators.bb_lower) / bb_range
            if position < 0.15:
                score += 0.9 * 0.15
                factors.append("Price near lower Bollinger Band → oversold")
            elif position > 0.85:
                score -= 0.9 * 0.15
                factors.append("Price near upper Bollinger Band → overbought")
            elif 0.4 < position < 0.6:
                factors.append("Price at Bollinger midband → neutral")
        weight_sum += 0.15

    # EMA trend
    if indicators.ema_9 and indicators.ema_21:
        if indicators.ema_9 > indicators.ema_21:
            score += 0.6 * 0.15
            factors.append("EMA 9 > EMA 21 → short-term uptrend")
        else:
            score -= 0.6 * 0.15
            factors.append("EMA 9 < EMA 21 → short-term downtrend")
        weight_sum += 0.15

    # EMA 50 long term
    if indicators.ema_50:
        if current_price > indicators.ema_50:
            score += 0.4 * 0.15
            factors.append("Price above EMA 50 → medium-term bullish")
        else:
            score -= 0.4 * 0.15
            factors.append("Price below EMA 50 → medium-term bearish")
        weight_sum += 0.15

    # Stochastic
    if indicators.stoch_k is not None and indicators.stoch_d is not None:
        if indicators.stoch_k < 20 and indicators.stoch_d < 20:
            score += 0.7 * 0.15
            factors.append(f"Stochastic oversold (K={indicators.stoch_k:.1f})")
        elif indicators.stoch_k > 80 and indicators.stoch_d > 80:
            score -= 0.7 * 0.15
            factors.append(f"Stochastic overbought (K={indicators.stoch_k:.1f})")
        weight_sum += 0.15

    # Normalize
    if weight_sum > 0:
        score = score / weight_sum
    score = max(-1.0, min(1.0, score))

    return score, factors
