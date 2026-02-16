"""Integration tests for AlphaLab FastAPI endpoints."""

from __future__ import annotations

import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import pandas as pd

from alphalab.api.app import create_app


def _mock_fetch_ohlcv(self: object, symbol: str, start: str, end: str) -> pd.DataFrame:
    """Deterministic mock fetcher used in API integration tests."""
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


class TestApiIntegration(unittest.IsolatedAsyncioTestCase):
    """Validate API health and experiment workflows."""

    async def test_health(self) -> None:
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/health")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["service"], "alphalab-api")

    async def test_run_list_and_show_workflow(self) -> None:
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
                      tags: [api]
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
                app = create_app()
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                ) as client:
                    run_response = await client.post(
                        "/runs",
                        json={
                            "config_path": str(config_path),
                            "db_path": str(db_path),
                        },
                    )
                    self.assertEqual(run_response.status_code, 200, msg=run_response.text)
                    run_payload = run_response.json()
                    experiment_id = run_payload["experiment_id"]
                    self.assertTrue(experiment_id)
                    self.assertEqual(run_payload["strategy_name"], "trend_following")
                    self.assertEqual(run_payload["symbols"], ["ES"])

                    list_response = await client.get(
                        "/experiments",
                        params={"db_path": str(db_path)},
                    )
                    self.assertEqual(list_response.status_code, 200, msg=list_response.text)
                    list_payload = list_response.json()
                    self.assertTrue(list_payload)
                    listed_ids = [row["experiment_id"] for row in list_payload]
                    self.assertIn(experiment_id, listed_ids)

                    detail_response = await client.get(
                        f"/experiments/{experiment_id}",
                        params={"db_path": str(db_path)},
                    )
                    self.assertEqual(detail_response.status_code, 200, msg=detail_response.text)
                    detail_payload = detail_response.json()
                    self.assertEqual(detail_payload["experiment_id"], experiment_id)
                    self.assertIn("metrics", detail_payload)
                    self.assertIn("config_yaml", detail_payload)

    async def test_missing_experiment_returns_typed_404(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "experiments.sqlite"
            app = create_app()
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                response = await client.get(
                    "/experiments/exp_missing",
                    params={"db_path": str(db_path)},
                )
                self.assertEqual(response.status_code, 404, msg=response.text)
                payload = response.json()
                self.assertEqual(payload["error_code"], "experiment_store_error")


if __name__ == "__main__":
    unittest.main()
