"""Terminal and JSON output for a monitoring run."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .rules import Alert, Snapshot

DISCLAIMER = (
    "Watchtower reports what has already happened in the market. It does not predict "
    "prices, it is not financial advice, and it never places a trade. Every buy and "
    "sell decision stays with you."
)

SEVERITY_LABEL = {"high": "HIGH", "medium": "WATCH", "info": "INFO"}
COLORS = {"high": "\033[1;31m", "medium": "\033[1;33m", "info": "\033[0;36m"}
RESET = "\033[0m"
DIM = "\033[2m"


@dataclass
class Result:
    snapshot: Snapshot
    alerts: list[Alert] = field(default_factory=list)
    headlines: list[dict] = field(default_factory=list)


def _use_color(stream) -> bool:
    return stream.isatty() and not os.environ.get("NO_COLOR")


def render(results: list[Result], problems: list[str], stream=None, quiet: bool = False) -> str:
    stream = stream or sys.stdout
    color = _use_color(stream)
    lines: list[str] = []

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    alerts_total = sum(len(result.alerts) for result in results)
    lines.append(f"WATCHTOWER   {stamp}   {len(results)} holdings   {alerts_total} new alerts")
    lines.append("=" * 78)

    lines.extend(_alert_section(results, color))
    if results and not quiet:
        lines.append("")
        lines.extend(_table_section(results))

    if problems:
        lines.append("")
        lines.append("COULD NOT CHECK")
        for problem in problems:
            lines.append(f"  {problem}")

    lines.append("")
    lines.append(_wrap(DISCLAIMER, prefix="  ", color=DIM if color else ""))
    return "\n".join(lines)


def _alert_section(results: list[Result], color: bool) -> list[str]:
    if not results:
        return ["", "  No holding could be checked on this run. See the reasons below.", ""]

    flagged = [result for result in results if result.alerts]
    if not flagged:
        return ["", "  Nothing unusual today. Every holding is inside its normal range.", ""]

    lines = ["", "WHAT CHANGED", ""]
    for result in flagged:
        snapshot = result.snapshot
        for alert in result.alerts:
            tag = SEVERITY_LABEL[alert.severity]
            opener = COLORS[alert.severity] if color else ""
            closer = RESET if color else ""
            lines.append(f"  {opener}[{tag:<5}]{closer} {snapshot.label} ({snapshot.symbol})")
            lines.append(f"          {alert.headline}")
            lines.append(_wrap(alert.detail, prefix="          "))
            lines.append("")

        for item in result.headlines:
            source = " ".join(part for part in (item["publisher"], item["published"]) if part)
            lines.append(_wrap(f"News: {item['title']} ({source})", prefix="          "))
        if result.headlines:
            lines.append("")
    return lines


def _table_section(results: list[Result]) -> list[str]:
    header = (
        f"  {'SYMBOL':<10} {'NAME':<22} {'AS OF':<11} {'PRICE':>12} {'1D':>8} "
        f"{'5D':>8} {'20D':>8} {'RSI':>5} {'VS 50D':>8} {'52W POS':>8}"
    )
    lines = ["WATCHLIST", "", header, "  " + "-" * len(header.strip())]

    for result in sorted(results, key=lambda item: abs(item.snapshot.change_1d or 0), reverse=True):
        snapshot = result.snapshot
        lines.append(
            f"  {snapshot.symbol:<10} {_clip(snapshot.label, 22):<22} {snapshot.date:<11} "
            f"{snapshot.price:>12,.2f} {_pct(snapshot.change_1d):>8} "
            f"{_pct(snapshot.change_5d):>8} {_pct(snapshot.change_20d):>8} "
            f"{_num(snapshot.rsi14, 0):>5} {_pct(_gap(snapshot.price, snapshot.sma50)):>8} "
            f"{_pos(snapshot.range_position):>8}"
        )
    return lines


def render_json(results: list[Result], problems: list[str]) -> str:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "disclaimer": DISCLAIMER,
        "holdings": [
            {
                "snapshot": asdict(result.snapshot),
                "alerts": [asdict(alert) for alert in result.alerts],
                "headlines": result.headlines,
            }
            for result in results
        ],
        "problems": problems,
    }
    return json.dumps(payload, indent=2)


def _gap(price: float, reference: float | None) -> float | None:
    if reference is None or reference == 0:
        return None
    return (price - reference) / reference * 100.0


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}%"


def _num(value: float | None, places: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{places}f}"


def _pos(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _clip(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _wrap(text: str, prefix: str = "", width: int = 78, color: str = "") -> str:
    words = text.split()
    lines: list[str] = []
    current = prefix
    for word in words:
        if len(current) + len(word) + 1 > width and current.strip():
            lines.append(current.rstrip())
            current = prefix + word + " "
        else:
            current += word + " "
    if current.strip():
        lines.append(current.rstrip())
    body = "\n".join(lines)
    return f"{color}{body}{RESET}" if color else body
