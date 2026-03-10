"""Pure-Python candlestick pattern recognition.

Detects common bullish / bearish K-line patterns from OHLCV DataFrames.
Each detector returns a list of PatternMatch objects describing where
the pattern was found and its sentiment (bullish / bearish / neutral).

No external dependencies beyond pandas and numpy.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


@dataclass(frozen=True)
class PatternMatch:
    """A single pattern detection result."""

    index: int  # Row index (iloc) of the signal bar
    date: str  # ISO date string
    name: str  # Pattern name (English key)
    label: str  # Display label (Chinese)
    sentiment: str  # "bullish" | "bearish" | "neutral"
    confidence: float  # 0.0 – 1.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _body(o: float, c: float) -> float:
    return abs(c - o)


def _upper_shadow(o: float, h: float, c: float) -> float:
    return h - max(o, c)


def _lower_shadow(o: float, l: float, c: float) -> float:
    return min(o, c) - l


def _is_bullish(o: float, c: float) -> bool:
    return c > o


def _is_bearish(o: float, c: float) -> bool:
    return c < o


def _avg_body(opens: np.ndarray, closes: np.ndarray, window: int = 14) -> np.ndarray:
    """Rolling average body size over *window* bars."""
    bodies = np.abs(closes - opens)
    if len(bodies) < window:
        return np.full_like(bodies, bodies.mean() if len(bodies) > 0 else 1.0)
    kernel = np.ones(window) / window
    avg = np.convolve(bodies, kernel, mode="full")[:len(bodies)]
    avg[:window] = bodies[:window].mean()
    return avg


# ---------------------------------------------------------------------------
# Individual pattern detectors
# ---------------------------------------------------------------------------

def _detect_doji(
    opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    avg_bodies: np.ndarray,
) -> list[tuple[int, str, str, str, float]]:
    """Doji: very small body relative to range."""
    results = []
    for i in range(len(opens)):
        body = _body(opens[i], closes[i])
        rng = highs[i] - lows[i]
        if rng == 0:
            continue
        if body / rng < 0.1 and body < avg_bodies[i] * 0.1:
            results.append((i, "doji", "十字星", "neutral", 0.7))
    return results


def _detect_hammer(
    opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    avg_bodies: np.ndarray,
) -> list[tuple[int, str, str, str, float]]:
    """Hammer / Hanging Man: small body at top, long lower shadow."""
    results = []
    for i in range(1, len(opens)):
        body = _body(opens[i], closes[i])
        ls = _lower_shadow(opens[i], lows[i], closes[i])
        us = _upper_shadow(opens[i], highs[i], closes[i])
        rng = highs[i] - lows[i]
        if rng == 0 or body == 0:
            continue
        if ls >= body * 2 and us <= body * 0.3:
            # Check preceding trend (3-bar simple check)
            if i >= 3 and closes[i - 1] < closes[i - 3]:
                results.append((i, "hammer", "锤子线", "bullish", 0.75))
            elif i >= 3 and closes[i - 1] > closes[i - 3]:
                results.append((i, "hanging_man", "上吊线", "bearish", 0.70))
            else:
                results.append((i, "hammer", "锤子线", "bullish", 0.60))
    return results


def _detect_inverted_hammer(
    opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    avg_bodies: np.ndarray,
) -> list[tuple[int, str, str, str, float]]:
    """Inverted Hammer / Shooting Star: small body at bottom, long upper shadow."""
    results = []
    for i in range(1, len(opens)):
        body = _body(opens[i], closes[i])
        ls = _lower_shadow(opens[i], lows[i], closes[i])
        us = _upper_shadow(opens[i], highs[i], closes[i])
        if body == 0:
            continue
        if us >= body * 2 and ls <= body * 0.3:
            if i >= 3 and closes[i - 1] > closes[i - 3]:
                results.append((i, "shooting_star", "射击之星", "bearish", 0.75))
            elif i >= 3 and closes[i - 1] < closes[i - 3]:
                results.append((i, "inverted_hammer", "倒锤子线", "bullish", 0.70))
            else:
                results.append((i, "shooting_star", "射击之星", "bearish", 0.60))
    return results


def _detect_engulfing(
    opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    avg_bodies: np.ndarray,
) -> list[tuple[int, str, str, str, float]]:
    """Bullish / Bearish Engulfing: current body completely engulfs previous body."""
    results = []
    for i in range(1, len(opens)):
        prev_body = _body(opens[i - 1], closes[i - 1])
        curr_body = _body(opens[i], closes[i])
        if curr_body <= prev_body or curr_body < avg_bodies[i] * 0.5:
            continue
        # Bullish engulfing: prev bearish, curr bullish, curr body engulfs prev
        if _is_bearish(opens[i - 1], closes[i - 1]) and _is_bullish(opens[i], closes[i]):
            if opens[i] <= closes[i - 1] and closes[i] >= opens[i - 1]:
                results.append((i, "bullish_engulfing", "看涨吞没", "bullish", 0.80))
        # Bearish engulfing
        elif _is_bullish(opens[i - 1], closes[i - 1]) and _is_bearish(opens[i], closes[i]):
            if opens[i] >= closes[i - 1] and closes[i] <= opens[i - 1]:
                results.append((i, "bearish_engulfing", "看跌吞没", "bearish", 0.80))
    return results


def _detect_morning_evening_star(
    opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    avg_bodies: np.ndarray,
) -> list[tuple[int, str, str, str, float]]:
    """Morning Star / Evening Star: 3-bar reversal patterns."""
    results = []
    for i in range(2, len(opens)):
        body0 = _body(opens[i - 2], closes[i - 2])
        body1 = _body(opens[i - 1], closes[i - 1])
        body2 = _body(opens[i], closes[i])
        avg = avg_bodies[i]
        # Middle bar should be small
        if body1 >= avg * 0.5:
            continue
        # Morning star: first bearish, third bullish, both with significant bodies
        if (
            _is_bearish(opens[i - 2], closes[i - 2])
            and body0 > avg * 0.6
            and _is_bullish(opens[i], closes[i])
            and body2 > avg * 0.6
            and closes[i] > (opens[i - 2] + closes[i - 2]) / 2
        ):
            results.append((i, "morning_star", "启明星", "bullish", 0.85))
        # Evening star: first bullish, third bearish
        elif (
            _is_bullish(opens[i - 2], closes[i - 2])
            and body0 > avg * 0.6
            and _is_bearish(opens[i], closes[i])
            and body2 > avg * 0.6
            and closes[i] < (opens[i - 2] + closes[i - 2]) / 2
        ):
            results.append((i, "evening_star", "黄昏之星", "bearish", 0.85))
    return results


def _detect_three_soldiers_crows(
    opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    avg_bodies: np.ndarray,
) -> list[tuple[int, str, str, str, float]]:
    """Three White Soldiers / Three Black Crows."""
    results = []
    for i in range(2, len(opens)):
        b0 = _body(opens[i - 2], closes[i - 2])
        b1 = _body(opens[i - 1], closes[i - 1])
        b2 = _body(opens[i], closes[i])
        avg = avg_bodies[i]
        min_body = avg * 0.4
        # Three white soldiers: 3 consecutive bullish bars with significant bodies
        if (
            _is_bullish(opens[i - 2], closes[i - 2]) and b0 > min_body
            and _is_bullish(opens[i - 1], closes[i - 1]) and b1 > min_body
            and _is_bullish(opens[i], closes[i]) and b2 > min_body
            and closes[i - 1] > closes[i - 2]
            and closes[i] > closes[i - 1]
            and opens[i - 1] > opens[i - 2]
            and opens[i] > opens[i - 1]
        ):
            results.append((i, "three_white_soldiers", "三白兵", "bullish", 0.80))
        # Three black crows
        elif (
            _is_bearish(opens[i - 2], closes[i - 2]) and b0 > min_body
            and _is_bearish(opens[i - 1], closes[i - 1]) and b1 > min_body
            and _is_bearish(opens[i], closes[i]) and b2 > min_body
            and closes[i - 1] < closes[i - 2]
            and closes[i] < closes[i - 1]
            and opens[i - 1] < opens[i - 2]
            and opens[i] < opens[i - 1]
        ):
            results.append((i, "three_black_crows", "三乌鸦", "bearish", 0.80))
    return results


def _detect_marubozu(
    opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    avg_bodies: np.ndarray,
) -> list[tuple[int, str, str, str, float]]:
    """Marubozu: no or very short shadows."""
    results = []
    for i in range(len(opens)):
        body = _body(opens[i], closes[i])
        rng = highs[i] - lows[i]
        if rng == 0 or body < avg_bodies[i] * 0.8:
            continue
        us = _upper_shadow(opens[i], highs[i], closes[i])
        ls = _lower_shadow(opens[i], lows[i], closes[i])
        if us <= body * 0.05 and ls <= body * 0.05:
            if _is_bullish(opens[i], closes[i]):
                results.append((i, "bullish_marubozu", "看涨光头光脚", "bullish", 0.75))
            else:
                results.append((i, "bearish_marubozu", "看跌光头光脚", "bearish", 0.75))
    return results


def _detect_harami(
    opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    avg_bodies: np.ndarray,
) -> list[tuple[int, str, str, str, float]]:
    """Bullish / Bearish Harami: small body contained within previous large body."""
    results = []
    for i in range(1, len(opens)):
        prev_body = _body(opens[i - 1], closes[i - 1])
        curr_body = _body(opens[i], closes[i])
        if prev_body < avg_bodies[i] * 0.6 or curr_body > prev_body * 0.5:
            continue
        prev_hi = max(opens[i - 1], closes[i - 1])
        prev_lo = min(opens[i - 1], closes[i - 1])
        curr_hi = max(opens[i], closes[i])
        curr_lo = min(opens[i], closes[i])
        if curr_hi <= prev_hi and curr_lo >= prev_lo:
            if _is_bearish(opens[i - 1], closes[i - 1]) and _is_bullish(opens[i], closes[i]):
                results.append((i, "bullish_harami", "看涨孕线", "bullish", 0.70))
            elif _is_bullish(opens[i - 1], closes[i - 1]) and _is_bearish(opens[i], closes[i]):
                results.append((i, "bearish_harami", "看跌孕线", "bearish", 0.70))
    return results


def _detect_piercing_dark_cloud(
    opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    avg_bodies: np.ndarray,
) -> list[tuple[int, str, str, str, float]]:
    """Piercing Line / Dark Cloud Cover."""
    results = []
    for i in range(1, len(opens)):
        prev_body = _body(opens[i - 1], closes[i - 1])
        curr_body = _body(opens[i], closes[i])
        if prev_body < avg_bodies[i] * 0.5 or curr_body < avg_bodies[i] * 0.5:
            continue
        prev_mid = (opens[i - 1] + closes[i - 1]) / 2
        # Piercing line: prev bearish, curr bullish, opens below prev close, closes above midpoint
        if (
            _is_bearish(opens[i - 1], closes[i - 1])
            and _is_bullish(opens[i], closes[i])
            and opens[i] < closes[i - 1]
            and closes[i] > prev_mid
            and closes[i] < opens[i - 1]
        ):
            results.append((i, "piercing_line", "刺透形态", "bullish", 0.75))
        # Dark cloud cover: prev bullish, curr bearish
        elif (
            _is_bullish(opens[i - 1], closes[i - 1])
            and _is_bearish(opens[i], closes[i])
            and opens[i] > closes[i - 1]
            and closes[i] < prev_mid
            and closes[i] > opens[i - 1]
        ):
            results.append((i, "dark_cloud_cover", "乌云盖顶", "bearish", 0.75))
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_ALL_DETECTORS = [
    _detect_doji,
    _detect_hammer,
    _detect_inverted_hammer,
    _detect_engulfing,
    _detect_morning_evening_star,
    _detect_three_soldiers_crows,
    _detect_marubozu,
    _detect_harami,
    _detect_piercing_dark_cloud,
]


def detect_patterns(
    df: pd.DataFrame,
    *,
    last_n: Optional[int] = None,
) -> list[PatternMatch]:
    """Run all pattern detectors on a DataFrame.

    Args:
        df: DataFrame with columns ``Date``, ``Open``, ``High``, ``Low``,
            ``Close`` (and optionally ``Volume``).
        last_n: If set, only scan the last *last_n* bars (but still use
            earlier bars for context like rolling averages).

    Returns:
        List of PatternMatch sorted by date descending (newest first).
    """
    if df.empty or len(df) < 3:
        return []

    opens = df["Open"].values.astype(np.float64)
    highs = df["High"].values.astype(np.float64)
    lows = df["Low"].values.astype(np.float64)
    closes = df["Close"].values.astype(np.float64)
    dates = df["Date"]

    avg_bodies = _avg_body(opens, closes, window=14)

    raw_results: list[tuple[int, str, str, str, float]] = []
    for detector in _ALL_DETECTORS:
        raw_results.extend(detector(opens, highs, lows, closes, avg_bodies))

    # Filter to last_n bars if requested
    min_idx = (len(df) - last_n) if last_n is not None else 0
    min_idx = max(min_idx, 0)

    matches = []
    for idx, name, label, sentiment, conf in raw_results:
        if idx < min_idx:
            continue
        dt = dates.iloc[idx]
        date_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)
        matches.append(PatternMatch(
            index=idx,
            date=date_str,
            name=name,
            label=label,
            sentiment=sentiment,
            confidence=conf,
        ))

    # Deduplicate: if multiple patterns on the same bar, keep the highest confidence
    seen: dict[int, PatternMatch] = {}
    for m in matches:
        key = m.index
        if key not in seen or m.confidence > seen[key].confidence:
            seen[key] = m

    result = sorted(seen.values(), key=lambda m: m.index, reverse=True)
    logger.info(
        "Detected {n} patterns in {total} bars (scanned last {scan})",
        n=len(result),
        total=len(df),
        scan=last_n or len(df),
    )
    return result
