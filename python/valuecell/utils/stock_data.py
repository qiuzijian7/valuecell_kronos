"""Stock OHLCV data fetcher with local database caching.

Fetches data from Yahoo Finance REST API and caches it in the local
SQLite database. Subsequent requests are served from the cache when fresh,
with incremental updates for missing date ranges only.
"""

import random
import time
from datetime import date, datetime, timedelta
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
    use_cache: bool = True,
) -> pd.DataFrame:
    """Fetch OHLCV data, using local DB cache when available.

    Flow:
    1. Resolve the requested date range.
    2. If ``use_cache`` is True and interval is daily, query the local
       database for cached bars.
    3. If the cache fully covers the range and is fresh, return it.
    4. Otherwise, fetch only the missing date ranges from Yahoo Finance,
       store the new bars in the cache, and return the merged result.

    Args:
        ticker: Stock symbol in internal format (``EXCHANGE:SYMBOL``) or
            plain Yahoo format (``AAPL``).
        start_date: Start date string ``YYYY-MM-DD``. Ignored if *period* is set.
        end_date: End date string ``YYYY-MM-DD``. Defaults to today.
        period: Shorthand period such as ``1y``, ``2y``, ``6mo``, ``max``.
            Takes precedence over *start_date*/*end_date*.
        interval: Data interval (``1d``, ``1h``, ``5m``, etc.).
        timeout: HTTP request timeout in seconds.
        use_cache: Whether to use local DB caching (default True).
            Only effective for daily (``1d``) interval.

    Returns:
        DataFrame with columns: ``Date``, ``Open``, ``High``, ``Low``,
        ``Close``, ``Volume``.  Index is ``RangeIndex`` (not DatetimeIndex).

    Raises:
        ValueError: If no data is returned.
        ConnectionError: If the HTTP request fails after retries.
    """
    # Resolve target date range ------------------------------------------
    target_start, target_end = _resolve_date_range(start_date, end_date, period)

    # Only cache daily data — intraday data changes too fast
    can_cache = use_cache and interval == "1d"

    if can_cache:
        try:
            return _fetch_with_cache(ticker, target_start, target_end, interval, timeout)
        except Exception as cache_err:
            logger.warning(
                "Cache fetch failed for {t}, falling back to remote: {err}",
                t=ticker,
                err=str(cache_err),
            )

    # Fallback: direct remote fetch
    return _fetch_remote_ohlcv(
        ticker,
        start_date=target_start.isoformat(),
        end_date=target_end.isoformat(),
        interval=interval,
        timeout=timeout,
    )


def _resolve_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
    period: Optional[str],
) -> tuple[date, date]:
    """Convert period / start_date / end_date into a concrete (start, end) pair."""
    now = datetime.now()
    resolved_end = now.date()

    if period is not None:
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
            resolved_start = date(1970, 1, 1)
        elif period in period_deltas:
            resolved_start = (now - period_deltas[period]).date()
        else:
            try:
                days = int(period.rstrip("d"))
                resolved_start = (now - timedelta(days=days)).date()
            except ValueError:
                resolved_start = (now - timedelta(days=365)).date()
        return resolved_start, resolved_end

    if end_date is not None:
        resolved_end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if start_date is not None:
        resolved_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    else:
        resolved_start = (datetime.now() - timedelta(days=365)).date()

    return resolved_start, resolved_end


def _fetch_with_cache(
    ticker: str,
    target_start: date,
    target_end: date,
    interval: str,
    timeout: float,
) -> pd.DataFrame:
    """Try to serve from cache; fetch missing ranges from remote."""
    from valuecell.server.db.connection import get_database_manager
    from valuecell.server.db.repositories.stock_ohlcv_repository import (
        StockOHLCVRepository,
        get_stock_ohlcv_repository,
    )

    repo = get_stock_ohlcv_repository()
    db_manager = get_database_manager()
    session = db_manager.get_session()

    try:
        cached_start, cached_end = repo.get_cached_range(session, ticker, interval)

        # If cache is fresh enough, serve directly
        if cached_start is not None and cached_end is not None:
            if (
                cached_start <= target_start
                and repo.is_cache_fresh(cached_end, target_end)
            ):
                df = repo.query_bars(session, ticker, target_start, target_end, interval)
                if not df.empty:
                    logger.info(
                        "Cache hit for {t}: {n} bars ({s} ~ {e})",
                        t=ticker,
                        n=len(df),
                        s=target_start,
                        e=target_end,
                    )
                    return df

        # Compute what's missing
        missing_ranges = repo.compute_missing_range(
            cached_start, cached_end, target_start, target_end
        )

        if not missing_ranges:
            # Everything is cached
            df = repo.query_bars(session, ticker, target_start, target_end, interval)
            if not df.empty:
                return df

        # Fetch missing ranges from remote and store
        for range_start, range_end in missing_ranges:
            try:
                remote_df = _fetch_remote_ohlcv(
                    ticker,
                    start_date=range_start.isoformat(),
                    end_date=range_end.isoformat(),
                    interval=interval,
                    timeout=timeout,
                )
                if not remote_df.empty:
                    repo.upsert_bars(session, ticker, remote_df, interval)
            except (ValueError, ConnectionError) as fetch_err:
                logger.warning(
                    "Failed to fetch range {s}~{e} for {t}: {err}",
                    s=range_start,
                    e=range_end,
                    t=ticker,
                    err=str(fetch_err),
                )

        # Now serve the full range from cache
        df = repo.query_bars(session, ticker, target_start, target_end, interval)
        if df.empty:
            raise ValueError(f"No data available for {ticker} after cache update")

        logger.info(
            "Serving {n} bars for {t} from cache ({s} ~ {e})",
            n=len(df),
            t=ticker,
            s=target_start,
            e=target_end,
        )
        return df
    finally:
        session.close()


def _fetch_remote_ohlcv(
    ticker: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    interval: str = "1d",
    timeout: float = DEFAULT_TIMEOUT_S,
) -> pd.DataFrame:
    """Fetch OHLCV data directly from Yahoo Finance REST API.

    This is the raw remote fetcher — no caching involved.
    """
    yahoo_symbol = _convert_ticker_to_yahoo(ticker)

    # Build timestamps ---------------------------------------------------
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
        "Fetched {n} bars for {t} ({s}) from Yahoo Finance, range {start} ~ {end}",
        n=len(df),
        t=ticker,
        s=yahoo_symbol,
        start=df["Date"].iloc[0].date(),
        end=df["Date"].iloc[-1].date(),
    )
    return df



