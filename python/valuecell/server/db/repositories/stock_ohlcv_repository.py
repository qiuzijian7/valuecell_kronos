"""Repository for stock OHLCV data local caching.

Provides methods to query cached bars, detect date gaps,
and bulk-insert new bars from the Yahoo Finance API.
"""

from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy import and_, delete, func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..connection import get_database_manager
from ..models.stock_ohlcv import StockOHLCV

# How many hours before we consider cached data "stale" for the latest date
_CACHE_STALENESS_HOURS: int = 6


class StockOHLCVRepository:
    """Read / write helpers for the stock_ohlcv table."""

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_cached_range(
        session: Session,
        ticker: str,
        interval: str = "1d",
    ) -> tuple[Optional[date], Optional[date]]:
        """Return (earliest_date, latest_date) of cached bars, or (None, None)."""
        row = (
            session.query(
                func.min(StockOHLCV.date),
                func.max(StockOHLCV.date),
            )
            .filter(
                StockOHLCV.ticker == ticker,
                StockOHLCV.interval == interval,
            )
            .one()
        )
        return row[0], row[1]

    @staticmethod
    def query_bars(
        session: Session,
        ticker: str,
        start_date: date,
        end_date: date,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Return cached bars as a DataFrame matching fetch_ohlcv output format."""
        rows = (
            session.query(StockOHLCV)
            .filter(
                StockOHLCV.ticker == ticker,
                StockOHLCV.interval == interval,
                StockOHLCV.date >= start_date,
                StockOHLCV.date <= end_date,
            )
            .order_by(StockOHLCV.date)
            .all()
        )
        if not rows:
            return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])

        df = pd.DataFrame(
            [
                {
                    "Date": pd.Timestamp(r.date),
                    "Open": r.open,
                    "High": r.high,
                    "Low": r.low,
                    "Close": r.close,
                    "Volume": r.volume,
                }
                for r in rows
            ]
        )
        return df

    @staticmethod
    def count_bars(
        session: Session,
        ticker: str,
        interval: str = "1d",
    ) -> int:
        """Return total number of cached bars for a ticker."""
        return (
            session.query(func.count(StockOHLCV.id))
            .filter(
                StockOHLCV.ticker == ticker,
                StockOHLCV.interval == interval,
            )
            .scalar()
        ) or 0

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    @staticmethod
    def upsert_bars(
        session: Session,
        ticker: str,
        df: pd.DataFrame,
        interval: str = "1d",
    ) -> int:
        """Bulk upsert bars from a DataFrame into the cache.

        Uses SQLite INSERT OR REPLACE semantics to handle duplicates.
        Returns the number of rows upserted.
        """
        if df.empty:
            return 0

        records = []
        for _, row in df.iterrows():
            bar_date = pd.Timestamp(row["Date"]).date()
            records.append(
                {
                    "ticker": ticker,
                    "interval": interval,
                    "date": bar_date,
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row["Volume"]) if pd.notna(row.get("Volume")) else None,
                }
            )

        # SQLite upsert: ON CONFLICT DO UPDATE
        stmt = sqlite_insert(StockOHLCV).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "interval", "date"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
            },
        )
        session.execute(stmt)
        session.commit()

        logger.info(
            "Upserted {n} bars for {t} ({iv})",
            n=len(records),
            t=ticker,
            iv=interval,
        )
        return len(records)

    @staticmethod
    def delete_bars(
        session: Session,
        ticker: str,
        interval: str = "1d",
    ) -> int:
        """Delete all cached bars for a ticker. Returns deleted count."""
        result = session.execute(
            delete(StockOHLCV).where(
                and_(
                    StockOHLCV.ticker == ticker,
                    StockOHLCV.interval == interval,
                )
            )
        )
        session.commit()
        return result.rowcount

    # ------------------------------------------------------------------
    # Cache-aware fetch logic
    # ------------------------------------------------------------------

    @staticmethod
    def is_cache_fresh(
        latest_cached: Optional[date],
        target_end: date,
    ) -> bool:
        """Check if cached data is fresh enough.

        We consider the cache fresh if the latest cached date
        is within _CACHE_STALENESS_HOURS of the target end date,
        accounting for weekends/holidays (allow up to 4-day gap).
        """
        if latest_cached is None:
            return False
        gap = (target_end - latest_cached).days
        # For daily data, a gap of 0-4 days is acceptable
        # (covers weekends + possible holidays)
        return gap <= 4

    @staticmethod
    def compute_missing_range(
        cached_start: Optional[date],
        cached_end: Optional[date],
        target_start: date,
        target_end: date,
    ) -> list[tuple[date, date]]:
        """Compute date ranges that need fetching.

        Returns a list of (start, end) tuples representing gaps.
        Simplified: we only check the tail (most common case is
        the cache is stale by a few recent days).
        """
        ranges = []

        if cached_start is None:
            # No cache at all — fetch everything
            ranges.append((target_start, target_end))
            return ranges

        # Head gap: target starts before cache
        if target_start < cached_start:
            ranges.append((target_start, cached_start - timedelta(days=1)))

        # Tail gap: cache ends before target
        if cached_end < target_end:
            fetch_start = cached_end + timedelta(days=1)
            if fetch_start <= target_end:
                ranges.append((fetch_start, target_end))

        return ranges


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_repo: Optional[StockOHLCVRepository] = None


def get_stock_ohlcv_repository() -> StockOHLCVRepository:
    """Return a singleton StockOHLCVRepository."""
    global _repo  # noqa: PLW0603
    if _repo is None:
        _repo = StockOHLCVRepository()
    return _repo
