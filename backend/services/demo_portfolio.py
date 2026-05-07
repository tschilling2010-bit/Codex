"""Demo portfolio service — paper trading with real market prices."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config import STORAGE_DIR
from ..models.trading_schemas import (
    DemoPortfolio, DemoPosition, MarketType, TradeAction, TradeRecord, TradingSignal
)

log = logging.getLogger("trading.portfolio")

PORTFOLIO_DIR = STORAGE_DIR / "portfolios"
PORTFOLIO_DIR.mkdir(parents=True, exist_ok=True)

TRADING_FEE_PCT = 0.001  # 0.1% per trade (realistic for most brokers/exchanges)


def _portfolio_path(session_id: str) -> Path:
    return PORTFOLIO_DIR / f"{session_id}.json"


def _trades_path(session_id: str) -> Path:
    return PORTFOLIO_DIR / f"{session_id}_trades.json"


class DemoPortfolioService:
    """Manages a paper-trading portfolio session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._portfolio: Optional[DemoPortfolio] = None
        self._trades: list[TradeRecord] = []
        self._load()

    def _load(self) -> None:
        p = _portfolio_path(self.session_id)
        if p.exists():
            data = json.loads(p.read_text())
            self._portfolio = DemoPortfolio(**data)
        t = _trades_path(self.session_id)
        if t.exists():
            self._trades = [TradeRecord(**r) for r in json.loads(t.read_text())]

    def _save(self) -> None:
        if self._portfolio:
            _portfolio_path(self.session_id).write_text(
                self._portfolio.model_dump_json(indent=2)
            )
        _trades_path(self.session_id).write_text(
            json.dumps([t.model_dump(mode="json") for t in self._trades], indent=2, default=str)
        )

    @classmethod
    def create(cls, initial_balance: float, currency: str = "EUR") -> "DemoPortfolioService":
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        portfolio = DemoPortfolio(
            session_id=session_id,
            initial_balance=initial_balance,
            cash_balance=initial_balance,
            total_invested=0.0,
            total_value=initial_balance,
            total_pnl=0.0,
            total_pnl_pct=0.0,
            positions=[],
            trade_count=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            created_at=now,
            updated_at=now,
        )
        svc = cls.__new__(cls)
        svc.session_id = session_id
        svc._portfolio = portfolio
        svc._trades = []
        svc._save()
        return svc

    @classmethod
    def load(cls, session_id: str) -> Optional["DemoPortfolioService"]:
        if not _portfolio_path(session_id).exists():
            return None
        svc = cls(session_id)
        return svc

    def get_portfolio(self, prices: dict[str, float]) -> DemoPortfolio:
        self._refresh_portfolio(prices)
        return self._portfolio

    def _refresh_portfolio(self, prices: dict[str, float]) -> None:
        p = self._portfolio
        if not p:
            return
        total_invested = 0.0
        total_position_value = 0.0
        updated_positions = []
        for pos in p.positions:
            current_price = prices.get(pos.symbol, pos.current_price)
            current_value = pos.quantity * current_price
            unrealized_pnl = current_value - pos.invested_amount
            unrealized_pnl_pct = (unrealized_pnl / pos.invested_amount * 100) if pos.invested_amount else 0
            updated_positions.append(DemoPosition(
                symbol=pos.symbol,
                name=pos.name,
                market_type=pos.market_type,
                quantity=pos.quantity,
                avg_entry_price=pos.avg_entry_price,
                current_price=current_price,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
                invested_amount=pos.invested_amount,
                current_value=current_value,
                opened_at=pos.opened_at,
            ))
            total_invested += pos.invested_amount
            total_position_value += current_value

        total_value = p.cash_balance + total_position_value
        total_pnl = total_value - p.initial_balance
        total_pnl_pct = (total_pnl / p.initial_balance * 100) if p.initial_balance else 0

        self._portfolio = DemoPortfolio(
            session_id=p.session_id,
            initial_balance=p.initial_balance,
            cash_balance=p.cash_balance,
            total_invested=total_invested,
            total_value=total_value,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            positions=updated_positions,
            trade_count=p.trade_count,
            winning_trades=p.winning_trades,
            losing_trades=p.losing_trades,
            win_rate=p.win_rate,
            created_at=p.created_at,
            updated_at=datetime.now(timezone.utc),
        )

    def execute_trade(
        self,
        symbol: str,
        name: str,
        market_type: MarketType,
        action: TradeAction,
        amount_eur: float,
        current_price: float,
        signal: Optional[TradingSignal] = None,
    ) -> tuple[bool, str, Optional[TradeRecord]]:
        """Execute a demo trade. Returns (success, message, trade_record)."""
        p = self._portfolio
        if not p:
            return False, "Portfolio not found", None

        fee = amount_eur * TRADING_FEE_PCT

        if action == TradeAction.BUY:
            total_cost = amount_eur + fee
            if total_cost > p.cash_balance:
                return False, f"Insufficient funds: need €{total_cost:.2f}, have €{p.cash_balance:.2f}", None

            quantity = amount_eur / current_price
            trade = self._record_trade(symbol, action, quantity, current_price, amount_eur, fee, signal)

            # Update or create position
            existing = next((pos for pos in p.positions if pos.symbol == symbol), None)
            if existing:
                total_qty = existing.quantity + quantity
                total_invested = existing.invested_amount + amount_eur
                avg_price = total_invested / total_qty
                new_positions = [
                    pos if pos.symbol != symbol else DemoPosition(
                        symbol=symbol,
                        name=name,
                        market_type=market_type,
                        quantity=total_qty,
                        avg_entry_price=avg_price,
                        current_price=current_price,
                        unrealized_pnl=total_qty * current_price - total_invested,
                        unrealized_pnl_pct=((total_qty * current_price - total_invested) / total_invested * 100),
                        invested_amount=total_invested,
                        current_value=total_qty * current_price,
                        opened_at=existing.opened_at,
                    )
                    for pos in p.positions
                ]
            else:
                new_pos = DemoPosition(
                    symbol=symbol,
                    name=name,
                    market_type=market_type,
                    quantity=quantity,
                    avg_entry_price=current_price,
                    current_price=current_price,
                    unrealized_pnl=0.0,
                    unrealized_pnl_pct=0.0,
                    invested_amount=amount_eur,
                    current_value=amount_eur,
                    opened_at=datetime.now(timezone.utc),
                )
                new_positions = p.positions + [new_pos]

            self._portfolio = DemoPortfolio(
                **{**p.model_dump(), "cash_balance": p.cash_balance - total_cost, "positions": new_positions,
                   "trade_count": p.trade_count + 1, "updated_at": datetime.now(timezone.utc)}
            )
            self._trades.append(trade)
            self._save()
            return True, f"Bought {quantity:.6f} {symbol} @ ${current_price:.4f}", trade

        elif action == TradeAction.SELL:
            existing = next((pos for pos in p.positions if pos.symbol == symbol), None)
            if not existing:
                return False, f"No position in {symbol} to sell", None

            sell_amount = min(amount_eur, existing.current_value)
            sell_qty = sell_amount / current_price
            sell_qty = min(sell_qty, existing.quantity)

            gross_proceeds = sell_qty * current_price
            net_proceeds = gross_proceeds - fee
            cost_basis = sell_qty * existing.avg_entry_price
            realized_pnl = gross_proceeds - cost_basis - fee

            trade = self._record_trade(
                symbol, action, sell_qty, current_price, gross_proceeds, fee, signal, realized_pnl
            )

            remaining_qty = existing.quantity - sell_qty
            if remaining_qty < 1e-8:
                new_positions = [pos for pos in p.positions if pos.symbol != symbol]
            else:
                remaining_invested = existing.invested_amount * (remaining_qty / existing.quantity)
                new_positions = [
                    pos if pos.symbol != symbol else DemoPosition(
                        symbol=symbol,
                        name=name,
                        market_type=market_type,
                        quantity=remaining_qty,
                        avg_entry_price=existing.avg_entry_price,
                        current_price=current_price,
                        unrealized_pnl=remaining_qty * current_price - remaining_invested,
                        unrealized_pnl_pct=((remaining_qty * current_price - remaining_invested) / remaining_invested * 100),
                        invested_amount=remaining_invested,
                        current_value=remaining_qty * current_price,
                        opened_at=existing.opened_at,
                    )
                    for pos in p.positions
                ]

            winning = 1 if realized_pnl > 0 else 0
            losing = 1 if realized_pnl < 0 else 0
            new_win_count = p.winning_trades + winning
            new_lose_count = p.losing_trades + losing
            total_closed = new_win_count + new_lose_count
            win_rate = (new_win_count / total_closed * 100) if total_closed else 0

            self._portfolio = DemoPortfolio(
                **{**p.model_dump(),
                   "cash_balance": p.cash_balance + net_proceeds,
                   "positions": new_positions,
                   "trade_count": p.trade_count + 1,
                   "winning_trades": new_win_count,
                   "losing_trades": new_lose_count,
                   "win_rate": win_rate,
                   "updated_at": datetime.now(timezone.utc)}
            )
            self._trades.append(trade)
            self._save()
            return True, f"Sold {sell_qty:.6f} {symbol} @ ${current_price:.4f} | P&L: €{realized_pnl:+.4f}", trade

        return False, "Invalid action", None

    def _record_trade(
        self,
        symbol: str,
        action: TradeAction,
        quantity: float,
        price: float,
        total: float,
        fee: float,
        signal: Optional[TradingSignal],
        realized_pnl: Optional[float] = None,
    ) -> TradeRecord:
        return TradeRecord(
            id=str(uuid.uuid4()),
            symbol=symbol,
            action=action,
            quantity=quantity,
            price=price,
            total_value=total,
            fee=fee,
            realized_pnl=realized_pnl,
            signal_confidence=signal.confidence if signal else None,
            reasoning=signal.reasoning if signal else None,
            executed_at=datetime.now(timezone.utc),
        )

    def get_trades(self) -> list[TradeRecord]:
        return list(reversed(self._trades))

    def get_session_id(self) -> str:
        return self.session_id


# In-memory session cache
_sessions: dict[str, DemoPortfolioService] = {}


def get_or_create_session(session_id: Optional[str] = None, initial_balance: float = 10.0) -> DemoPortfolioService:
    if session_id and session_id in _sessions:
        return _sessions[session_id]
    if session_id:
        svc = DemoPortfolioService.load(session_id)
        if svc:
            _sessions[session_id] = svc
            return svc
    svc = DemoPortfolioService.create(initial_balance)
    _sessions[svc.session_id] = svc
    return svc


def get_session(session_id: str) -> Optional[DemoPortfolioService]:
    if session_id in _sessions:
        return _sessions[session_id]
    svc = DemoPortfolioService.load(session_id)
    if svc:
        _sessions[session_id] = svc
    return svc
