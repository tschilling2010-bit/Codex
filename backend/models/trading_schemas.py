"""Pydantic schemas for the AI Trading Bot system."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MarketType(str, Enum):
    CRYPTO = "crypto"
    STOCK = "stock"
    FOREX = "forex"
    ETF = "etf"


class TradeAction(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class SignalStrength(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class OutcomeStatus(str, Enum):
    OPEN = "open"           # Trade still open, tracking ongoing
    TARGET_HIT = "target_hit"   # Price reached predicted target → WIN
    STOP_HIT = "stop_hit"      # Price hit stop-loss → LOSS
    CLOSED_PROFIT = "closed_profit"
    CLOSED_LOSS = "closed_loss"
    EXPIRED = "expired"     # Timeframe passed, closed at market


class MarketSymbol(BaseModel):
    symbol: str
    name: str
    market_type: MarketType
    exchange: Optional[str] = None
    currency: str = "USD"


class OHLCV(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class TechnicalIndicators(BaseModel):
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    ema_9: Optional[float] = None
    ema_21: Optional[float] = None
    ema_50: Optional[float] = None
    sma_200: Optional[float] = None
    atr: Optional[float] = None
    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None
    volume_sma: Optional[float] = None
    vwap: Optional[float] = None


class MarketAnalysis(BaseModel):
    symbol: str
    current_price: float
    price_change_24h: float
    price_change_pct_24h: float
    volume_24h: float
    market_cap: Optional[float] = None
    indicators: TechnicalIndicators
    trend: str
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None
    timestamp: datetime


class TradingSignal(BaseModel):
    symbol: str
    action: TradeAction
    strength: SignalStrength
    confidence: float = Field(ge=0.0, le=1.0)
    entry_price: float
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    reasoning: str
    key_factors: list[str] = []
    risk_reward_ratio: Optional[float] = None
    timeframe: str = "1d"
    timestamp: datetime


class TradeOutcome(BaseModel):
    """Tracks what actually happened after a trade was executed."""
    trade_id: str
    symbol: str
    action: TradeAction
    entry_price: float
    predicted_target: Optional[float]
    predicted_stop: Optional[float]
    invested_eur: float
    quantity: float

    # Outcome (filled as price moves)
    exit_price: Optional[float] = None
    exit_eur: Optional[float] = None
    pnl_eur: Optional[float] = None
    pnl_pct: Optional[float] = None
    status: OutcomeStatus = OutcomeStatus.OPEN

    # Timing
    opened_at: datetime
    closed_at: Optional[datetime] = None
    duration_minutes: Optional[float] = None

    # Bot reasoning stored for display
    bot_reasoning: str = ""
    bot_confidence: float = 0.0
    key_factors: list[str] = []

    # What-if explanation (generated after close)
    outcome_explanation: str = ""
    prediction_correct: Optional[bool] = None  # Did bot call direction right?


class DemoPosition(BaseModel):
    symbol: str
    name: str
    market_type: MarketType
    quantity: float
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    invested_amount: float
    current_value: float
    opened_at: datetime
    # Store the signal that triggered this buy
    signal_target: Optional[float] = None
    signal_stop: Optional[float] = None
    signal_reasoning: Optional[str] = None


class TradeRecord(BaseModel):
    id: str
    symbol: str
    action: TradeAction
    quantity: float
    price: float
    total_value: float
    fee: float
    realized_pnl: Optional[float] = None
    signal_confidence: Optional[float] = None
    signal_strength: Optional[str] = None
    reasoning: Optional[str] = None
    key_factors: list[str] = []
    predicted_target: Optional[float] = None
    predicted_stop: Optional[float] = None
    executed_at: datetime


class DemoPortfolio(BaseModel):
    session_id: str
    initial_balance: float
    cash_balance: float
    total_invested: float
    total_value: float
    total_pnl: float
    total_pnl_pct: float
    positions: list[DemoPosition] = []
    trade_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    created_at: datetime
    updated_at: datetime


class PerformanceStats(BaseModel):
    """Aggregated performance analytics for a demo session."""
    session_id: str
    initial_balance: float
    current_value: float
    total_pnl: float
    total_pnl_pct: float

    # Trade stats
    total_trades: int
    winning_trades: int
    losing_trades: int
    open_trades: int
    win_rate: float

    # Signal accuracy
    predictions_correct: int = 0
    predictions_wrong: int = 0
    prediction_accuracy: float = 0.0

    # Best/worst
    best_trade_pnl: Optional[float] = None
    best_trade_symbol: Optional[str] = None
    worst_trade_pnl: Optional[float] = None
    worst_trade_symbol: Optional[str] = None

    # Avg metrics
    avg_win_eur: float = 0.0
    avg_loss_eur: float = 0.0
    avg_trade_duration_minutes: float = 0.0
    profit_factor: float = 0.0  # Total wins / Total losses

    # P&L over time (list of {timestamp, value} for chart)
    equity_curve: list[dict] = []

    computed_at: datetime


class BotActivity(BaseModel):
    """A single bot activity event for the live log."""
    timestamp: datetime
    event_type: str  # scan, signal, trade, outcome, stop_loss
    symbol: Optional[str] = None
    message: str
    detail: Optional[str] = None
    emoji: str = "📊"


class StartDemoRequest(BaseModel):
    initial_balance: float = Field(default=10.0, ge=1.0, le=100000.0)
    currency: str = "EUR"
    auto_start_bot: bool = True
    markets: list[str] = ["BTC-USD", "ETH-USD", "SOL-USD", "AAPL", "TSLA", "NVDA"]


class ManualTradeRequest(BaseModel):
    session_id: str
    symbol: str
    action: TradeAction
    amount_eur: float = Field(ge=0.5)


class BotConfig(BaseModel):
    session_id: str
    markets: list[str] = ["BTC-USD", "ETH-USD", "AAPL", "TSLA"]
    max_position_pct: float = Field(default=0.25, ge=0.05, le=0.5)
    min_confidence: float = Field(default=0.60, ge=0.5, le=0.95)
    trade_interval_minutes: int = Field(default=15, ge=5, le=60)
    risk_per_trade_pct: float = Field(default=0.02, ge=0.01, le=0.1)


class MarketDataResponse(BaseModel):
    symbol: str
    name: str
    market_type: MarketType
    candles: list[OHLCV]
    analysis: MarketAnalysis
    signal: Optional[TradingSignal] = None
