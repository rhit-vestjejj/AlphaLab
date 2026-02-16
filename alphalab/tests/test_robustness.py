"""Unit tests for robustness suite outputs."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from alphalab.core.research.robustness import RobustnessSettings, run_robustness_suite
from alphalab.core.research.strategy import StrategyDefinition
from alphalab.core.utils.errors import RobustnessError
from alphalab.tests.helpers import make_price_frame


class TestRobustnessSuite(unittest.TestCase):
    """Validate deterministic robustness suite execution."""

    @staticmethod
    def _adaptive_strategy() -> StrategyDefinition:
        """Create a deterministic strategy that adapts to any split length."""

        def required_columns() -> list[str]:
            return ["close"]

        def generate_positions(df: pd.DataFrame, params: dict[str, object]) -> pd.Series:
            close = pd.to_numeric(df["close"], errors="coerce")
            momentum = close.pct_change().fillna(0.0)
            return momentum.apply(lambda value: 1.0 if value >= 0 else -1.0).astype(float)

        return StrategyDefinition(
            strategy_name="adaptive_test_strategy",
            required_columns=required_columns,
            generate_positions=generate_positions,
        )

    def test_robustness_outputs(self) -> None:
        frame = make_price_frame(
            [
                100.0,
                101.0,
                102.0,
                99.0,
                98.0,
                100.0,
                103.0,
                104.0,
                102.0,
                101.0,
                103.0,
                105.0,
            ]
        )
        strategy = self._adaptive_strategy()
        settings = RobustnessSettings(
            walk_forward_splits=3,
            parameter_grid={"lookback": [5, 10]},
            cost_stress_bps=[0.0, 5.0],
            volatility_window=3,
            trend_window=4,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = run_robustness_suite(
                experiment_id="exp_test",
                data_by_symbol={"ES": frame},
                strategy=strategy,
                strategy_params={"lookback": 5},
                transaction_cost_bps=5.0,
                leverage_cap=1.0,
                max_position=1.0,
                annualization_factor=252,
                settings=settings,
                output_dir=output_dir,
                save_plots=False,
            )

            self.assertEqual(len(result.walk_forward_results), 3)
            self.assertEqual(len(result.parameter_grid_results), 2)
            self.assertEqual(len(result.cost_stress_results), 2)
            self.assertEqual(len(result.regime_results), 4)
            self.assertTrue(result.report_path.exists())
            self.assertTrue(result.summary_json_path.exists())

            payload = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["experiment_id"], "exp_test")
            self.assertIn("aggregated_metrics", payload)
            self.assertIn("baseline_metrics", payload)

    def test_no_common_index_raises_typed_error(self) -> None:
        frame_es = make_price_frame([100.0, 101.0, 102.0, 103.0])
        frame_cl = make_price_frame([70.0, 69.0, 71.0, 72.0]).copy()
        frame_cl.index = frame_cl.index + pd.Timedelta(days=30)

        strategy = self._adaptive_strategy()
        settings = RobustnessSettings(
            walk_forward_splits=2,
            parameter_grid={"lookback": [3]},
            cost_stress_bps=[0.0],
            volatility_window=2,
            trend_window=2,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(RobustnessError):
                run_robustness_suite(
                    experiment_id="exp_no_common_index",
                    data_by_symbol={"CL": frame_cl, "ES": frame_es},
                    strategy=strategy,
                    strategy_params={"lookback": 3},
                    transaction_cost_bps=5.0,
                    leverage_cap=1.0,
                    max_position=1.0,
                    annualization_factor=252,
                    settings=settings,
                    output_dir=Path(temp_dir),
                    save_plots=False,
                )


if __name__ == "__main__":
    unittest.main()
