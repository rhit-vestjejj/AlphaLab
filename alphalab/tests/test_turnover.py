"""Unit tests for turnover statistics."""

from __future__ import annotations

import unittest

from alphalab.core.backtest.engine import run_backtest
from alphalab.tests.helpers import make_price_frame, strategy_from_positions


class TestTurnover(unittest.TestCase):
    """Validate turnover calculation from daily position changes."""

    def test_turnover_stats(self) -> None:
        frame = make_price_frame([100.0, 100.0, 100.0, 100.0])
        strategy = strategy_from_positions("turnover_case", [0.0, 1.0, -1.0, -1.0])

        result = run_backtest(
            data_by_symbol={"ES": frame},
            strategy=strategy,
            strategy_params={},
            transaction_cost_bps=0.0,
            leverage_cap=1.0,
            max_position=1.0,
        )

        self.assertAlmostEqual(result.turnover_stats["average_daily_turnover"], 0.75, places=12)
        self.assertAlmostEqual(result.turnover_stats["max_daily_turnover"], 2.0, places=12)


if __name__ == "__main__":
    unittest.main()
