# Watchtower

A monitoring agent for a personal investment watchlist, built around gold and
the other commodities you follow. It checks your holdings on a schedule, works
out what normal looks like for each one, and tells you the moment something
steps outside that range.

## What it does, and what it does not do

Watchtower reports what has already happened and puts the context next to it,
so you see a move early and can decide quickly.

It does not predict prices. It does not tell you what to buy or sell, and it
never places a trade. Anything claiming to call the next move reliably is
selling a story. The value here is speed and attention, not prophecy. Every
decision stays with you.

## Quick start

No installation and no API key needed. It uses Python 3.11 or newer and the
standard library only.

```bash
python3 -m watchtower check
```

That reads `watchlist.toml`, pulls daily prices for everything on it, and
prints a report.

## What comes back

```
WATCHTOWER   2026-09-07 21:32 UTC   6 holdings   1 new alerts
==============================================================================

WHAT CHANGED

  [WATCH] S&P 500 (^GSPC)
          Trading near its 52 week high
          Price 7,718.60 against a 52 week high of 7,816.70.

          News: Could This Vanguard Growth ETF Be a No-Brainer Buy for
          Long-Term Investors? (Motley Fool 2026-09-07)

WATCHLIST

  SYMBOL     NAME                   AS OF              PRICE       1D       5D      20D   RSI   VS 50D  52W POS
  -------------------------------------------------------------------------------------------------------------
  SLV        Silver (iShares fund)  2026-09-04         59.82   -1.21%   -0.33%   +4.03%    53   +6.81%      31%
  GC=F       Gold (spot price)      2026-09-07      4,476.60   +1.06%   +1.03%   +2.63%    55   +5.41%      44%
```

## What gets flagged

| Alert | What it means |
| --- | --- |
| Big move | A one day move past your threshold, or a move well outside what is normal for that asset |
| Volume spike | Trading volume far above its recent average, alongside a real price move. This usually means news |
| Trend change | The 50 day average crossing the 200 day average, up or down |
| Near 52 week high or low | Price approaching the edge of its yearly range |
| Your own price level | Price crossing a level you set yourself |
| Drawdown | A fall from the recent peak past your threshold |
| Stretched momentum | RSI above 70 or below 30, marked as context only |

Alerts are graded HIGH, WATCH or INFO. Anything flagged also pulls two recent
news headlines, so you are never looking at a price move with no explanation.

The same alert will not repeat for the same holding within the cooldown period,
which is three days by default. That keeps a long running trend from filling
your report every single day.

## Adding your own holdings

Edit `watchlist.toml`. Each entry needs a Yahoo Finance ticker.

```toml
[[holdings]]
symbol = "GC=F"
label = "Gold (spot price)"
alert_above = 5000.0
alert_below = 4000.0
```

Set `alert_above` or `alert_below` and you get told as soon as your own level is
crossed. Useful ticker patterns are `GC=F` for a commodity future, `GLD` for a
fund, `AAPL` for a share, `^GSPC` for an index, `BTC-USD` for crypto and
`EURUSD=X` for a currency pair.

Thresholds live in the same file, so you can make the agent more or less
sensitive without touching any code.

## A note on commodity data

A futures ticker such as `GC=F` gives the gold price everyone quotes, but its
history is stitched together from contracts that expire and roll over. That
makes its volume column jump for reasons that have nothing to do with the
market, and it puts small kinks in the daily price history around each roll.

Watchtower detects futures automatically and switches volume rules off for
them, so you do not get false alarms. The default watchlist pairs each futures
price with its fund equivalent, such as `GLD` alongside `GC=F`. The future gives
you the headline price and the fund gives you clean volume and trading flow.

## Running it on a schedule

A daily check just after the US market closes works well. Add this to your
crontab with `crontab -e`:

```
0 22 * * 1-5 cd /path/to/nem && /usr/bin/python3 -m watchtower check >> watchtower.log 2>&1
```

## Commands

```bash
python3 -m watchtower check              # run one monitoring pass
python3 -m watchtower check --quiet      # alerts only, no full table
python3 -m watchtower check --json       # machine readable output
python3 -m watchtower check --all-alerts # ignore the repeat alert cooldown
python3 -m watchtower check --no-news    # skip headlines
python3 -m watchtower history GLD        # stored price history for one holding
python3 -m watchtower alerts             # alerts from earlier runs
```

Use `--config path/to/file.toml` to run more than one watchlist, for example a
long term portfolio and a shorter term list.

## How it is put together

| File | Job |
| --- | --- |
| `watchtower/datafeed.py` | Daily prices and news from the Yahoo Finance public API |
| `watchtower/store.py` | SQLite history and the record of alerts already sent |
| `watchtower/indicators.py` | The maths: averages, RSI, volume ratio, drawdown, range position |
| `watchtower/rules.py` | Turns the numbers into graded alerts |
| `watchtower/report.py` | Terminal and JSON output |
| `watchtower/cli.py` | Command line entry point |

Price history is cached in `data/watchtower.db`, so past data stays available
even when the feed is down.

## Tests

```bash
python3 -m unittest discover -s tests
```
