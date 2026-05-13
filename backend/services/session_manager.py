"""
Persistent session manager — saves the active bot session to disk so it
survives server restarts. On startup the bot resumes automatically.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from ..config import STORAGE_DIR

log = logging.getLogger("trading.session_manager")

_SESSION_FILE = STORAGE_DIR / "active_session.json"


def save_active_session(
    session_id: str,
    initial_balance: float,
    markets: list[str],
    min_confidence: float = 0.55,
    trade_interval_minutes: int = 8,
    max_position_pct: float = 0.60,
    risk_per_trade_pct: float = 0.15,
    api_key: str = "",
) -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "session_id": session_id,
        "initial_balance": initial_balance,
        "markets": markets,
        "min_confidence": min_confidence,
        "trade_interval_minutes": trade_interval_minutes,
        "max_position_pct": max_position_pct,
        "risk_per_trade_pct": risk_per_trade_pct,
        "api_key": api_key,
    }
    _SESSION_FILE.write_text(json.dumps(data, indent=2))
    log.info("Active session saved: %s", session_id)


def load_active_session() -> Optional[dict]:
    if not _SESSION_FILE.exists():
        return None
    try:
        return json.loads(_SESSION_FILE.read_text())
    except Exception as exc:
        log.warning("Could not load active session: %s", exc)
        return None


def clear_active_session() -> None:
    if _SESSION_FILE.exists():
        _SESSION_FILE.unlink()
        log.info("Active session cleared")
