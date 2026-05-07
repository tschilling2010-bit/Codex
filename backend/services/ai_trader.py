"""AI Trader service — uses Claude to generate expert daytrading signals."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import anthropic

from ..models.trading_schemas import (
    MarketAnalysis, SignalStrength, TradeAction, TradingSignal
)
from .technical_analysis import score_signal

log = logging.getLogger("trading.ai_trader")

_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


SYSTEM_PROMPT = """You are an elite algorithmic day trader with 20 years of experience at top hedge funds (Citadel, Renaissance Technologies, Two Sigma). You specialize in:

- Momentum and mean-reversion strategies
- Multi-timeframe technical analysis
- Risk-adjusted position sizing
- Reading market microstructure

Your analysis combines:
1. Technical indicators (RSI, MACD, Bollinger Bands, EMA crossovers, ATR, Stochastic)
2. Price action and candlestick patterns
3. Volume analysis and market breadth
4. Current market sentiment and news flow
5. Support/resistance levels
6. Risk/reward optimization

You always respond with structured JSON containing your trading decision. You are direct, data-driven, and never emotional. You protect capital first, seek returns second. You understand that in demo/paper trading mode, accuracy of analysis is paramount to build trust."""


def _build_analysis_prompt(
    symbol: str,
    name: str,
    analysis: MarketAnalysis,
    news_headlines: list[str],
    technical_score: float,
    technical_factors: list[str],
) -> str:
    ind = analysis.indicators
    news_text = "\n".join(f"- {h}" for h in news_headlines) if news_headlines else "No recent news available"

    return f"""Analyze {name} ({symbol}) and provide a day-trading signal.

=== MARKET DATA ===
Current Price: ${analysis.current_price:.4f}
24h Change: {analysis.price_change_pct_24h:+.2f}% (${analysis.price_change_24h:+.4f})
24h Volume: {analysis.volume_24h:,.0f}
Trend: {analysis.trend}
Support: {f'${analysis.support_level:.4f}' if analysis.support_level else 'N/A'}
Resistance: {f'${analysis.resistance_level:.4f}' if analysis.resistance_level else 'N/A'}

=== TECHNICAL INDICATORS ===
RSI (14): {f'{ind.rsi:.2f}' if ind.rsi else 'N/A'}
MACD: {f'{ind.macd:.4f}' if ind.macd else 'N/A'} | Signal: {f'{ind.macd_signal:.4f}' if ind.macd_signal else 'N/A'} | Histogram: {f'{ind.macd_histogram:.4f}' if ind.macd_histogram else 'N/A'}
Bollinger Bands: Upper={f'${ind.bb_upper:.4f}' if ind.bb_upper else 'N/A'} | Mid={f'${ind.bb_middle:.4f}' if ind.bb_middle else 'N/A'} | Lower={f'${ind.bb_lower:.4f}' if ind.bb_lower else 'N/A'}
EMA 9: {f'${ind.ema_9:.4f}' if ind.ema_9 else 'N/A'}
EMA 21: {f'${ind.ema_21:.4f}' if ind.ema_21 else 'N/A'}
EMA 50: {f'${ind.ema_50:.4f}' if ind.ema_50 else 'N/A'}
SMA 200: {f'${ind.sma_200:.4f}' if ind.sma_200 else 'N/A'}
ATR (14): {f'{ind.atr:.4f}' if ind.atr else 'N/A'}
Stochastic %K/%D: {f'{ind.stoch_k:.1f}/{ind.stoch_d:.1f}' if ind.stoch_k else 'N/A'}
VWAP: {f'${ind.vwap:.4f}' if ind.vwap else 'N/A'}

=== ALGO PRE-SCORE ===
Technical Score: {technical_score:+.3f} (range: -1.0 bearish → +1.0 bullish)
Key Technical Factors:
{chr(10).join(f'- {f}' for f in technical_factors)}

=== RECENT NEWS ===
{news_text}

=== YOUR TASK ===
Based on all data above, provide your expert day-trading analysis as JSON:

{{
  "action": "buy" | "sell" | "hold",
  "strength": "strong_buy" | "buy" | "neutral" | "sell" | "strong_sell",
  "confidence": 0.0-1.0,
  "entry_price": <current or slightly adjusted price>,
  "target_price": <realistic intraday target>,
  "stop_loss": <risk management stop>,
  "risk_reward_ratio": <target_gain / max_loss>,
  "reasoning": "<2-3 sentence expert summary>",
  "key_factors": ["<factor 1>", "<factor 2>", "<factor 3>", ...],
  "timeframe": "1h" | "4h" | "1d",
  "market_context": "<brief market context>",
  "risk_level": "low" | "medium" | "high"
}}

Be precise. Use real numbers. Consider intraday daytrading context."""


async def analyze_market(
    symbol: str,
    name: str,
    analysis: MarketAnalysis,
    news_headlines: list[str],
    technical_score: float,
    technical_factors: list[str],
) -> TradingSignal:
    """Generate AI-powered trading signal using Claude."""
    prompt = _build_analysis_prompt(symbol, name, analysis, news_headlines, technical_score, technical_factors)

    try:
        client = _get_client()
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()

        # Extract JSON from response
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        data = json.loads(raw)

        action = TradeAction(data.get("action", "hold"))
        strength = SignalStrength(data.get("strength", "neutral"))
        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        entry_price = float(data.get("entry_price", analysis.current_price))
        target = data.get("target_price")
        stop = data.get("stop_loss")
        rr = data.get("risk_reward_ratio")

        return TradingSignal(
            symbol=symbol,
            action=action,
            strength=strength,
            confidence=confidence,
            entry_price=entry_price,
            target_price=float(target) if target else None,
            stop_loss=float(stop) if stop else None,
            reasoning=data.get("reasoning", "AI analysis complete."),
            key_factors=data.get("key_factors", technical_factors[:3]),
            risk_reward_ratio=float(rr) if rr else None,
            timeframe=data.get("timeframe", "1h"),
            timestamp=datetime.now(timezone.utc),
        )

    except json.JSONDecodeError as exc:
        log.warning("AI response JSON parse error for %s: %s", symbol, exc)
        return _fallback_signal(symbol, analysis, technical_score, technical_factors)
    except Exception as exc:
        log.error("AI analysis failed for %s: %s", symbol, exc)
        return _fallback_signal(symbol, analysis, technical_score, technical_factors)


def _fallback_signal(
    symbol: str,
    analysis: MarketAnalysis,
    technical_score: float,
    technical_factors: list[str],
) -> TradingSignal:
    """Generate a signal purely from technical score when AI is unavailable."""
    if technical_score > 0.4:
        action = TradeAction.BUY
        strength = SignalStrength.STRONG_BUY if technical_score > 0.7 else SignalStrength.BUY
    elif technical_score < -0.4:
        action = TradeAction.SELL
        strength = SignalStrength.STRONG_SELL if technical_score < -0.7 else SignalStrength.SELL
    else:
        action = TradeAction.HOLD
        strength = SignalStrength.NEUTRAL

    confidence = min(0.9, abs(technical_score) * 0.8 + 0.3)
    price = analysis.current_price
    atr_val = analysis.indicators.atr or price * 0.01

    return TradingSignal(
        symbol=symbol,
        action=action,
        strength=strength,
        confidence=confidence,
        entry_price=price,
        target_price=price * (1 + 0.02) if action == TradeAction.BUY else price * (1 - 0.02),
        stop_loss=price - atr_val if action == TradeAction.BUY else price + atr_val,
        reasoning=f"Technical analysis score: {technical_score:+.3f}. AI unavailable — using algorithmic signals.",
        key_factors=technical_factors[:5],
        risk_reward_ratio=2.0,
        timeframe="1h",
        timestamp=datetime.now(timezone.utc),
    )
