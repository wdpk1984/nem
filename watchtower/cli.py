"""Command line entry point for Watchtower."""

from __future__ import annotations

import argparse
import sys

from .config import Config, ConfigError, DEFAULT_CONFIG_PATH, Holding, load_config
from .datafeed import FeedError, fetch_headlines, fetch_series
from .report import Result, render, render_json
from .rules import build_snapshot, evaluate
from .store import Store


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as error:
        print(f"Configuration problem: {error}", file=sys.stderr)
        return 2

    if args.command == "history":
        return _command_history(config, args)
    if args.command == "alerts":
        return _command_alerts(config, args)
    return _command_check(config, args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="watchtower",
        description="Monitor a personal investment watchlist and flag unusual moves early.",
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="path to the watchlist file")
    subparsers = parser.add_subparsers(dest="command")

    check = subparsers.add_parser("check", help="run one monitoring pass (default)")
    check.add_argument("--no-news", action="store_true", help="skip news headlines")
    check.add_argument("--all-alerts", action="store_true", help="ignore the repeat alert cooldown")
    check.add_argument("--quiet", action="store_true", help="print alerts only, no full table")
    check.add_argument("--json", action="store_true", help="print machine readable output")

    history = subparsers.add_parser("history", help="show stored price history for one symbol")
    history.add_argument("symbol")
    history.add_argument("--days", type=int, default=20, help="how many sessions to show")

    subparsers.add_parser("alerts", help="show alerts that fired in earlier runs")

    parser.set_defaults(command="check", no_news=False, all_alerts=False, quiet=False, json=False)
    return parser


def _command_check(config: Config, args: argparse.Namespace) -> int:
    settings = config.settings
    results: list[Result] = []
    problems: list[str] = []

    with Store(settings.database) as store:
        for holding in config.holdings:
            try:
                series = fetch_series(
                    holding.symbol, holding.display, lookback_days=settings.lookback_days
                )
            except FeedError as error:
                problems.append(str(error))
                continue

            store.save_bars(series.symbol, series.bars)
            snapshot = build_snapshot(series, config.thresholds.drawdown_window)
            alerts = evaluate(snapshot, config.thresholds, holding)

            fresh = []
            for alert in alerts:
                on_cooldown = store.alert_is_on_cooldown(
                    alert.symbol, alert.rule, settings.cooldown_days
                )
                if on_cooldown and not args.all_alerts:
                    continue
                store.record_alert(alert.symbol, alert.rule, alert.severity, alert.headline)
                fresh.append(alert)

            headlines = []
            if fresh and settings.news and not args.no_news:
                headlines = fetch_headlines(_news_query(holding), settings.news_count)

            results.append(Result(snapshot=snapshot, alerts=fresh, headlines=headlines))

    if args.json:
        print(render_json(results, problems))
    else:
        print(render(results, problems, quiet=args.quiet))

    if problems and not results:
        return 1
    return 0


def _news_query(holding: Holding) -> str:
    return holding.news_query or holding.symbol


def _command_history(config: Config, args: argparse.Namespace) -> int:
    with Store(config.settings.database) as store:
        bars = store.load_bars(args.symbol, limit=args.days)
        if not bars:
            known = ", ".join(store.tracked_symbols()) or "nothing yet"
            print(f"No stored history for {args.symbol}. Stored symbols: {known}")
            return 1

        print(f"{args.symbol}   last {len(bars)} sessions")
        print(f"  {'DATE':<12} {'CLOSE':>12} {'HIGH':>12} {'LOW':>12} {'VOLUME':>14}")
        for bar in bars:
            print(
                f"  {bar.date:<12} {bar.close:>12,.2f} {bar.high:>12,.2f} "
                f"{bar.low:>12,.2f} {bar.volume:>14,.0f}"
            )
    return 0


def _command_alerts(config: Config, args: argparse.Namespace) -> int:
    with Store(config.settings.database) as store:
        rows = store.recent_alerts()
        if not rows:
            print("No alerts recorded yet. Run a check first.")
            return 0
        print(f"  {'DATE':<12} {'SYMBOL':<10} {'LEVEL':<8} HEADLINE")
        for row in rows:
            print(
                f"  {row['fired_on']:<12} {row['symbol']:<10} "
                f"{row['severity']:<8} {row['headline']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
