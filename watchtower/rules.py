"""Turning price history into a snapshot, and the snapshot into alerts.

Every rule describes something that has already happened. None of them
forecast a price or suggest a trade.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import indicators
from .config import Holding, Thresholds
from .datafeed import Series

SEVERITY_ORDER = {"high": 0, "medium": 1, "info": 2}
WEEK_52_SESSIONS = 252


@dataclass(frozen=True)
class Snapshot:
    symbol: str
    label: str
    currency: str
    date: str
    price: float
    sessions: int
    change_1d: float | None = None
    change_5d: float | None = None
    change_20d: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    trend_cross: str | None = None
    rsi14: float | None = None
    volume_ratio: float | None = None
    return_z: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    range_position: float | None = None
    drawdown: float | None = None
    volume_is_comparable: bool = True


@dataclass(frozen=True)
class Alert:
    symbol: str
    label: str
    rule: str
    severity: str
    headline: str
    detail: str


def build_snapshot(series: Series, drawdown_window: int = 60) -> Snapshot:
    closes = series.closes
    latest = series.latest

    window = series.bars[-WEEK_52_SESSIONS:]
    high_52w = max(bar.high for bar in window)
    low_52w = min(bar.low for bar in window)

    return Snapshot(
        symbol=series.symbol,
        label=series.label,
        currency=series.currency,
        date=latest.date,
        price=latest.close,
        sessions=len(closes),
        change_1d=indicators.change_over(closes, 1),
        change_5d=indicators.change_over(closes, 5),
        change_20d=indicators.change_over(closes, 20),
        sma50=indicators.sma(closes, 50),
        sma200=indicators.sma(closes, 200),
        trend_cross=indicators.crossover(
            indicators.sma_series(closes, 50), indicators.sma_series(closes, 200)
        ),
        rsi14=indicators.rsi(closes),
        volume_ratio=(
            indicators.volume_ratio(series.volumes) if series.volume_is_comparable else None
        ),
        volume_is_comparable=series.volume_is_comparable,
        return_z=indicators.return_zscore(closes),
        high_52w=high_52w,
        low_52w=low_52w,
        range_position=indicators.range_position(latest.close, low_52w, high_52w),
        drawdown=indicators.drawdown_from_peak(closes, drawdown_window),
    )


def evaluate(snapshot: Snapshot, thresholds: Thresholds, holding: Holding | None = None) -> list[Alert]:
    """Run every rule and return the alerts that fired, most serious first."""
    found = [
        _big_move(snapshot, thresholds),
        _volume_spike(snapshot, thresholds),
        _trend_cross(snapshot),
        _range_extreme(snapshot, thresholds),
        _stretched(snapshot, thresholds),
        _drawdown(snapshot, thresholds),
        _level_break(snapshot, holding),
    ]
    alerts = [alert for alert in found if alert is not None]
    return sorted(alerts, key=lambda alert: SEVERITY_ORDER[alert.severity])


def _alert(snapshot: Snapshot, rule: str, severity: str, headline: str, detail: str) -> Alert:
    return Alert(snapshot.symbol, snapshot.label, rule, severity, headline, detail)


def _big_move(snapshot: Snapshot, thresholds: Thresholds) -> Alert | None:
    change = snapshot.change_1d
    if change is None:
        return None

    unusual = snapshot.return_z is not None and abs(snapshot.return_z) >= thresholds.move_zscore
    if abs(change) < thresholds.move_pct and not unusual:
        return None

    direction = "up" if change > 0 else "down"
    severity = "high" if abs(change) >= thresholds.move_pct * 2 else "medium"
    detail = f"Closed at {snapshot.price:,.2f} on {snapshot.date}."
    if snapshot.return_z is not None:
        detail += f" That is {abs(snapshot.return_z):.1f} times its normal daily swing."
    return _alert(
        snapshot,
        "big_move",
        severity,
        f"Moved {direction} {abs(change):.2f}% in one session",
        detail,
    )


def _volume_spike(snapshot: Snapshot, thresholds: Thresholds) -> Alert | None:
    ratio = snapshot.volume_ratio
    if ratio is None or ratio < thresholds.volume_ratio:
        return None
    if snapshot.change_1d is None or abs(snapshot.change_1d) < 1.0:
        return None

    direction = "higher" if snapshot.change_1d > 0 else "lower"
    return _alert(
        snapshot,
        "volume_spike",
        "medium",
        f"Trading volume {ratio:.1f} times normal",
        f"Price went {direction} by {abs(snapshot.change_1d):.2f}% on heavy volume. "
        "Unusual volume usually means news, so it is worth a look.",
    )


def _trend_cross(snapshot: Snapshot) -> Alert | None:
    if snapshot.trend_cross is None or snapshot.sma50 is None or snapshot.sma200 is None:
        return None

    if snapshot.trend_cross == "up":
        headline = "50 day average crossed above the 200 day average"
        meaning = "The medium term trend has turned upward."
    else:
        headline = "50 day average crossed below the 200 day average"
        meaning = "The medium term trend has turned downward."

    return _alert(
        snapshot,
        "trend_cross",
        "medium",
        headline,
        f"{meaning} 50 day is {snapshot.sma50:,.2f} against 200 day at {snapshot.sma200:,.2f}.",
    )


def _range_extreme(snapshot: Snapshot, thresholds: Thresholds) -> Alert | None:
    if snapshot.high_52w is None or snapshot.low_52w is None:
        return None

    edge = thresholds.range_edge_pct
    from_high = indicators.pct_change(snapshot.price, snapshot.high_52w)
    from_low = indicators.pct_change(snapshot.price, snapshot.low_52w)

    if from_high is not None and from_high >= -edge:
        return _alert(
            snapshot,
            "near_52w_high",
            "medium",
            "Trading near its 52 week high",
            f"Price {snapshot.price:,.2f} against a 52 week high of {snapshot.high_52w:,.2f}.",
        )
    if from_low is not None and from_low <= edge:
        return _alert(
            snapshot,
            "near_52w_low",
            "medium",
            "Trading near its 52 week low",
            f"Price {snapshot.price:,.2f} against a 52 week low of {snapshot.low_52w:,.2f}.",
        )
    return None


def _stretched(snapshot: Snapshot, thresholds: Thresholds) -> Alert | None:
    value = snapshot.rsi14
    if value is None:
        return None

    if value >= thresholds.rsi_high:
        return _alert(
            snapshot,
            "rsi_high",
            "info",
            f"Momentum is stretched, RSI {value:.0f}",
            "The asset has been bought hard recently. Stretched can stay stretched, "
            "so this is context rather than a signal on its own.",
        )
    if value <= thresholds.rsi_low:
        return _alert(
            snapshot,
            "rsi_low",
            "info",
            f"Momentum is washed out, RSI {value:.0f}",
            "The asset has been sold hard recently. Weak can stay weak, "
            "so this is context rather than a signal on its own.",
        )
    return None


def _drawdown(snapshot: Snapshot, thresholds: Thresholds) -> Alert | None:
    value = snapshot.drawdown
    if value is None or value > -abs(thresholds.drawdown_pct):
        return None
    return _alert(
        snapshot,
        "drawdown",
        "high",
        f"Down {abs(value):.1f}% from its recent peak",
        f"Measured over the last {thresholds.drawdown_window} sessions. Price is now {snapshot.price:,.2f}.",
    )


def _level_break(snapshot: Snapshot, holding: Holding | None) -> Alert | None:
    if holding is None:
        return None

    if holding.alert_above is not None and snapshot.price >= holding.alert_above:
        return _alert(
            snapshot,
            "level_above",
            "high",
            f"Crossed above your level of {holding.alert_above:,.2f}",
            f"Price is {snapshot.price:,.2f}. This is the level you set in the watchlist.",
        )
    if holding.alert_below is not None and snapshot.price <= holding.alert_below:
        return _alert(
            snapshot,
            "level_below",
            "high",
            f"Dropped below your level of {holding.alert_below:,.2f}",
            f"Price is {snapshot.price:,.2f}. This is the level you set in the watchlist.",
        )
    return None
