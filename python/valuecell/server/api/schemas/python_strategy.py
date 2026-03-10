"""Python Strategy API schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .base import SuccessResponse


# --- Request models ---


class PythonStrategyCreateRequest(BaseModel):
    """Request to create a new Python strategy."""

    name: str = Field(..., description="Strategy display name")
    description: Optional[str] = Field(None, description="Strategy description")
    code: str = Field(..., description="Python strategy source code")


class PythonStrategyUpdateRequest(BaseModel):
    """Request to update an existing Python strategy."""

    name: Optional[str] = Field(None, description="Strategy display name")
    description: Optional[str] = Field(None, description="Strategy description")
    code: Optional[str] = Field(None, description="Python strategy source code")


class BacktestRequest(BaseModel):
    """Request to run a backtest on a Python strategy."""

    strategy_id: str = Field(..., description="Python strategy ID")
    symbol: str = Field(default="AAPL", description="Ticker symbol to backtest")
    start_date: str = Field(
        default="2024-01-01", description="Backtest start date (YYYY-MM-DD)"
    )
    end_date: str = Field(
        default="2025-01-01", description="Backtest end date (YYYY-MM-DD)"
    )
    initial_capital: float = Field(
        default=100000.0, description="Initial capital for backtest", gt=0
    )
    commission_rate: float = Field(
        default=0.001,
        description="Commission rate per trade (e.g. 0.001 = 0.1%)",
        ge=0,
    )


# --- Response models ---


class PythonStrategyItem(BaseModel):
    """Python strategy data for API responses."""

    id: str = Field(..., description="Strategy UUID")
    name: str = Field(..., description="Strategy display name")
    description: Optional[str] = Field(None, description="Strategy description")
    code: str = Field(..., description="Python strategy source code")
    status: str = Field(..., description="Strategy status")
    backtest_config: Optional[Dict[str, Any]] = Field(
        None, description="Backtest configuration"
    )
    backtest_result: Optional[Dict[str, Any]] = Field(
        None, description="Backtest result"
    )
    backtest_error: Optional[str] = Field(None, description="Backtest error message")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Update timestamp")


class BacktestTradeRecord(BaseModel):
    """A single trade in the backtest result."""

    date: str
    action: str  # "BUY" or "SELL"
    symbol: str
    price: float
    shares: float
    value: float
    commission: float


class BacktestMetrics(BaseModel):
    """Backtest performance metrics."""

    total_return_pct: float = Field(..., description="Total return percentage")
    annual_return_pct: Optional[float] = Field(
        None, description="Annualized return percentage"
    )
    max_drawdown_pct: float = Field(..., description="Maximum drawdown percentage")
    sharpe_ratio: Optional[float] = Field(None, description="Sharpe ratio")
    total_trades: int = Field(..., description="Total number of trades")
    winning_trades: int = Field(..., description="Number of winning trades")
    losing_trades: int = Field(..., description="Number of losing trades")
    win_rate_pct: float = Field(..., description="Win rate percentage")
    initial_capital: float = Field(..., description="Initial capital")
    final_value: float = Field(..., description="Final portfolio value")
    profit_loss: float = Field(..., description="Total profit/loss")


class BacktestResultData(BaseModel):
    """Full backtest result."""

    strategy_id: str
    success: bool
    metrics: Optional[BacktestMetrics] = None
    equity_curve: Optional[List[List[Any]]] = Field(
        None, description="[[date, value], ...] for chart"
    )
    trades: Optional[List[BacktestTradeRecord]] = None
    message: str = ""
    chart: Optional[str] = Field(None, description="Plotly chart JSON")


# Typed responses
PythonStrategyListResponse = SuccessResponse[List[PythonStrategyItem]]
PythonStrategyCreateResponse = SuccessResponse[PythonStrategyItem]
PythonStrategyUpdateResponse = SuccessResponse[PythonStrategyItem]
BacktestResultResponse = SuccessResponse[BacktestResultData]
