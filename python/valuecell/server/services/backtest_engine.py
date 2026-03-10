"""Backtest engine for user-created Python strategies.

Executes user strategy code in a sandboxed context against historical market data,
tracks trades, and computes performance metrics.
"""

import json
import math
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    """A single completed round-trip trade."""

    date: str
    action: str  # "BUY" or "SELL"
    symbol: str
    price: float
    shares: float
    value: float
    commission: float


@dataclass
class BacktestContext:
    """Mutable context passed into the user strategy on each bar."""

    symbol: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    position: float = 0.0
    cash: float = 0.0
    portfolio_value: float = 0.0
    history: pd.DataFrame = field(default_factory=pd.DataFrame)

    # Internal helpers exposed to user code
    _trades: List[Trade] = field(default_factory=list)
    _commission_rate: float = 0.001

    def buy(self, shares: Optional[float] = None) -> None:
        """Buy *shares* units (defaults to max affordable)."""
        price = self.close
        if shares is None:
            affordable = self.cash / (price * (1 + self._commission_rate))
            shares = math.floor(affordable)
        if shares <= 0:
            return
        cost = shares * price
        commission = cost * self._commission_rate
        if cost + commission > self.cash:
            return
        self.cash -= cost + commission
        self.position += shares
        self._trades.append(
            Trade(
                date=self.date,
                action="BUY",
                symbol=self.symbol,
                price=price,
                shares=shares,
                value=cost,
                commission=commission,
            )
        )

    def sell(self, shares: Optional[float] = None) -> None:
        """Sell *shares* units (defaults to entire position)."""
        if self.position <= 0:
            return
        price = self.close
        if shares is None:
            shares = self.position
        shares = min(shares, self.position)
        if shares <= 0:
            return
        revenue = shares * price
        commission = revenue * self._commission_rate
        self.cash += revenue - commission
        self.position -= shares
        self._trades.append(
            Trade(
                date=self.date,
                action="SELL",
                symbol=self.symbol,
                price=price,
                shares=shares,
                value=revenue,
                commission=commission,
            )
        )


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _compute_metrics(
    equity_curve: List[float],
    trades: List[Trade],
    initial_capital: float,
) -> Dict[str, Any]:
    """Compute standard backtest metrics from an equity curve."""
    final_value = equity_curve[-1] if equity_curve else initial_capital
    total_return_pct = ((final_value - initial_capital) / initial_capital) * 100

    # Max drawdown
    peak = initial_capital
    max_dd = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    max_drawdown_pct = max_dd * 100

    # Trade-level win/loss
    buy_trades: Dict[str, List[Trade]] = {}
    sell_trades: Dict[str, List[Trade]] = {}
    for t in trades:
        bucket = buy_trades if t.action == "BUY" else sell_trades
        bucket.setdefault(t.symbol, []).append(t)

    winning = 0
    losing = 0
    # Pair buys and sells sequentially
    for sym in buy_trades:
        buys = buy_trades[sym]
        sells = sell_trades.get(sym, [])
        for i, b in enumerate(buys):
            if i < len(sells):
                pnl = (sells[i].price - b.price) * b.shares
                if pnl >= 0:
                    winning += 1
                else:
                    losing += 1

    total_trades = len(trades)
    total_round_trips = winning + losing
    win_rate = (winning / total_round_trips * 100) if total_round_trips > 0 else 0.0

    # Annualised return
    n_days = len(equity_curve)
    annual_return_pct: Optional[float] = None
    if n_days > 1 and final_value > 0 and initial_capital > 0:
        years = n_days / 252
        if years > 0:
            annual_return_pct = ((final_value / initial_capital) ** (1 / years) - 1) * 100

    # Sharpe ratio (daily returns, annualised)
    sharpe: Optional[float] = None
    if len(equity_curve) > 2:
        returns = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1]
            if prev > 0:
                returns.append((equity_curve[i] - prev) / prev)
        if returns:
            import statistics

            mean_r = statistics.mean(returns)
            std_r = statistics.stdev(returns) if len(returns) > 1 else 0
            if std_r > 0:
                sharpe = (mean_r / std_r) * math.sqrt(252)

    return {
        "total_return_pct": round(total_return_pct, 2),
        "annual_return_pct": round(annual_return_pct, 2) if annual_return_pct is not None else None,
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
        "total_trades": total_trades,
        "winning_trades": winning,
        "losing_trades": losing,
        "win_rate_pct": round(win_rate, 2),
        "initial_capital": initial_capital,
        "final_value": round(final_value, 2),
        "profit_loss": round(final_value - initial_capital, 2),
    }


# ---------------------------------------------------------------------------
# Chart builder
# ---------------------------------------------------------------------------

def _build_chart_json(
    dates: List[str],
    equity_curve: List[float],
    trades: List[Trade],
    ohlc_df: pd.DataFrame,
) -> Optional[str]:
    """Build a Plotly chart JSON with equity curve, candlestick, and trade markers."""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.08,
            row_heights=[0.6, 0.4],
            subplot_titles=("Price", "Portfolio Value"),
        )

        # Candlestick
        fig.add_trace(
            go.Candlestick(
                x=dates,
                open=ohlc_df["Open"].tolist(),
                high=ohlc_df["High"].tolist(),
                low=ohlc_df["Low"].tolist(),
                close=ohlc_df["Close"].tolist(),
                name="Price",
                increasing_line_color="#26A69A",
                decreasing_line_color="#EF5350",
            ),
            row=1,
            col=1,
        )

        # Buy markers
        buy_dates = [t.date for t in trades if t.action == "BUY"]
        buy_prices = [t.price for t in trades if t.action == "BUY"]
        if buy_dates:
            fig.add_trace(
                go.Scatter(
                    x=buy_dates,
                    y=buy_prices,
                    mode="markers",
                    marker=dict(symbol="triangle-up", size=10, color="#26A69A"),
                    name="Buy",
                ),
                row=1,
                col=1,
            )

        # Sell markers
        sell_dates = [t.date for t in trades if t.action == "SELL"]
        sell_prices = [t.price for t in trades if t.action == "SELL"]
        if sell_dates:
            fig.add_trace(
                go.Scatter(
                    x=sell_dates,
                    y=sell_prices,
                    mode="markers",
                    marker=dict(symbol="triangle-down", size=10, color="#EF5350"),
                    name="Sell",
                ),
                row=1,
                col=1,
            )

        # Equity curve
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=equity_curve,
                mode="lines",
                line=dict(color="#42A5F5", width=2),
                name="Portfolio",
            ),
            row=2,
            col=1,
        )

        fig.update_layout(
            template="plotly_white",
            height=560,
            showlegend=True,
            xaxis_rangeslider_visible=False,
            xaxis2_rangeslider_visible=False,
        )

        return json.dumps(fig.to_dict())
    except Exception as exc:
        logger.warning("Chart generation failed: {err}", err=str(exc))
        return None


# ---------------------------------------------------------------------------
# Fetch market data
# ---------------------------------------------------------------------------

async def _fetch_ohlcv(
    symbol: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Download OHLCV data via Yahoo Finance REST API (async-wrapped).

    Uses direct HTTP requests instead of yfinance to avoid rate limiting.
    """
    import asyncio

    from valuecell.utils.stock_data import fetch_ohlcv as _fetch

    def _download() -> pd.DataFrame:
        return _fetch(symbol, start_date=start_date, end_date=end_date, interval="1d")

    return await asyncio.to_thread(_download)


# ---------------------------------------------------------------------------
# Strategy execution
# ---------------------------------------------------------------------------

def _compile_strategy(code: str) -> Any:
    """Compile and extract the strategy function from user code.

    The user code must define a function ``strategy(ctx)`` that is called on each bar.
    """
    namespace: Dict[str, Any] = {}
    # Allow common imports in user code
    allowed_builtins = {
        "__builtins__": {
            "range": range,
            "len": len,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "list": list,
            "dict": dict,
            "tuple": tuple,
            "set": set,
            "sum": sum,
            "sorted": sorted,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "print": print,
            "isinstance": isinstance,
            "True": True,
            "False": False,
            "None": None,
        },
        "math": math,
        "pd": pd,
    }
    namespace.update(allowed_builtins)
    exec(compile(code, "<strategy>", "exec"), namespace)  # noqa: S102

    fn = namespace.get("strategy")
    if fn is None or not callable(fn):
        raise ValueError(
            "Strategy code must define a callable `strategy(ctx)` function."
        )
    return fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_backtest(
    code: str,
    symbol: str = "AAPL",
    start_date: str = "2024-01-01",
    end_date: str = "2025-01-01",
    initial_capital: float = 100_000.0,
    commission_rate: float = 0.001,
) -> Dict[str, Any]:
    """Run a backtest for the given Python strategy code.

    Returns a dict suitable for ``BacktestResultData`` schema.
    """
    try:
        strategy_fn = _compile_strategy(code)
    except Exception as exc:
        return {
            "success": False,
            "metrics": None,
            "equity_curve": None,
            "trades": None,
            "message": f"Strategy compilation error: {exc}",
            "chart": None,
        }

    try:
        df = await _fetch_ohlcv(symbol, start_date, end_date)
    except Exception as exc:
        return {
            "success": False,
            "metrics": None,
            "equity_curve": None,
            "trades": None,
            "message": f"Data fetch error: {exc}",
            "chart": None,
        }

    # Run bar-by-bar
    ctx = BacktestContext(
        symbol=symbol,
        date="",
        open=0,
        high=0,
        low=0,
        close=0,
        volume=0,
        cash=initial_capital,
        position=0,
        portfolio_value=initial_capital,
    )
    ctx._commission_rate = commission_rate

    equity_curve: List[float] = []
    dates: List[str] = []

    try:
        for i in range(len(df)):
            row = df.iloc[i]
            date_val = row.get("Date", row.get("Datetime", ""))
            if hasattr(date_val, "strftime"):
                date_str = date_val.strftime("%Y-%m-%d")
            else:
                date_str = str(date_val)

            ctx.date = date_str
            ctx.open = float(row["Open"])
            ctx.high = float(row["High"])
            ctx.low = float(row["Low"])
            ctx.close = float(row["Close"])
            ctx.volume = float(row.get("Volume", 0))
            ctx.history = df.iloc[: i + 1]

            strategy_fn(ctx)

            ctx.portfolio_value = ctx.cash + ctx.position * ctx.close
            equity_curve.append(round(ctx.portfolio_value, 2))
            dates.append(date_str)

    except Exception as exc:
        tb = traceback.format_exc()
        logger.warning("Strategy runtime error: {err}", err=str(exc))
        return {
            "success": False,
            "metrics": None,
            "equity_curve": None,
            "trades": None,
            "message": f"Strategy runtime error: {exc}\n{tb}",
            "chart": None,
        }

    # Compute metrics
    metrics = _compute_metrics(equity_curve, ctx._trades, initial_capital)

    # Build equity curve for frontend [[date, value], ...]
    eq_data = [[d, v] for d, v in zip(dates, equity_curve)]

    # Trade records
    trade_records = [
        {
            "date": t.date,
            "action": t.action,
            "symbol": t.symbol,
            "price": round(t.price, 4),
            "shares": t.shares,
            "value": round(t.value, 2),
            "commission": round(t.commission, 4),
        }
        for t in ctx._trades
    ]

    # Chart
    chart_json = _build_chart_json(dates, equity_curve, ctx._trades, df)

    return {
        "success": True,
        "metrics": metrics,
        "equity_curve": eq_data,
        "trades": trade_records,
        "message": f"Backtest completed: {len(dates)} bars, {len(ctx._trades)} trades",
        "chart": chart_json,
    }
