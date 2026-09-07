"""Plain maths on price series. Every function returns None when there is not
enough history, so callers never work with a half formed number."""

from __future__ import annotations

import statistics


def pct_change(new: float, old: float) -> float | None:
    if old == 0:
        return None
    return (new - old) / old * 100.0


def change_over(closes: list[float], sessions: int) -> float | None:
    if len(closes) <= sessions:
        return None
    return pct_change(closes[-1], closes[-1 - sessions])


def sma(values: list[float], window: int) -> float | None:
    if window <= 0 or len(values) < window:
        return None
    return sum(values[-window:]) / window


def sma_series(values: list[float], window: int) -> list[float | None]:
    """Rolling average aligned to the input, with None where history is short."""
    if window <= 0:
        return [None] * len(values)
    output: list[float | None] = []
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= window:
            running -= values[index - window]
        output.append(running / window if index >= window - 1 else None)
    return output


def returns(closes: list[float]) -> list[float]:
    output = []
    for previous, current in zip(closes, closes[1:]):
        change = pct_change(current, previous)
        if change is not None:
            output.append(change)
    return output


def return_zscore(closes: list[float], window: int = 60) -> float | None:
    """How unusual the latest daily move is against its own recent history."""
    history = returns(closes)
    if len(history) < 20:
        return None
    latest = history[-1]
    baseline = history[-(window + 1) : -1] if len(history) > window else history[:-1]
    if len(baseline) < 15:
        return None
    spread = statistics.pstdev(baseline)
    if spread == 0:
        return None
    return (latest - statistics.fmean(baseline)) / spread


def rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's relative strength index. Above 70 is stretched, below 30 is washed out."""
    if len(closes) < period + 1:
        return None

    gains, losses = [], []
    for previous, current in zip(closes, closes[1:]):
        move = current - previous
        gains.append(max(move, 0.0))
        losses.append(max(-move, 0.0))

    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        average_gain = (average_gain * (period - 1) + gain) / period
        average_loss = (average_loss * (period - 1) + loss) / period

    if average_loss == 0:
        return 100.0
    strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + strength))


def volume_ratio(volumes: list[float], window: int = 20) -> float | None:
    """Latest volume against its recent average. Above 2 means unusual interest."""
    if len(volumes) < window + 1:
        return None
    baseline = volumes[-(window + 1) : -1]
    average = statistics.fmean(baseline)
    if average <= 0:
        return None
    return volumes[-1] / average


def range_position(value: float, low: float, high: float) -> float | None:
    """Where a price sits inside a range, from 0 at the low to 1 at the high."""
    if high <= low:
        return None
    return (value - low) / (high - low)


def drawdown_from_peak(closes: list[float], window: int = 60) -> float | None:
    """How far the latest price sits below its highest close in the window."""
    if len(closes) < 2:
        return None
    recent = closes[-window:] if len(closes) > window else closes
    peak = max(recent)
    if peak <= 0:
        return None
    return (closes[-1] - peak) / peak * 100.0


def crossover(fast: list[float | None], slow: list[float | None], within: int = 3) -> str | None:
    """Detect a fast line crossing a slow line in the last few sessions.

    Returns "up", "down", or None.
    """
    pairs = [(f, s) for f, s in zip(fast, slow) if f is not None and s is not None]
    if len(pairs) < within + 1:
        return None

    window = pairs[-(within + 1) :]
    start_above = window[0][0] > window[0][1]
    end_above = window[-1][0] > window[-1][1]
    if start_above == end_above:
        return None
    return "up" if end_above else "down"
