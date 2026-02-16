"""Unit tests for fixed bps transaction cost behavior."""

from __future__ import annotations

import unittest

from alphalab.core.backtest.engine import run_backtest
from alphalab.tests.helpers import make_price_frame, strategy_from_positions


class TestCostModel(unittest.TestCase):
    """Validate transaction cost subtraction from returns."""

    def test_cost_deduction(self) -> None:
        frame = make_price_frame([100.0, 100.0, 100.0, 100.0])
        strategy = strategy_from_positions("cost_case", [0.0, 1.0, -1.0, -1.0])

        result = run_backtest(
            data_by_symbol={"ES": frame},
            strategy=strategy,
            strategy_params={},
            transaction_cost_bps=10.0,
            leverage_cap=1.0,
            max_position=1.0,
        )

        expected_returns = [0.0, -0.001, -0.002, 0.0]
        for observed, expected in zip(result.daily_returns.tolist(), expected_returns, strict=True):
            self.assertAlmostEqual(observed, expected, places=12)


if __name__ == "__main__":
    unittest.main()
