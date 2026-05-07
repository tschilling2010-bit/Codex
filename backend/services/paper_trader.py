"""In-memory paper trading engine with 10 EUR starting balance."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

STARTING_BALANCE_EUR = 10.0
TRADING_FEE_PCT = 0.001  # 0.1% per trade (Binance standard)


@dataclass
class Position:
    symbol: str
    side: str           # "long" | "short"
    entry_price: float
    quantity: float     # in base asset (e.g. BTC)
    entry_time: int
    stop_loss_price: float
    take_profit_price: float
    entry_cost_eur: float


@dataclass
class Trade:
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    entry_time: int
    exit_time: int
    pnl_eur: float
    pnl_pct: float
    exit_reason: str    # "tp" | "sl" | "manual" | "signal"


@dataclass
class BotState:
    running: bool = False
    interval: str = "1h"
    selected_symbols: List[str] = field(default_factory=lambda: ["BTCUSDT"])
    last_analysis: Dict[str, Any] = field(default_factory=dict)
    last_signal: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class PaperTrader:
    def __init__(self) -> None:
        self.balance_eur: float = STARTING_BALANCE_EUR
        self.positions: Dict[str, Position] = {}   # symbol -> position
        self.trade_history: List[Trade] = []
        self.state = BotState()
        self._log: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    #  Core trading ops                                                    #
    # ------------------------------------------------------------------ #

    def open_position(
        self,
        symbol: str,
        side: str,
        price: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        size_pct: float = 0.95,  # use 95% of balance per trade
    ) -> Optional[Dict[str, Any]]:
        if symbol in self.positions:
            return None  # already in trade

        cost_eur = self.balance_eur * size_pct
        fee = cost_eur * TRADING_FEE_PCT
        actual_cost = cost_eur - fee
        if actual_cost <= 0:
            return None

        quantity = actual_cost / price

        if side == "long":
            sl_price = price * (1 - stop_loss_pct / 100)
            tp_price = price * (1 + take_profit_pct / 100)
        else:
            sl_price = price * (1 + stop_loss_pct / 100)
            tp_price = price * (1 - take_profit_pct / 100)

        pos = Position(
            symbol=symbol,
            side=side,
            entry_price=price,
            quantity=quantity,
            entry_time=int(time.time()),
            stop_loss_price=round(sl_price, 6),
            take_profit_price=round(tp_price, 6),
            entry_cost_eur=actual_cost,
        )
        self.positions[symbol] = pos
        self.balance_eur -= cost_eur
        self._log_event("open", symbol, side, price, cost_eur)
        return self._position_dict(pos)

    def close_position(
        self,
        symbol: str,
        current_price: float,
        reason: str = "manual",
    ) -> Optional[Dict[str, Any]]:
        pos = self.positions.pop(symbol, None)
        if pos is None:
            return None

        fee = pos.quantity * current_price * TRADING_FEE_PCT
        proceeds = pos.quantity * current_price - fee

        if pos.side == "long":
            pnl_eur = proceeds - pos.entry_cost_eur
        else:
            pnl_eur = pos.entry_cost_eur - proceeds

        pnl_pct = (pnl_eur / pos.entry_cost_eur) * 100
        self.balance_eur += pos.entry_cost_eur + pnl_eur

        trade = Trade(
            symbol=symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=current_price,
            quantity=pos.quantity,
            entry_time=pos.entry_time,
            exit_time=int(time.time()),
            pnl_eur=round(pnl_eur, 4),
            pnl_pct=round(pnl_pct, 2),
            exit_reason=reason,
        )
        self.trade_history.append(trade)
        self._log_event("close", symbol, pos.side, current_price, pnl_eur, reason)
        return self._trade_dict(trade)

    def check_exits(self, symbol: str, current_price: float) -> Optional[Dict[str, Any]]:
        pos = self.positions.get(symbol)
        if pos is None:
            return None

        if pos.side == "long":
            if current_price <= pos.stop_loss_price:
                return self.close_position(symbol, current_price, "sl")
            if current_price >= pos.take_profit_price:
                return self.close_position(symbol, current_price, "tp")
        else:
            if current_price >= pos.stop_loss_price:
                return self.close_position(symbol, current_price, "sl")
            if current_price <= pos.take_profit_price:
                return self.close_position(symbol, current_price, "tp")

        return None

    # ------------------------------------------------------------------ #
    #  Portfolio stats                                                     #
    # ------------------------------------------------------------------ #

    def portfolio_snapshot(self, live_prices: Dict[str, float]) -> Dict[str, Any]:
        unrealized = 0.0
        positions_out = []
        for sym, pos in self.positions.items():
            price = live_prices.get(sym, pos.entry_price)
            if pos.side == "long":
                unr = (price - pos.entry_price) * pos.quantity
            else:
                unr = (pos.entry_price - price) * pos.quantity
            unrealized += unr
            pnl_pct = (unr / pos.entry_cost_eur) * 100 if pos.entry_cost_eur > 0 else 0
            positions_out.append({
                "symbol": sym,
                "side": pos.side,
                "entry_price": pos.entry_price,
                "current_price": round(price, 6),
                "quantity": round(pos.quantity, 8),
                "entry_cost_eur": round(pos.entry_cost_eur, 4),
                "unrealized_pnl_eur": round(unr, 4),
                "unrealized_pnl_pct": round(pnl_pct, 2),
                "stop_loss": pos.stop_loss_price,
                "take_profit": pos.take_profit_price,
                "entry_time": pos.entry_time,
            })

        total_value = self.balance_eur + sum(
            p["entry_cost_eur"] + p["unrealized_pnl_eur"] for p in positions_out
        )
        realized = sum(t.pnl_eur for t in self.trade_history)
        wins = [t for t in self.trade_history if t.pnl_eur > 0]
        win_rate = round(len(wins) / len(self.trade_history) * 100, 1) if self.trade_history else 0.0

        return {
            "balance_eur": round(self.balance_eur, 4),
            "total_value_eur": round(total_value, 4),
            "realized_pnl_eur": round(realized, 4),
            "unrealized_pnl_eur": round(unrealized, 4),
            "total_pnl_eur": round(realized + unrealized, 4),
            "total_pnl_pct": round((total_value - STARTING_BALANCE_EUR) / STARTING_BALANCE_EUR * 100, 2),
            "total_trades": len(self.trade_history),
            "win_rate": win_rate,
            "positions": positions_out,
        }

    def reset(self) -> None:
        self.balance_eur = STARTING_BALANCE_EUR
        self.positions.clear()
        self.trade_history.clear()
        self._log.clear()
        self.state = BotState()

    def get_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._log[-limit:]

    def get_trades(self) -> List[Dict[str, Any]]:
        return [self._trade_dict(t) for t in reversed(self.trade_history)]

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _position_dict(self, p: Position) -> Dict[str, Any]:
        return {
            "symbol": p.symbol, "side": p.side, "entry_price": p.entry_price,
            "quantity": round(p.quantity, 8), "entry_cost_eur": round(p.entry_cost_eur, 4),
            "stop_loss": p.stop_loss_price, "take_profit": p.take_profit_price,
            "entry_time": p.entry_time,
        }

    def _trade_dict(self, t: Trade) -> Dict[str, Any]:
        return {
            "symbol": t.symbol, "side": t.side, "entry_price": t.entry_price,
            "exit_price": t.exit_price, "quantity": round(t.quantity, 8),
            "pnl_eur": t.pnl_eur, "pnl_pct": t.pnl_pct,
            "exit_reason": t.exit_reason,
            "entry_time": t.entry_time, "exit_time": t.exit_time,
        }

    def _log_event(self, event: str, symbol: str, side: str, price: float, amount: float, note: str = "") -> None:
        self._log.append({
            "ts": int(time.time()),
            "event": event,
            "symbol": symbol,
            "side": side,
            "price": round(price, 6),
            "amount_eur": round(amount, 4),
            "note": note,
        })


# Singleton instance shared across requests
trader = PaperTrader()
