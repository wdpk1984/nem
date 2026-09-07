"""Watchlist configuration, read from a TOML file."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

DEFAULT_CONFIG_PATH = "watchlist.toml"


class ConfigError(RuntimeError):
    """Raised when the watchlist file is missing or malformed."""


@dataclass(frozen=True)
class Holding:
    symbol: str
    label: str = ""
    kind: str = ""
    news_query: str = ""
    alert_above: float | None = None
    alert_below: float | None = None

    @property
    def display(self) -> str:
        return self.label or self.symbol


@dataclass(frozen=True)
class Thresholds:
    move_pct: float = 2.0
    move_zscore: float = 2.5
    volume_ratio: float = 2.0
    rsi_high: float = 70.0
    rsi_low: float = 30.0
    range_edge_pct: float = 2.0
    drawdown_pct: float = 10.0
    drawdown_window: int = 60


@dataclass(frozen=True)
class Settings:
    lookback_days: int = 400
    cooldown_days: int = 3
    news: bool = True
    news_count: int = 2
    database: str = "data/watchtower.db"


@dataclass(frozen=True)
class Config:
    settings: Settings = field(default_factory=Settings)
    thresholds: Thresholds = field(default_factory=Thresholds)
    holdings: list[Holding] = field(default_factory=list)


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> Config:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(
            f"watchlist file not found at {config_path}. "
            "Point --config at your watchlist file, or create watchlist.toml in this folder."
        )

    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{config_path} is not valid TOML: {error}") from error

    holdings = _build_holdings(raw.get("holdings") or [], config_path)
    return Config(
        settings=_build(Settings, raw.get("settings") or {}, "settings"),
        thresholds=_build(Thresholds, raw.get("thresholds") or {}, "thresholds"),
        holdings=holdings,
    )


def _build_holdings(entries: list, config_path: Path) -> list[Holding]:
    if not entries:
        raise ConfigError(f"{config_path} has no holdings. Add at least one [[holdings]] entry.")

    holdings: list[Holding] = []
    seen: set[str] = set()
    for entry in entries:
        symbol = str(entry.get("symbol") or "").strip()
        if not symbol:
            raise ConfigError("every holding needs a symbol, for example symbol = \"GC=F\"")
        if symbol in seen:
            raise ConfigError(f"{symbol} is listed twice in the watchlist")
        seen.add(symbol)
        holdings.append(_build(Holding, entry, f"holding {symbol}"))
    return holdings


def _build(target, values: dict, where: str):
    known = {f.name for f in fields(target)}
    unknown = set(values) - known
    if unknown:
        raise ConfigError(f"unknown option(s) in {where}: {', '.join(sorted(unknown))}")
    return target(**values)
