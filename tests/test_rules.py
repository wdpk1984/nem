import unittest
from dataclasses import replace

from watchtower.config import Holding, Thresholds
from watchtower.datafeed import Bar, Series
from watchtower.rules import Snapshot, build_snapshot, evaluate

THRESHOLDS = Thresholds()


def make_series(closes, volumes=None, instrument_type="ETF"):
    volumes = volumes or [1000.0] * len(closes)
    bars = [
        Bar(
            date=f"2026-01-{index + 1:02d}",
            open=close,
            high=close * 1.01,
            low=close * 0.99,
            close=close,
            volume=volume,
        )
        for index, (close, volume) in enumerate(zip(closes, volumes))
    ]
    return Series(symbol="TEST", label="Test Asset", currency="USD", bars=bars, instrument_type=instrument_type)


def make_snapshot(**overrides) -> Snapshot:
    base = dict(
        symbol="TEST",
        label="Test Asset",
        currency="USD",
        date="2026-01-30",
        price=100.0,
        sessions=200,
        change_1d=0.1,
        rsi14=50.0,
        high_52w=150.0,
        low_52w=50.0,
    )
    base.update(overrides)
    return Snapshot(**base)


class TestBuildSnapshot(unittest.TestCase):
    def test_fields_come_out_of_the_price_history(self):
        closes = [100.0] * 30 + [110.0]
        snapshot = build_snapshot(make_series(closes))

        self.assertEqual(snapshot.symbol, "TEST")
        self.assertEqual(snapshot.price, 110.0)
        self.assertEqual(snapshot.sessions, 31)
        self.assertAlmostEqual(snapshot.change_1d, 10.0)
        self.assertIsNone(snapshot.sma50)

    def test_volume_is_ignored_for_futures(self):
        closes = [100.0] * 30
        volumes = [100.0] * 29 + [9000.0]

        fund = build_snapshot(make_series(closes, volumes, instrument_type="ETF"))
        future = build_snapshot(make_series(closes, volumes, instrument_type="FUTURE"))

        self.assertIsNotNone(fund.volume_ratio)
        self.assertIsNone(future.volume_ratio)
        self.assertFalse(future.volume_is_comparable)


class TestRules(unittest.TestCase):
    def rules_fired(self, snapshot, holding=None):
        return {alert.rule for alert in evaluate(snapshot, THRESHOLDS, holding)}

    def test_calm_market_produces_nothing(self):
        self.assertEqual(self.rules_fired(make_snapshot()), set())

    def test_big_move_fires_on_a_large_daily_change(self):
        self.assertIn("big_move", self.rules_fired(make_snapshot(change_1d=-3.5)))

    def test_big_move_fires_when_a_small_move_is_unusual_for_the_asset(self):
        snapshot = make_snapshot(change_1d=0.9, return_z=3.1)
        self.assertIn("big_move", self.rules_fired(snapshot))

    def test_big_move_severity_scales(self):
        medium = evaluate(make_snapshot(change_1d=2.5), THRESHOLDS)[0]
        high = evaluate(make_snapshot(change_1d=-6.0), THRESHOLDS)[0]
        self.assertEqual(medium.severity, "medium")
        self.assertEqual(high.severity, "high")

    def test_volume_spike_needs_a_price_move_alongside_it(self):
        quiet_price = make_snapshot(change_1d=0.2, volume_ratio=5.0)
        with_move = make_snapshot(change_1d=1.5, volume_ratio=5.0)
        self.assertNotIn("volume_spike", self.rules_fired(quiet_price))
        self.assertIn("volume_spike", self.rules_fired(with_move))

    def test_trend_cross(self):
        snapshot = make_snapshot(trend_cross="up", sma50=105.0, sma200=100.0)
        alerts = evaluate(snapshot, THRESHOLDS)
        self.assertIn("trend_cross", {alert.rule for alert in alerts})

    def test_trend_cross_needs_both_averages(self):
        snapshot = make_snapshot(trend_cross="up", sma50=105.0, sma200=None)
        self.assertNotIn("trend_cross", self.rules_fired(snapshot))

    def test_near_52_week_high_and_low(self):
        self.assertIn("near_52w_high", self.rules_fired(make_snapshot(price=149.0)))
        self.assertIn("near_52w_low", self.rules_fired(make_snapshot(price=50.5)))

    def test_stretched_momentum_is_information_only(self):
        alerts = evaluate(make_snapshot(rsi14=78.0), THRESHOLDS)
        stretched = [alert for alert in alerts if alert.rule == "rsi_high"]
        self.assertEqual(stretched[0].severity, "info")

    def test_drawdown(self):
        self.assertIn("drawdown", self.rules_fired(make_snapshot(drawdown=-14.0)))
        self.assertNotIn("drawdown", self.rules_fired(make_snapshot(drawdown=-4.0)))

    def test_user_price_levels(self):
        above = Holding(symbol="TEST", alert_above=120.0)
        below = Holding(symbol="TEST", alert_below=90.0)

        self.assertIn("level_above", self.rules_fired(make_snapshot(price=125.0), above))
        self.assertNotIn("level_above", self.rules_fired(make_snapshot(price=110.0), above))
        self.assertIn("level_below", self.rules_fired(make_snapshot(price=85.0), below))

    def test_alerts_come_back_most_serious_first(self):
        snapshot = make_snapshot(change_1d=-6.0, rsi14=25.0, drawdown=-20.0)
        severities = [alert.severity for alert in evaluate(snapshot, THRESHOLDS)]
        self.assertEqual(severities, sorted(severities, key=["high", "medium", "info"].index))

    def test_missing_data_never_raises(self):
        empty = replace(make_snapshot(), change_1d=None, rsi14=None, high_52w=None, low_52w=None)
        self.assertEqual(evaluate(empty, THRESHOLDS), [])


if __name__ == "__main__":
    unittest.main()
