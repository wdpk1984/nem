"""Daily price bars from the Yahoo Finance chart API. No API key required."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
USER_AGENT = "Mozilla/5.0 (compatible; watchtower/0.1)"


class FeedError(RuntimeError):
    """Raised when price data cannot be retrieved for a symbol."""


@dataclass(frozen=True)
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Series:
    symbol: str
    label: str
    currency: str
    bars: list[Bar]
    instrument_type: str = ""

    @property
    def volume_is_comparable(self) -> bool:
        """Futures history stitches together contracts that expire and roll over,
        so its volume column jumps for reasons that have nothing to do with the
        market. Volume rules are only meaningful on a continuous series."""
        return self.instrument_type.upper() != "FUTURE"

    @property
    def closes(self) -> list[float]:
        return [bar.close for bar in self.bars]

    @property
    def highs(self) -> list[float]:
        return [bar.high for bar in self.bars]

    @property
    def lows(self) -> list[float]:
        return [bar.low for bar in self.bars]

    @property
    def volumes(self) -> list[float]:
        return [bar.volume for bar in self.bars]

    @property
    def latest(self) -> Bar:
        return self.bars[-1]


def _request_json(url: str, timeout: float = 20.0, retries: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise FeedError("not recognised by the data provider, check the ticker") from error
            if error.code < 500:
                raise FeedError(f"data provider refused the request (HTTP {error.code})") from error
            last_error = error
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
            last_error = error

        if attempt < retries - 1:
            time.sleep(2**attempt)

    raise FeedError(f"could not reach the data provider ({last_error})")


def _yahoo_range(lookback_days: int) -> str:
    for days, label in ((5, "5d"), (30, "1mo"), (95, "3mo"), (185, "6mo"), (370, "1y"), (740, "2y")):
        if lookback_days <= days:
            return label
    return "5y"


def fetch_series(symbol: str, label: str = "", lookback_days: int = 400, timeout: float = 20.0) -> Series:
    """Fetch daily bars for one symbol, oldest first."""
    query = urllib.parse.urlencode({"range": _yahoo_range(lookback_days), "interval": "1d"})
    url = CHART_URL.format(symbol=urllib.parse.quote(symbol, safe="")) + "?" + query
    try:
        payload = _request_json(url, timeout=timeout)
    except FeedError as error:
        raise FeedError(f"{symbol}: {error}") from error

    chart = payload.get("chart") or {}
    error = chart.get("error")
    if error:
        raise FeedError(f"{symbol}: {error.get('description') or error}")

    results = chart.get("result") or []
    if not results:
        raise FeedError(f"{symbol}: no data returned, check the ticker is correct")

    result = results[0]
    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]

    bars = _build_bars(timestamps, quotes, int(meta.get("gmtoffset") or 0))
    if not bars:
        raise FeedError(f"{symbol}: price history came back empty")

    return Series(
        symbol=symbol,
        label=label or meta.get("shortName") or symbol,
        currency=meta.get("currency") or "",
        bars=bars,
        instrument_type=meta.get("instrumentType") or "",
    )


def _build_bars(timestamps: list[int], quotes: dict, gmt_offset: int) -> list[Bar]:
    opens = quotes.get("open") or []
    highs = quotes.get("high") or []
    lows = quotes.get("low") or []
    closes = quotes.get("close") or []
    volumes = quotes.get("volume") or []

    bars: list[Bar] = []
    for index, stamp in enumerate(timestamps):
        close = _value_at(closes, index)
        if close is None:
            continue
        local_time = datetime.fromtimestamp(stamp, tz=timezone.utc) + timedelta(seconds=gmt_offset)
        bars.append(
            Bar(
                date=local_time.date().isoformat(),
                open=_value_at(opens, index, close),
                high=_value_at(highs, index, close),
                low=_value_at(lows, index, close),
                close=close,
                volume=_value_at(volumes, index, 0.0) or 0.0,
            )
        )
    return bars


def _value_at(values: list, index: int, fallback: float | None = None) -> float | None:
    if index < len(values) and values[index] is not None:
        return float(values[index])
    return fallback


def fetch_headlines(query: str, count: int = 3, timeout: float = 15.0) -> list[dict]:
    """Recent news headlines for a symbol or search term.

    News is context only, so a failure here never stops a monitoring run.
    """
    params = urllib.parse.urlencode({"q": query, "newsCount": count, "quotesCount": 0})
    try:
        payload = _request_json(f"{SEARCH_URL}?{params}", timeout=timeout, retries=1)
    except FeedError:
        return []

    headlines = []
    for item in (payload.get("news") or [])[:count]:
        published = item.get("providerPublishTime")
        headlines.append(
            {
                "title": item.get("title") or "",
                "publisher": item.get("publisher") or "",
                "link": item.get("link") or "",
                "published": (
                    datetime.fromtimestamp(published, tz=timezone.utc).strftime("%Y-%m-%d")
                    if published
                    else ""
                ),
            }
        )
    return headlines
