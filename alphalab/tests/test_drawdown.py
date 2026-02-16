"""Unit tests for drawdown metrics."""

from __future__ import annotations

import unittest

import pandas as pd

from alphalab.core.backtest.metrics import calculate_max_drawdown


class TestDrawdown(unittest.TestCase):
    """Validate max drawdown calculation."""

    def test_max_drawdown(self) -> None:
        index = pd.date_range("2020-01-01", periods=5, freq="D", tz="UTC")
        equity_curve = pd.Series([1.0, 1.1, 1.05, 1.2, 0.9], index=index, dtype=float)
        max_drawdown = calculate_max_drawdown(equity_curve)
        self.assertAlmostEqual(max_drawdown, -0.25, places=12)


if __name__ == "__main__":
    unittest.main()
