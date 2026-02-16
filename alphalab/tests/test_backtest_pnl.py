"""Unit tests for deterministic PnL behavior."""

from __future__ import annotations

import unittest

from alphalab.core.backtest.engine import run_backtest
from alphalab.tests.helpers import make_price_frame, strategy_from_positions


class TestBacktestPnL(unittest.TestCase):
    """Validate base PnL calculation with next-day close execution."""

    def test_pnl_without_costs(self) -> None:
        frame = make_price_frame([100.0, 110.0, 121.0])
        strategy = strategy_from_positions("constant_long", [1.0, 1.0, 1.0])

        result = run_backtest(
            data_by_symbol={"ES": frame},
            strategy=strategy,
            strategy_params={},
            transaction_cost_bps=0.0,
            leverage_cap=1.0,
            max_position=1.0,
        )

        expected_returns = [0.0, 0.1, 0.1]
        for observed, expected in zip(result.daily_returns.tolist(), expected_returns, strict=True):
            self.assertAlmostEqual(observed, expected, places=12)
        self.assertAlmostEqual(float(result.equity_curve.iloc[-1]), 1.21, places=12)


if __name__ == "__main__":
    unittest.main()
