import unittest

from watchtower import indicators


class TestBasicMaths(unittest.TestCase):
    def test_pct_change(self):
        self.assertAlmostEqual(indicators.pct_change(110, 100), 10.0)
        self.assertAlmostEqual(indicators.pct_change(90, 100), -10.0)
        self.assertIsNone(indicators.pct_change(10, 0))

    def test_change_over_needs_enough_history(self):
        self.assertIsNone(indicators.change_over([100, 101], 5))
        self.assertAlmostEqual(indicators.change_over([100, 101, 102, 103, 104, 105, 110], 5), 8.910891, places=5)

    def test_sma(self):
        self.assertEqual(indicators.sma([1, 2, 3, 4], 2), 3.5)
        self.assertIsNone(indicators.sma([1, 2], 5))

    def test_sma_series_alignment(self):
        result = indicators.sma_series([1, 2, 3, 4, 5], 3)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[:2], [None, None])
        self.assertAlmostEqual(result[2], 2.0)
        self.assertAlmostEqual(result[4], 4.0)


class TestMomentum(unittest.TestCase):
    def test_rsi_extremes(self):
        rising = [float(value) for value in range(100, 130)]
        falling = list(reversed(rising))
        self.assertEqual(indicators.rsi(rising), 100.0)
        self.assertAlmostEqual(indicators.rsi(falling), 0.0)

    def test_rsi_needs_enough_history(self):
        self.assertIsNone(indicators.rsi([100, 101, 102]))

    def test_rsi_midrange_for_choppy_prices(self):
        closes = [100 + (1 if index % 2 else -1) for index in range(40)]
        value = indicators.rsi(closes)
        self.assertGreater(value, 30)
        self.assertLess(value, 70)

    def test_return_zscore_flags_an_unusual_day(self):
        closes = [100.0]
        for _ in range(60):
            closes.append(closes[-1] * 1.001)
        closes.append(closes[-1] * 1.08)
        self.assertGreater(indicators.return_zscore(closes), 3.0)

    def test_return_zscore_is_none_without_variation(self):
        self.assertIsNone(indicators.return_zscore([100.0] * 40))


class TestContext(unittest.TestCase):
    def test_volume_ratio(self):
        volumes = [100.0] * 20 + [300.0]
        self.assertAlmostEqual(indicators.volume_ratio(volumes), 3.0)

    def test_volume_ratio_needs_a_baseline(self):
        self.assertIsNone(indicators.volume_ratio([100.0, 200.0]))

    def test_range_position(self):
        self.assertAlmostEqual(indicators.range_position(50, 0, 100), 0.5)
        self.assertIsNone(indicators.range_position(50, 100, 100))

    def test_drawdown_from_peak(self):
        closes = [100.0, 120.0, 90.0]
        self.assertAlmostEqual(indicators.drawdown_from_peak(closes), -25.0)

    def test_no_drawdown_at_a_new_high(self):
        self.assertAlmostEqual(indicators.drawdown_from_peak([100.0, 110.0]), 0.0)


class TestCrossover(unittest.TestCase):
    def test_upward_cross(self):
        fast = [None, 1.0, 2.0, 3.0, 6.0]
        slow = [None, 5.0, 5.0, 5.0, 5.0]
        self.assertEqual(indicators.crossover(fast, slow), "up")

    def test_downward_cross(self):
        fast = [9.0, 8.0, 7.0, 4.0]
        slow = [5.0, 5.0, 5.0, 5.0]
        self.assertEqual(indicators.crossover(fast, slow), "down")

    def test_no_cross(self):
        fast = [6.0, 7.0, 8.0, 9.0]
        slow = [5.0, 5.0, 5.0, 5.0]
        self.assertIsNone(indicators.crossover(fast, slow))

    def test_ignores_a_cross_outside_the_window(self):
        fast = [1.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        slow = [5.0] * 6
        self.assertIsNone(indicators.crossover(fast, slow, within=2))


if __name__ == "__main__":
    unittest.main()
