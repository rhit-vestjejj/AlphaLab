"""Integration tests for CLI command flow."""

from __future__ import annotations

import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from typer.testing import CliRunner

from alphalab.cli import app


def _mock_fetch_ohlcv(self: object, symbol: str, start: str, end: str) -> pd.DataFrame:
    """Deterministic mock fetcher used in CLI integration tests."""
    _ = self
    index = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    if index.empty:
        empty_index = pd.DatetimeIndex([], tz="UTC", name="date")
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"], index=empty_index)

    symbol_offset = {"ES": 100.0, "CL": 70.0, "GC": 140.0}.get(symbol, 50.0)
    close = pd.Series(range(len(index)), index=index, dtype=float) + symbol_offset
    frame = pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000.0,
        },
        index=index,
    )
    frame.index.name = "date"
    return frame


class TestCliIntegration(unittest.TestCase):
    """Validate end-to-end CLI workflow with experiment tracking."""

    def test_run_list_show_and_robustness_flow(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir = root / "cache"
            artifacts_dir = root / "artifacts"
            db_path = root / "experiments.sqlite"
            config_path = root / "config.yaml"

            config_path.write_text(
                textwrap.dedent(f"""
                    data:
                      provider: eodhd
                      symbols: [ES]
                      start: "2020-01-01"
                      end: "2020-01-10"
                      cache_dir: {cache_dir}
                    strategy:
                      module: alphalab.strategies.examples.trend_following
                      params:
                        lookback: 3
                    backtest:
                      transaction_cost_bps: 5.0
                      leverage_cap: 1.0
                      max_position: 1.0
                      annualization_factor: 252
                    output:
                      artifacts_dir: {artifacts_dir}
                      save_equity_plot: true
                      equity_plot_filename: equity_curve.png
                    robustness:
                      walk_forward_splits: 2
                      parameter_grid:
                        lookback: [2, 3]
                      cost_stress_bps: [0, 5]
                      volatility_window: 3
                      trend_window: 4
                    experiments:
                      db_path: {db_path}
                      tags: [integration]
                    """).strip() + "\n",
                encoding="utf-8",
            )

            with (
                patch.dict(os.environ, {"EODHD_API_KEY": "test_key"}, clear=False),
                patch(
                    "alphalab.core.data.eodhd_provider.EODHDProvider.fetch_ohlcv",
                    new=_mock_fetch_ohlcv,
                ),
            ):
                run_result = runner.invoke(app, ["run", "--config", str(config_path)])
                self.assertEqual(run_result.exit_code, 0, msg=run_result.output)
                experiment_line = next(
                    line
                    for line in run_result.output.splitlines()
                    if line.startswith("experiment_id=")
                )
                experiment_id = experiment_line.split("=", 1)[1].strip()
                self.assertTrue(experiment_id)

                list_result = runner.invoke(app, ["list", "--db-path", str(db_path)])
                self.assertEqual(list_result.exit_code, 0, msg=list_result.output)
                self.assertIn(experiment_id, list_result.output)

                show_result = runner.invoke(
                    app, ["show", "--experiment", experiment_id, "--db-path", str(db_path)]
                )
                self.assertEqual(show_result.exit_code, 0, msg=show_result.output)
                self.assertIn("config_yaml:", show_result.output)
                self.assertIn("metrics:", show_result.output)

                robustness_result = runner.invoke(
                    app, ["robustness", "--experiment", experiment_id, "--db-path", str(db_path)]
                )
                self.assertEqual(robustness_result.exit_code, 0, msg=robustness_result.output)
                report_line = next(
                    line
                    for line in robustness_result.output.splitlines()
                    if line.startswith("report=")
                )
                report_path = Path(report_line.split("=", 1)[1].strip())
                self.assertTrue(report_path.exists())

                show_after_robustness = runner.invoke(
                    app, ["show", "--experiment", experiment_id, "--db-path", str(db_path)]
                )
                self.assertEqual(
                    show_after_robustness.exit_code, 0, msg=show_after_robustness.output
                )
                self.assertIn("robustness_report.md", show_after_robustness.output)


if __name__ == "__main__":
    unittest.main()
