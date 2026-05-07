"""Technical indicators computed with numpy only."""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np


def _closes(klines: List[Dict]) -> np.ndarray:
    return np.array([k["close"] for k in klines], dtype=float)


def _highs(klines: List[Dict]) -> np.ndarray:
    return np.array([k["high"] for k in klines], dtype=float)


def _lows(klines: List[Dict]) -> np.ndarray:
    return np.array([k["low"] for k in klines], dtype=float)


def _volumes(klines: List[Dict]) -> np.ndarray:
    return np.array([k["volume"] for k in klines], dtype=float)


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    result = np.full_like(values, np.nan)
    k = 2.0 / (period + 1)
    # seed with SMA
    result[period - 1] = np.mean(values[:period])
    for i in range(period, len(values)):
        result[i] = values[i] * k + result[i - 1] * (1 - k)
    return result


def rsi(klines: List[Dict], period: int = 14) -> float:
    closes = _closes(klines)
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def macd(
    klines: List[Dict],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Dict[str, float]:
    closes = _closes(klines)
    if len(closes) < slow + signal:
        return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = ema_fast - ema_slow
    valid = macd_line[~np.isnan(macd_line)]
    if len(valid) < signal:
        return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}
    signal_line = _ema(valid, signal)
    m = round(float(valid[-1]), 4)
    s = round(float(signal_line[-1]), 4)
    return {"macd": m, "signal": s, "histogram": round(m - s, 4)}


def bollinger_bands(
    klines: List[Dict], period: int = 20, std_dev: float = 2.0
) -> Dict[str, float]:
    closes = _closes(klines)
    if len(closes) < period:
        price = float(closes[-1])
        return {"upper": price, "middle": price, "lower": price, "width": 0.0}
    window = closes[-period:]
    mid = float(np.mean(window))
    std = float(np.std(window, ddof=1))
    upper = round(mid + std_dev * std, 4)
    lower = round(mid - std_dev * std, 4)
    width = round((upper - lower) / mid * 100, 2) if mid > 0 else 0.0
    return {"upper": upper, "middle": round(mid, 4), "lower": lower, "width": width}


def volume_trend(klines: List[Dict], period: int = 20) -> str:
    vols = _volumes(klines)
    if len(vols) < period + 1:
        return "neutral"
    avg = float(np.mean(vols[-period - 1:-1]))
    last = float(vols[-1])
    if last > avg * 1.5:
        return "very_high"
    if last > avg * 1.1:
        return "high"
    if last < avg * 0.6:
        return "very_low"
    if last < avg * 0.9:
        return "low"
    return "normal"


def support_resistance(klines: List[Dict], lookback: int = 50) -> Dict[str, float]:
    highs = _highs(klines[-lookback:])
    lows = _lows(klines[-lookback:])
    return {
        "resistance": round(float(np.max(highs)), 4),
        "support": round(float(np.min(lows)), 4),
    }


def compute_all(klines: List[Dict]) -> Dict[str, Any]:
    closes = _closes(klines)
    price = float(closes[-1])
    rsi_val = rsi(klines)
    macd_val = macd(klines)
    bb = bollinger_bands(klines)
    vol_trend = volume_trend(klines)
    sr = support_resistance(klines)

    # simple trend: last close vs 20-bar EMA
    ema20 = _ema(closes, 20)
    trend = "bullish" if price > float(ema20[-1]) else "bearish"

    # BB position 0-100
    bb_range = bb["upper"] - bb["lower"]
    bb_pos = round((price - bb["lower"]) / bb_range * 100, 1) if bb_range > 0 else 50.0

    return {
        "price": round(price, 6),
        "trend": trend,
        "rsi": rsi_val,
        "macd": macd_val,
        "bollinger_bands": bb,
        "bb_position": bb_pos,
        "volume_trend": vol_trend,
        "support": sr["support"],
        "resistance": sr["resistance"],
        "ema20": round(float(ema20[-1]), 6) if not np.isnan(ema20[-1]) else price,
    }
