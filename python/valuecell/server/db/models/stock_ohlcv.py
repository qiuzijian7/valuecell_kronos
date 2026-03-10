"""Stock OHLCV (Open/High/Low/Close/Volume) data model.

Stores daily candlestick data locally to reduce Yahoo Finance API calls
and avoid rate-limiting issues.
"""

from sqlalchemy import Column, Date, Float, Index, Integer, String
from sqlalchemy.sql import func
from sqlalchemy import DateTime

from .base import Base


class StockOHLCV(Base):
    """Daily OHLCV bar for a single ticker.

    Composite unique constraint on (ticker, interval, date) ensures
    no duplicate bars are stored.
    """

    __tablename__ = "stock_ohlcv"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Ticker in internal format, e.g. "NASDAQ:AAPL", "SSE:601398"
    ticker = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Ticker in EXCHANGE:SYMBOL format",
    )

    # Data interval: "1d", "1h", etc.
    interval = Column(
        String(10),
        nullable=False,
        default="1d",
        comment="Bar interval (1d, 1h, etc.)",
    )

    # Bar date (for daily data, time component is midnight)
    date = Column(Date, nullable=False, comment="Bar date")

    # OHLCV fields
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=True)

    # Metadata
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_stock_ohlcv_ticker_interval_date", "ticker", "interval", "date", unique=True),
    )

    def __repr__(self) -> str:
        return (
            f"<StockOHLCV(ticker='{self.ticker}', date={self.date}, "
            f"close={self.close})>"
        )
