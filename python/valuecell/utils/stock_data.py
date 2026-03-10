"""Direct Yahoo Finance REST API data fetcher.

Bypasses the yfinance library to avoid rate limiting issues.
Uses the Yahoo Finance v8 chart API with User-Agent rotation and retry logic.
"""

import random
import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests
from loguru import logger

# User-Agent pool for rotation to reduce rate limiting
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

DEFAULT_TIMEOUT_S: float = 30.0
MAX_RETRIES: int = 5
RETRY_BACKOFF_BASE_S: float = 2.0

# Reusable session for connection pooling and cookie persistence
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """Return a reusable session with cookie persistence."""
    global _session  # noqa: PLW0603
    if _session is None:
        _session = requests.Session()
        # Warm up cookies by visiting the Yahoo Finance page once
        try:
            _session.get(
                "https://finance.yahoo.com",
                headers=_get_random_headers(),
                timeout=10,
            )
        except requests.RequestException:
            pass
    return _session


def _get_random_headers() -> dict:
    """Build request headers with a random User-Agent."""
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _convert_ticker_to_yahoo(ticker: str) -> str:
    """Convert internal ticker format to Yahoo Finance symbol.

    Internal format: ``EXCHANGE:SYMBOL`` (e.g. ``NASDAQ:AAPL``, ``SSE:601398``).
    Also handles plain symbols like ``AAPL``.
    """
    if ":" not in ticker:
        return ticker

    exchange, symbol = ticker.split(":", 1)
    exchange_upper = exchange.upper()

    suffix_map = {
        "SSE": ".SS",
        "SZSE": ".SZ",
        "HKEX": ".HK",
        "CRYPTO": "-USD",
    }

    suffix = suffix_map.get(exchange_upper, "")

    if exchange_upper == "HKEX" and symbol.isdigit():
        symbol = str(int(symbol)).zfill(4)

    return f"{symbol}{suffix}"


def fetch_ohlcv(
    ticker: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: Optional[str] = None,
    interval: str = "1d",
    timeout: float = DEFAULT_TIMEOUT_S,
) -> pd.DataFrame:
    """Fetch OHLCV data from Yahoo Finance REST API.

    Either *period* **or** *start_date*/*end_date* should be provided.
    When *period* is given, the date range is computed automatically.

    Args:
        ticker: Stock symbol in internal format (``EXCHANGE:SYMBOL``) or
            plain Yahoo format (``AAPL``).
        start_date: Start date string ``YYYY-MM-DD``. Ignored if *period* is set.
        end_date: End date string ``YYYY-MM-DD``. Defaults to today.
        period: Shorthand period such as ``1y``, ``2y``, ``6mo``, ``max``.
            Takes precedence over *start_date*/*end_date*.
        interval: Data interval (``1d``, ``1h``, ``5m``, etc.).
        timeout: HTTP request timeout in seconds.

    Returns:
        DataFrame with columns: ``Date``, ``Open``, ``High``, ``Low``,
        ``Close``, ``Volume``.  Index is ``RangeIndex`` (not DatetimeIndex).

    Raises:
        ValueError: If no data is returned.
        ConnectionError: If the HTTP request fails after retries.
    """
    yahoo_symbol = _convert_ticker_to_yahoo(ticker)

    # Build timestamps ---------------------------------------------------
    if period is not None:
        params = _build_period_params(period, interval)
    else:
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

        period1 = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
        period2 = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp()) + 86400
        params = {
            "period1": period1,
            "period2": period2,
            "interval": interval,
            "includePrePost": "false",
            "events": "div,splits",
        }

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"

    # Retry loop ---------------------------------------------------------
    session = _get_session()
    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(
                url,
                params=params,
                headers=_get_random_headers(),
                timeout=timeout,
            )
            if resp.status_code == 429:
                wait = RETRY_BACKOFF_BASE_S * (2 ** attempt) + random.uniform(0, 2)
                logger.warning(
                    "Yahoo Finance rate-limited (429), retrying in {w:.1f}s (attempt {a}/{m})",
                    w=wait,
                    a=attempt + 1,
                    m=MAX_RETRIES,
                )
                time.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()
            break
        except requests.RequestException as exc:
            last_exc = exc
            wait = RETRY_BACKOFF_BASE_S * (2 ** attempt) + random.uniform(0, 2)
            logger.warning(
                "Yahoo Finance request failed: {err}, retrying in {w:.1f}s (attempt {a}/{m})",
                err=str(exc),
                w=wait,
                a=attempt + 1,
                m=MAX_RETRIES,
            )
            time.sleep(wait)
    else:
        raise ConnectionError(
            f"Failed to fetch data for {ticker} after {MAX_RETRIES} retries: {last_exc}"
        )

    # Parse response -----------------------------------------------------
    chart = data.get("chart", {})
    results = chart.get("result")
    if not results:
        error_desc = chart.get("error", {}).get("description", "unknown error")
        raise ValueError(
            f"No data returned for {ticker} ({yahoo_symbol}): {error_desc}"
        )

    result = results[0]
    timestamps = result.get("timestamp")
    if not timestamps:
        raise ValueError(f"No timestamps in response for {ticker}")

    quote = result["indicators"]["quote"][0]

    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(timestamps, unit="s"),
            "Open": quote.get("open", []),
            "High": quote.get("high", []),
            "Low": quote.get("low", []),
            "Close": quote.get("close", []),
            "Volume": quote.get("volume", []),
        }
    )

    # Drop rows with missing price data
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df = df.sort_values("Date").reset_index(drop=True)

    if df.empty:
        raise ValueError(f"All rows contained NaN for {ticker}")

    logger.info(
        "Fetched {n} bars for {t} ({s}), range {start} ~ {end}",
        n=len(df),
        t=ticker,
        s=yahoo_symbol,
        start=df["Date"].iloc[0].date(),
        end=df["Date"].iloc[-1].date(),
    )
    return df


def _build_period_params(period: str, interval: str) -> dict:
    """Convert a period string to query parameters with timestamps."""
    now = datetime.now()

    period_deltas = {
        "1d": timedelta(days=1),
        "5d": timedelta(days=5),
        "1mo": timedelta(days=30),
        "3mo": timedelta(days=90),
        "6mo": timedelta(days=180),
        "1y": timedelta(days=365),
        "2y": timedelta(days=730),
        "5y": timedelta(days=1825),
        "10y": timedelta(days=3650),
        "ytd": timedelta(days=(now - datetime(now.year, 1, 1)).days),
    }

    if period == "max":
        period1 = 0
    elif period in period_deltas:
        period1 = int((now - period_deltas[period]).timestamp())
    else:
        # Fallback: try to parse as Nd (e.g. "730d")
        try:
            days = int(period.rstrip("d"))
            period1 = int((now - timedelta(days=days)).timestamp())
        except ValueError:
            period1 = int((now - timedelta(days=365)).timestamp())

    period2 = int(now.timestamp()) + 86400

    return {
        "period1": period1,
        "period2": period2,
        "interval": interval,
        "includePrePost": "false",
        "events": "div,splits",
    }
