"""
Trade Outcome Tracker — monitors open trades and records what actually happened.

After the bot buys an asset, this service checks periodically:
- Did the price reach the predicted target? → WIN
- Did the price drop to the stop-loss? → LOSS
- Did time expire? → Close at market price

This is the "was wäre passiert" (what would have happened) engine.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from ..config import STORAGE_DIR
from ..models.trading_schemas import (
    BotActivity, OutcomeStatus, TradeOutcome, TradeRecord, TradeAction
)
from .market_data import get_current_price

log = logging.getLogger("trading.tracker")

OUTCOMES_DIR = STORAGE_DIR / "outcomes"
OUTCOMES_DIR.mkdir(parents=True, exist_ok=True)

# How long to hold a position before closing at market (in minutes)
DEFAULT_HOLD_MINUTES = 60 * 4  # 4 hours max hold for daytrading


def _outcomes_path(session_id: str) -> Path:
    return OUTCOMES_DIR / f"{session_id}_outcomes.json"


def _activity_path(session_id: str) -> Path:
    return OUTCOMES_DIR / f"{session_id}_activity.json"


class TradeTracker:
    """
    Monitors all open trades for a session.
    When a position is closed (manually or by bot), records the outcome
    and generates the "what would have happened" explanation.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._outcomes: dict[str, TradeOutcome] = {}
        self._activity: list[BotActivity] = []
        self._load()

    def _load(self) -> None:
        p = _outcomes_path(self.session_id)
        if p.exists():
            raw = json.loads(p.read_text())
            self._outcomes = {k: TradeOutcome(**v) for k, v in raw.items()}
        a = _activity_path(self.session_id)
        if a.exists():
            self._activity = [BotActivity(**x) for x in json.loads(a.read_text())]

    def _save(self) -> None:
        _outcomes_path(self.session_id).write_text(
            json.dumps({k: v.model_dump(mode="json") for k, v in self._outcomes.items()}, indent=2, default=str)
        )
        _activity_path(self.session_id).write_text(
            json.dumps([a.model_dump(mode="json") for a in self._activity[-200:]], indent=2, default=str)
        )

    def record_trade_open(self, trade: TradeRecord, invested_eur: float) -> TradeOutcome:
        """Register a new trade for outcome tracking."""
        outcome = TradeOutcome(
            trade_id=trade.id,
            symbol=trade.symbol,
            action=trade.action,
            entry_price=trade.price,
            predicted_target=trade.predicted_target,
            predicted_stop=trade.predicted_stop,
            invested_eur=invested_eur,
            quantity=trade.quantity,
            status=OutcomeStatus.OPEN,
            opened_at=trade.executed_at,
            bot_reasoning=trade.reasoning or "",
            bot_confidence=trade.signal_confidence or 0.0,
            key_factors=trade.key_factors or [],
        )
        if trade.action == TradeAction.BUY:
            self._outcomes[trade.id] = outcome
        self._save()
        return outcome

    def record_trade_close(
        self,
        trade_id: str,
        exit_price: float,
        realized_pnl: float,
        invested_eur: float,
        closed_at: Optional[datetime] = None,
    ) -> Optional[TradeOutcome]:
        """Update an outcome when a trade is closed."""
        outcome = self._outcomes.get(trade_id)
        if not outcome:
            return None

        closed_at = closed_at or datetime.now(timezone.utc)
        duration = (closed_at - outcome.opened_at).total_seconds() / 60

        exit_eur = invested_eur + realized_pnl
        pnl_pct = (realized_pnl / invested_eur * 100) if invested_eur else 0

        # Determine status
        if outcome.predicted_target and exit_price >= outcome.predicted_target:
            status = OutcomeStatus.TARGET_HIT
        elif outcome.predicted_stop and exit_price <= outcome.predicted_stop:
            status = OutcomeStatus.STOP_HIT
        elif realized_pnl > 0:
            status = OutcomeStatus.CLOSED_PROFIT
        elif realized_pnl < 0:
            status = OutcomeStatus.CLOSED_LOSS
        else:
            status = OutcomeStatus.EXPIRED

        prediction_correct = realized_pnl > 0 if outcome.action == TradeAction.BUY else realized_pnl < 0

        outcome.exit_price = exit_price
        outcome.exit_eur = exit_eur
        outcome.pnl_eur = realized_pnl
        outcome.pnl_pct = pnl_pct
        outcome.status = status
        outcome.closed_at = closed_at
        outcome.duration_minutes = duration
        outcome.prediction_correct = prediction_correct
        outcome.outcome_explanation = self._generate_explanation(outcome)

        self._outcomes[trade_id] = outcome
        self._save()

        self.log_activity(
            event_type="outcome",
            symbol=outcome.symbol,
            message=self._short_outcome(outcome),
            detail=outcome.outcome_explanation,
            emoji="✅" if realized_pnl > 0 else "❌",
        )

        return outcome

    def _generate_explanation(self, o: TradeOutcome) -> str:
        """Generate a human-readable 'was wäre passiert' explanation in German."""
        direction = "gekauft" if o.action == TradeAction.BUY else "verkauft"
        duration_str = self._fmt_duration(o.duration_minutes or 0)

        if o.pnl_eur is None:
            return ""

        pnl_abs = abs(o.pnl_eur)
        pnl_sign = "+" if o.pnl_eur >= 0 else "-"
        result_word = "gewonnen" if o.pnl_eur >= 0 else "verloren"

        explanation = (
            f"Der Bot hat {o.symbol} für €{o.invested_eur:.2f} {direction}. "
            f"Einstiegspreis: ${o.entry_price:.4f}. "
        )

        if o.status == OutcomeStatus.TARGET_HIT:
            explanation += (
                f"Nach {duration_str} hat der Kurs das Kursziel ${o.predicted_target:.4f} erreicht. "
                f"Die Prognose war korrekt — du hättest €{pnl_abs:.4f} {result_word} "
                f"({o.pnl_pct:+.2f}%)."
            )
        elif o.status == OutcomeStatus.STOP_HIT:
            explanation += (
                f"Nach {duration_str} hat der Kurs den Stop-Loss ${o.predicted_stop:.4f} getriggert. "
                f"Der Bot hat die Position geschützt — du hättest €{pnl_abs:.4f} {result_word} "
                f"({o.pnl_pct:+.2f}%)."
            )
        else:
            explanation += (
                f"Nach {duration_str} wurde die Position bei ${o.exit_price:.4f} geschlossen. "
                f"Du hättest €{pnl_abs:.4f} {result_word} ({o.pnl_pct:+.2f}%)."
            )

        if o.prediction_correct:
            explanation += " ✅ Bot-Prognose war korrekt."
        else:
            explanation += " ⚠️ Bot-Prognose war falsch — Markt lief gegen die Erwartung."

        return explanation

    def _short_outcome(self, o: TradeOutcome) -> str:
        if o.pnl_eur is None:
            return f"{o.symbol} geschlossen"
        sign = "+" if o.pnl_eur >= 0 else ""
        return f"{o.symbol}: {sign}€{o.pnl_eur:.4f} ({o.pnl_pct:+.2f}%)"

    def _fmt_duration(self, minutes: float) -> str:
        if minutes < 60:
            return f"{int(minutes)} Min."
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hours}h {mins}min"

    def log_activity(
        self, event_type: str, message: str,
        symbol: Optional[str] = None, detail: Optional[str] = None, emoji: str = "📊"
    ) -> BotActivity:
        activity = BotActivity(
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            symbol=symbol,
            message=message,
            detail=detail,
            emoji=emoji,
        )
        self._activity.append(activity)
        self._save()
        return activity

    async def check_open_outcomes(self, portfolio_positions: list) -> list[dict]:
        """
        Check all open outcomes against current prices.
        Returns list of outcome updates to broadcast.
        """
        updates = []
        for outcome in list(self._outcomes.values()):
            if outcome.status != OutcomeStatus.OPEN:
                continue

            current_price = await get_current_price(outcome.symbol)
            if not current_price:
                continue

            # Check if target or stop was hit
            triggered = False
            if outcome.action == TradeAction.BUY:
                if outcome.predicted_target and current_price >= outcome.predicted_target:
                    # Target hit!
                    realized_pnl = (outcome.predicted_target - outcome.entry_price) * outcome.quantity
                    self.record_trade_close(outcome.trade_id, outcome.predicted_target, realized_pnl, outcome.invested_eur)
                    triggered = True
                    updates.append({"type": "target_hit", "outcome": self._outcomes[outcome.trade_id].model_dump(mode="json")})
                elif outcome.predicted_stop and current_price <= outcome.predicted_stop:
                    # Stop hit!
                    realized_pnl = (outcome.predicted_stop - outcome.entry_price) * outcome.quantity
                    self.record_trade_close(outcome.trade_id, outcome.predicted_stop, realized_pnl, outcome.invested_eur)
                    triggered = True
                    updates.append({"type": "stop_hit", "outcome": self._outcomes[outcome.trade_id].model_dump(mode="json")})

            # Check expiry
            if not triggered and outcome.opened_at:
                age_minutes = (datetime.now(timezone.utc) - outcome.opened_at).total_seconds() / 60
                if age_minutes >= DEFAULT_HOLD_MINUTES:
                    realized_pnl = (current_price - outcome.entry_price) * outcome.quantity
                    self.record_trade_close(outcome.trade_id, current_price, realized_pnl, outcome.invested_eur)
                    updates.append({"type": "expired", "outcome": self._outcomes[outcome.trade_id].model_dump(mode="json")})

        return updates

    def get_outcomes(self, limit: int = 50) -> list[TradeOutcome]:
        outcomes = list(self._outcomes.values())
        outcomes.sort(key=lambda o: o.opened_at, reverse=True)
        return outcomes[:limit]

    def get_activity(self, limit: int = 50) -> list[BotActivity]:
        return list(reversed(self._activity[-limit:]))

    def get_performance_summary(self) -> dict:
        closed = [o for o in self._outcomes.values() if o.status != OutcomeStatus.OPEN]
        wins = [o for o in closed if o.pnl_eur and o.pnl_eur > 0]
        losses = [o for o in closed if o.pnl_eur and o.pnl_eur < 0]
        correct = [o for o in closed if o.prediction_correct is True]

        total_win = sum(o.pnl_eur for o in wins if o.pnl_eur)
        total_loss = abs(sum(o.pnl_eur for o in losses if o.pnl_eur))

        profit_factor = round(total_win / total_loss, 4) if total_loss > 0 else (99.0 if total_win > 0 else 0.0)
        return {
            "total_closed": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(closed) * 100, 2) if closed else 0.0,
            "prediction_accuracy": round(len(correct) / len(closed) * 100, 2) if closed else 0.0,
            "total_profit": round(total_win, 6),
            "total_loss": round(total_loss, 6),
            "profit_factor": profit_factor,
            "avg_win": round(total_win / len(wins), 6) if wins else 0.0,
            "avg_loss": round(total_loss / len(losses), 6) if losses else 0.0,
            "best_trade": round(max((o.pnl_eur for o in closed if o.pnl_eur), default=0), 6),
            "worst_trade": round(min((o.pnl_eur for o in closed if o.pnl_eur), default=0), 6),
        }


# Global tracker registry
_trackers: dict[str, TradeTracker] = {}


def get_tracker(session_id: str) -> TradeTracker:
    if session_id not in _trackers:
        _trackers[session_id] = TradeTracker(session_id)
    return _trackers[session_id]
