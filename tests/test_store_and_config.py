import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from watchtower.config import ConfigError, load_config
from watchtower.datafeed import Bar
from watchtower.store import Store

VALID_CONFIG = """
[settings]
cooldown_days = 5

[thresholds]
move_pct = 3.5

[[holdings]]
symbol = "GC=F"
label = "Gold"
alert_below = 4000.0

[[holdings]]
symbol = "GLD"
"""


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.addCleanup(self._temp.cleanup)

    def write_config(self, text: str) -> Path:
        path = self.root / "watchlist.toml"
        path.write_text(text, encoding="utf-8")
        return path


class TestConfig(TempDirTest):
    def test_reads_settings_thresholds_and_holdings(self):
        config = load_config(self.write_config(VALID_CONFIG))

        self.assertEqual(config.settings.cooldown_days, 5)
        self.assertEqual(config.settings.lookback_days, 400)
        self.assertEqual(config.thresholds.move_pct, 3.5)
        self.assertEqual([holding.symbol for holding in config.holdings], ["GC=F", "GLD"])
        self.assertEqual(config.holdings[0].alert_below, 4000.0)
        self.assertEqual(config.holdings[1].display, "GLD")

    def test_missing_file(self):
        with self.assertRaisesRegex(ConfigError, "not found"):
            load_config(self.root / "nope.toml")

    def test_duplicate_symbol(self):
        text = '[[holdings]]\nsymbol = "GLD"\n\n[[holdings]]\nsymbol = "GLD"\n'
        with self.assertRaisesRegex(ConfigError, "listed twice"):
            load_config(self.write_config(text))

    def test_no_holdings(self):
        with self.assertRaisesRegex(ConfigError, "no holdings"):
            load_config(self.write_config("[settings]\nnews = false\n"))

    def test_unknown_option_is_caught_early(self):
        text = '[settings]\nmispelled = 3\n\n[[holdings]]\nsymbol = "GLD"\n'
        with self.assertRaisesRegex(ConfigError, "unknown option"):
            load_config(self.write_config(text))

    def test_bad_toml(self):
        with self.assertRaisesRegex(ConfigError, "not valid TOML"):
            load_config(self.write_config("[settings\n"))


class TestStore(TempDirTest):
    def setUp(self):
        super().setUp()
        self.store = Store(self.root / "data" / "test.db")
        self.addCleanup(self.store.close)

    def bars(self, count: int) -> list[Bar]:
        return [
            Bar(f"2026-01-{index + 1:02d}", 10.0, 11.0, 9.0, 10.0 + index, 100.0)
            for index in range(count)
        ]

    def test_bars_round_trip(self):
        self.store.save_bars("GLD", self.bars(3))
        stored = self.store.load_bars("GLD")

        self.assertEqual(len(stored), 3)
        self.assertEqual(stored[0].date, "2026-01-01")
        self.assertEqual(stored[-1].close, 12.0)

    def test_saving_the_same_day_twice_does_not_duplicate(self):
        self.store.save_bars("GLD", self.bars(3))
        self.store.save_bars("GLD", self.bars(3))
        self.assertEqual(len(self.store.load_bars("GLD")), 3)

    def test_load_bars_limit_returns_the_most_recent(self):
        self.store.save_bars("GLD", self.bars(10))
        recent = self.store.load_bars("GLD", limit=2)
        self.assertEqual([bar.date for bar in recent], ["2026-01-09", "2026-01-10"])

    def test_tracked_symbols(self):
        self.store.save_bars("GLD", self.bars(1))
        self.store.save_bars("SLV", self.bars(1))
        self.assertEqual(self.store.tracked_symbols(), ["GLD", "SLV"])

    def test_cooldown_suppresses_a_repeat_alert(self):
        self.store.record_alert("GLD", "big_move", "high", "Moved down 4%")
        self.assertTrue(self.store.alert_is_on_cooldown("GLD", "big_move", 3))

    def test_cooldown_expires(self):
        long_ago = date.today() - timedelta(days=10)
        self.store.record_alert("GLD", "big_move", "high", "Moved down 4%", today=long_ago)
        self.assertFalse(self.store.alert_is_on_cooldown("GLD", "big_move", 3))

    def test_cooldown_is_per_rule_and_per_symbol(self):
        self.store.record_alert("GLD", "big_move", "high", "Moved down 4%")
        self.assertFalse(self.store.alert_is_on_cooldown("GLD", "drawdown", 3))
        self.assertFalse(self.store.alert_is_on_cooldown("SLV", "big_move", 3))

    def test_zero_cooldown_never_suppresses(self):
        self.store.record_alert("GLD", "big_move", "high", "Moved down 4%")
        self.assertFalse(self.store.alert_is_on_cooldown("GLD", "big_move", 0))

    def test_recent_alerts(self):
        self.store.record_alert("GLD", "big_move", "high", "Moved down 4%")
        rows = self.store.recent_alerts()
        self.assertEqual(rows[0]["symbol"], "GLD")
        self.assertEqual(rows[0]["headline"], "Moved down 4%")


if __name__ == "__main__":
    unittest.main()
