"""SQLite storage for price history and for alerts that have already fired.

Keeping fired alerts on disk is what stops the agent repeating the same
message every time it runs.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from .datafeed import Bar

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    symbol TEXT NOT NULL,
    date   TEXT NOT NULL,
    open   REAL NOT NULL,
    high   REAL NOT NULL,
    low    REAL NOT NULL,
    close  REAL NOT NULL,
    volume REAL NOT NULL,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS alerts (
    symbol    TEXT NOT NULL,
    rule      TEXT NOT NULL,
    fired_on  TEXT NOT NULL,
    severity  TEXT NOT NULL,
    headline  TEXT NOT NULL,
    PRIMARY KEY (symbol, rule, fired_on)
);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        with self._connection:
            self._connection.executescript(SCHEMA)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def save_bars(self, symbol: str, bars: list[Bar]) -> int:
        rows = [(symbol, b.date, b.open, b.high, b.low, b.close, b.volume) for b in bars]
        with self._connection:
            self._connection.executemany(
                "INSERT OR REPLACE INTO bars VALUES (?, ?, ?, ?, ?, ?, ?)", rows
            )
        return len(rows)

    def load_bars(self, symbol: str, limit: int | None = None) -> list[Bar]:
        query = "SELECT * FROM bars WHERE symbol = ? ORDER BY date"
        with closing(self._connection.execute(query, (symbol,))) as cursor:
            rows = cursor.fetchall()
        if limit is not None:
            rows = rows[-limit:]
        return [
            Bar(r["date"], r["open"], r["high"], r["low"], r["close"], r["volume"]) for r in rows
        ]

    def tracked_symbols(self) -> list[str]:
        with closing(self._connection.execute("SELECT DISTINCT symbol FROM bars ORDER BY symbol")) as cursor:
            return [row["symbol"] for row in cursor.fetchall()]

    def alert_is_on_cooldown(self, symbol: str, rule: str, cooldown_days: int, today: date | None = None) -> bool:
        if cooldown_days <= 0:
            return False
        cutoff = ((today or date.today()) - timedelta(days=cooldown_days)).isoformat()
        query = "SELECT 1 FROM alerts WHERE symbol = ? AND rule = ? AND fired_on > ? LIMIT 1"
        with closing(self._connection.execute(query, (symbol, rule, cutoff))) as cursor:
            return cursor.fetchone() is not None

    def record_alert(self, symbol: str, rule: str, severity: str, headline: str, today: date | None = None) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO alerts VALUES (?, ?, ?, ?, ?)",
                (symbol, rule, (today or date.today()).isoformat(), severity, headline),
            )

    def recent_alerts(self, limit: int = 20) -> list[sqlite3.Row]:
        query = "SELECT * FROM alerts ORDER BY fired_on DESC, symbol LIMIT ?"
        with closing(self._connection.execute(query, (limit,))) as cursor:
            return cursor.fetchall()
