"""Python Strategy CRUD and Backtest Router."""

from typing import List, Optional

from fastapi import APIRouter
from loguru import logger

from ...db.connection import get_database_manager
from ...db.models.python_strategy import PythonStrategy
from ...services.backtest_engine import run_backtest
from ..schemas import SuccessResponse
from ..schemas.python_strategy import (
    BacktestRequest,
    BacktestResultData,
    BacktestResultResponse,
    PythonStrategyCreateRequest,
    PythonStrategyCreateResponse,
    PythonStrategyItem,
    PythonStrategyListResponse,
    PythonStrategyUpdateRequest,
    PythonStrategyUpdateResponse,
)

# Default strategy template
DEFAULT_STRATEGY_CODE = '''"""My Strategy

Define a `strategy(ctx)` function that is called on each bar.

ctx attributes:
  ctx.date       - current bar date string (YYYY-MM-DD)
  ctx.open       - open price
  ctx.high       - high price
  ctx.low        - low price
  ctx.close      - close price
  ctx.volume     - volume
  ctx.position   - current shares held
  ctx.cash       - available cash
  ctx.portfolio_value - total portfolio value
  ctx.history    - DataFrame of all bars up to now (columns: Date, Open, High, Low, Close, Volume)

ctx methods:
  ctx.buy(shares=None)   - buy shares (None = max affordable)
  ctx.sell(shares=None)  - sell shares (None = sell all)

Available modules: math, pd (pandas)
"""


def strategy(ctx):
    # Simple moving-average crossover example
    if len(ctx.history) < 20:
        return

    closes = ctx.history["Close"]
    sma5 = closes.iloc[-5:].mean()
    sma20 = closes.iloc[-20:].mean()

    if sma5 > sma20 and ctx.position == 0:
        ctx.buy()
    elif sma5 < sma20 and ctx.position > 0:
        ctx.sell()
'''


def _model_to_item(m: PythonStrategy) -> PythonStrategyItem:
    """Convert a DB model instance to an API response item."""
    return PythonStrategyItem(
        id=str(m.id),
        name=m.name,
        description=m.description,
        code=m.code,
        status=m.status,
        backtest_config=m.backtest_config,
        backtest_result=m.backtest_result,
        backtest_error=m.backtest_error,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def create_python_strategy_router() -> APIRouter:
    """Create the Python strategy router."""
    router = APIRouter(prefix="/python-strategies", tags=["python-strategies"])

    # ------------------------------------------------------------------
    # List all
    # ------------------------------------------------------------------
    @router.get("/", response_model=PythonStrategyListResponse)
    async def list_strategies():
        """List all Python strategies."""
        session = get_database_manager().get_session()
        try:
            items = (
                session.query(PythonStrategy)
                .order_by(PythonStrategy.updated_at.desc())
                .all()
            )
            result = [_model_to_item(m) for m in items]
            return SuccessResponse.create(data=result)
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Get single
    # ------------------------------------------------------------------
    @router.get("/{strategy_id}", response_model=PythonStrategyCreateResponse)
    async def get_strategy(strategy_id: str):
        """Get a single Python strategy by ID."""
        session = get_database_manager().get_session()
        try:
            m = (
                session.query(PythonStrategy)
                .filter(PythonStrategy.id == strategy_id)
                .first()
            )
            if m is None:
                return SuccessResponse.create(data=None, msg="Strategy not found")
            return SuccessResponse.create(data=_model_to_item(m))
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    @router.post("/", response_model=PythonStrategyCreateResponse)
    async def create_strategy(req: PythonStrategyCreateRequest):
        """Create a new Python strategy."""
        session = get_database_manager().get_session()
        try:
            m = PythonStrategy(
                name=req.name,
                description=req.description,
                code=req.code or DEFAULT_STRATEGY_CODE,
            )
            session.add(m)
            session.commit()
            session.refresh(m)
            return SuccessResponse.create(data=_model_to_item(m))
        except Exception as exc:
            session.rollback()
            logger.warning("Create python strategy failed: {err}", err=str(exc))
            return SuccessResponse.create(data=None, msg=f"Create failed: {exc}")
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    @router.put("/{strategy_id}", response_model=PythonStrategyUpdateResponse)
    async def update_strategy(strategy_id: str, req: PythonStrategyUpdateRequest):
        """Update an existing Python strategy."""
        session = get_database_manager().get_session()
        try:
            m = (
                session.query(PythonStrategy)
                .filter(PythonStrategy.id == strategy_id)
                .first()
            )
            if m is None:
                return SuccessResponse.create(data=None, msg="Strategy not found")
            if req.name is not None:
                m.name = req.name
            if req.description is not None:
                m.description = req.description
            if req.code is not None:
                m.code = req.code
                # Reset status when code changes
                m.status = "draft"
                m.backtest_result = None
                m.backtest_error = None
            session.commit()
            session.refresh(m)
            return SuccessResponse.create(data=_model_to_item(m))
        except Exception as exc:
            session.rollback()
            logger.warning("Update python strategy failed: {err}", err=str(exc))
            return SuccessResponse.create(data=None, msg=f"Update failed: {exc}")
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------
    @router.delete("/{strategy_id}", response_model=SuccessResponse)
    async def delete_strategy(strategy_id: str):
        """Delete a Python strategy."""
        session = get_database_manager().get_session()
        try:
            m = (
                session.query(PythonStrategy)
                .filter(PythonStrategy.id == strategy_id)
                .first()
            )
            if m is None:
                return SuccessResponse.create(msg="Strategy not found")
            session.delete(m)
            session.commit()
            return SuccessResponse.create(msg="Deleted")
        except Exception as exc:
            session.rollback()
            logger.warning("Delete python strategy failed: {err}", err=str(exc))
            return SuccessResponse.create(msg=f"Delete failed: {exc}")
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Run backtest
    # ------------------------------------------------------------------
    @router.post("/backtest", response_model=BacktestResultResponse)
    async def backtest(req: BacktestRequest):
        """Execute backtest for a Python strategy."""
        try:
            session = get_database_manager().get_session()
            try:
                m = (
                    session.query(PythonStrategy)
                    .filter(PythonStrategy.id == req.strategy_id)
                    .first()
                )
                if m is None:
                    return SuccessResponse.create(
                        data=BacktestResultData(
                            strategy_id=req.strategy_id,
                            success=False,
                            message="Strategy not found",
                        )
                    )

                strategy_code = m.code

                # Mark as backtesting
                m.status = "backtesting"
                m.backtest_config = {
                    "symbol": req.symbol,
                    "start_date": req.start_date,
                    "end_date": req.end_date,
                    "initial_capital": req.initial_capital,
                    "commission_rate": req.commission_rate,
                }
                m.backtest_error = None
                session.commit()
            finally:
                session.close()

            # Run backtest (outside session)
            result = await run_backtest(
                code=strategy_code,
                symbol=req.symbol,
                start_date=req.start_date,
                end_date=req.end_date,
                initial_capital=req.initial_capital,
                commission_rate=req.commission_rate,
            )

            # Persist result
            session = get_database_manager().get_session()
            try:
                m = (
                    session.query(PythonStrategy)
                    .filter(PythonStrategy.id == req.strategy_id)
                    .first()
                )
                if m is not None:
                    if result["success"]:
                        m.status = "completed"
                        m.backtest_result = {
                            "metrics": result["metrics"],
                            "equity_curve": result.get("equity_curve"),
                            "trades": result.get("trades"),
                        }
                        m.backtest_error = None
                    else:
                        m.status = "error"
                        m.backtest_error = result.get("message", "Unknown error")
                    session.commit()
            except Exception as exc:
                session.rollback()
                logger.warning("Persist backtest result failed: {err}", err=str(exc))
            finally:
                session.close()

            return SuccessResponse.create(
                data=BacktestResultData(
                    strategy_id=req.strategy_id,
                    success=result["success"],
                    metrics=result.get("metrics"),
                    equity_curve=result.get("equity_curve"),
                    trades=result.get("trades"),
                    message=result.get("message", ""),
                    chart=result.get("chart"),
                )
            )
        except Exception as exc:
            import traceback

            tb = traceback.format_exc()
            logger.error("Backtest endpoint error: {err}\n{tb}", err=str(exc), tb=tb)
            return SuccessResponse.create(
                data=BacktestResultData(
                    strategy_id=req.strategy_id,
                    success=False,
                    message=f"Server error: {exc}",
                )
            )

    # ------------------------------------------------------------------
    # Get default template
    # ------------------------------------------------------------------
    @router.get("/template/default", response_model=SuccessResponse)
    async def get_default_template():
        """Get the default strategy code template."""
        return SuccessResponse.create(data={"code": DEFAULT_STRATEGY_CODE})

    return router
