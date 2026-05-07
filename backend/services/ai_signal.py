"""Generates BUY/SELL/HOLD signals using Claude AI."""
from __future__ import annotations

import os
from typing import Any, Dict

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

_SYSTEM = """You are an expert day-trading analyst.
You receive real-time market data and technical indicators for a crypto pair.
Your job: produce a precise trading signal with clear reasoning.

Rules:
- Be concise and direct
- Always include a confidence score 0-100
- Always include a risk level: low / medium / high
- Suggest stop-loss and take-profit levels in percentage terms
- Output valid JSON only, no extra text
"""

_USER_TEMPLATE = """
Analyze this market data and return a JSON signal:

Symbol: {symbol}
Current Price: {price}
Trend: {trend}
RSI (14): {rsi}
MACD: line={macd_line}, signal={macd_signal}, histogram={macd_hist}
Bollinger Bands: upper={bb_upper}, middle={bb_mid}, lower={bb_lower}, width={bb_width}%
BB Position: {bb_pos}% (0=at lower band, 100=at upper band)
Volume Trend: {vol_trend}
Support: {support}
Resistance: {resistance}
EMA20: {ema20}
Interval: {interval}

Return ONLY this JSON (fill in all fields):
{{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": <0-100>,
  "risk_level": "low" | "medium" | "high",
  "stop_loss_pct": <e.g. 1.5>,
  "take_profit_pct": <e.g. 3.0>,
  "reasoning": "<2-3 sentences explaining key signals>",
  "key_factors": ["factor1", "factor2", "factor3"]
}}
"""


async def get_signal(
    symbol: str,
    indicators: Dict[str, Any],
    interval: str = "1h",
) -> Dict[str, Any]:
    if not ANTHROPIC_API_KEY:
        return _fallback_signal(symbol, indicators)

    try:
        import anthropic
        bb = indicators["bollinger_bands"]
        macd_d = indicators["macd"]
        prompt = _USER_TEMPLATE.format(
            symbol=symbol,
            price=indicators["price"],
            trend=indicators["trend"],
            rsi=indicators["rsi"],
            macd_line=macd_d["macd"],
            macd_signal=macd_d["signal"],
            macd_hist=macd_d["histogram"],
            bb_upper=bb["upper"],
            bb_mid=bb["middle"],
            bb_lower=bb["lower"],
            bb_width=bb["width"],
            bb_pos=indicators["bb_position"],
            vol_trend=indicators["volume_trend"],
            support=indicators["support"],
            resistance=indicators["resistance"],
            ema20=indicators["ema20"],
            interval=interval,
        )
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        text = msg.content[0].text.strip()
        # strip markdown fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as exc:
        return {**_fallback_signal(symbol, indicators), "error": str(exc)}


def _fallback_signal(symbol: str, indicators: Dict[str, Any]) -> Dict[str, Any]:
    """Rule-based fallback when Claude API is unavailable."""
    rsi_val = indicators.get("rsi", 50)
    macd_hist = indicators.get("macd", {}).get("histogram", 0)
    bb_pos = indicators.get("bb_position", 50)
    trend = indicators.get("trend", "neutral")

    score = 0
    factors = []

    if rsi_val < 30:
        score += 2
        factors.append(f"RSI oversold ({rsi_val})")
    elif rsi_val > 70:
        score -= 2
        factors.append(f"RSI overbought ({rsi_val})")
    else:
        factors.append(f"RSI neutral ({rsi_val})")

    if macd_hist > 0:
        score += 1
        factors.append("MACD histogram positive")
    else:
        score -= 1
        factors.append("MACD histogram negative")

    if bb_pos < 25:
        score += 1
        factors.append("Price near lower Bollinger Band")
    elif bb_pos > 75:
        score -= 1
        factors.append("Price near upper Bollinger Band")

    if trend == "bullish":
        score += 1
        factors.append("Price above EMA20 (bullish trend)")
    else:
        score -= 1
        factors.append("Price below EMA20 (bearish trend)")

    if score >= 2:
        action, confidence = "BUY", min(40 + score * 10, 75)
        sl, tp = 1.5, 3.0
    elif score <= -2:
        action, confidence = "SELL", min(40 + abs(score) * 10, 75)
        sl, tp = 1.5, 3.0
    else:
        action, confidence = "HOLD", 50
        sl, tp = 1.0, 2.0

    risk = "low" if confidence < 50 else ("medium" if confidence < 70 else "high")
    reasoning = (
        f"Rule-based signal (no AI key). Score {score:+d}. "
        f"RSI={rsi_val}, MACD hist={macd_hist:.4f}, BB pos={bb_pos}%."
    )
    return {
        "action": action,
        "confidence": confidence,
        "risk_level": risk,
        "stop_loss_pct": sl,
        "take_profit_pct": tp,
        "reasoning": reasoning,
        "key_factors": factors,
        "fallback": True,
    }
