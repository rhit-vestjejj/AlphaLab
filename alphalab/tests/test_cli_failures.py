"""Integration tests for CLI typed failures and failure manifests."""

from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from typer.testing import CliRunner

from alphalab.cli import app


class TestCliFailures(unittest.TestCase):
    """Validate typed exit codes and failure manifest behavior."""

    def test_run_with_missing_config_returns_config_exit_code(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.yaml"
            result = runner.invoke(app, ["run", "--config", str(missing_path)])
            self.assertEqual(result.exit_code, 2, msg=result.output)

    def test_run_strategy_import_failure_writes_failed_manifest(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir = root / "cache"
            artifacts_dir = root / "artifacts"
            db_path = root / "experiments.sqlite"
            config_path = root / "invalid_strategy.yaml"

            config_path.write_text(
                textwrap.dedent(f"""
                    data:
                      provider: eodhd
                      symbols: [ES]
                      start: "2020-01-01"
                      end: "2020-01-05"
                      cache_dir: {cache_dir}
                    strategy:
                      module: alphalab.strategies.examples.does_not_exist
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
                      tags: [failure-test]
                    """).strip() + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(app, ["run", "--config", str(config_path)])
            self.assertEqual(result.exit_code, 6, msg=result.output)

            manifest_line = next(
                line for line in result.output.splitlines() if line.startswith("manifest=")
            )
            manifest_path = Path(manifest_line.split("=", 1)[1].strip())
            self.assertTrue(manifest_path.exists())

            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["command"], "run")
            self.assertEqual(
                payload["failure"]["exception_type"],
                "StrategyError",
            )
            self.assertEqual(payload["inputs"]["config_path"], str(config_path.resolve()))

    def test_show_missing_experiment_returns_store_exit_code(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "experiments.sqlite"
            result = runner.invoke(
                app,
                ["show", "--experiment", "exp_missing", "--db-path", str(db_path)],
            )
            self.assertEqual(result.exit_code, 8, msg=result.output)


if __name__ == "__main__":
    unittest.main()
