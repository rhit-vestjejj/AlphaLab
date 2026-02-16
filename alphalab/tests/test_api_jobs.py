"""Integration tests for API background job queue endpoints."""

from __future__ import annotations

import asyncio
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


async def _poll_job_result(
    client: httpx.AsyncClient,
    job_id: str,
    timeout_seconds: float = 15.0,
) -> dict[str, object]:
    """Poll a job endpoint until completion or timeout."""
    max_polls = max(1, int(timeout_seconds / 0.05))
    for _ in range(max_polls):
        response = await client.get(f"/jobs/{job_id}")
        if response.status_code != 200:
            raise AssertionError(
                f"Unexpected job status response: {response.status_code} {response.text}"
            )
        payload = response.json()
        if payload["status"] in {"succeeded", "failed"}:
            return payload
        await asyncio.sleep(0.05)
    raise AssertionError(f"Timed out waiting for job completion: {job_id}")


class TestApiJobs(unittest.IsolatedAsyncioTestCase):
    """Validate API background queue behavior for run and robustness jobs."""

    @staticmethod
    def _write_config(
        config_path: Path, cache_dir: Path, artifacts_dir: Path, db_path: Path
    ) -> None:
        """Write deterministic API test config to disk."""
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
                  tags: [jobs]
                """).strip() + "\n",
            encoding="utf-8",
        )

    async def test_run_and_robustness_jobs_succeed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir = root / "cache"
            artifacts_dir = root / "artifacts"
            db_path = root / "experiments.sqlite"
            config_path = root / "config.yaml"
            self._write_config(config_path, cache_dir, artifacts_dir, db_path)

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
                    run_enqueue = await client.post(
                        "/jobs/runs",
                        json={"config_path": str(config_path), "db_path": str(db_path)},
                    )
                    self.assertEqual(run_enqueue.status_code, 202, msg=run_enqueue.text)
                    run_job = run_enqueue.json()
                    self.assertEqual(run_job["job_type"], "run")
                    run_final = await _poll_job_result(client, run_job["job_id"])
                    self.assertEqual(run_final["status"], "succeeded")
                    run_result = run_final.get("result") or {}
                    experiment_id = run_result.get("experiment_id")
                    self.assertIsInstance(experiment_id, str)
                    self.assertTrue(experiment_id)

                    robustness_enqueue = await client.post(
                        "/jobs/robustness",
                        json={"experiment_id": experiment_id, "db_path": str(db_path)},
                    )
                    self.assertEqual(
                        robustness_enqueue.status_code, 202, msg=robustness_enqueue.text
                    )
                    robustness_job = robustness_enqueue.json()
                    self.assertEqual(robustness_job["job_type"], "robustness")
                    robustness_final = await _poll_job_result(client, robustness_job["job_id"])
                    self.assertEqual(robustness_final["status"], "succeeded")
                    robustness_result = robustness_final.get("result") or {}
                    self.assertIn("report_path", robustness_result)
                    self.assertIn("summary_json_path", robustness_result)

                    jobs_list = await client.get("/jobs", params={"limit": 10})
                    self.assertEqual(jobs_list.status_code, 200, msg=jobs_list.text)
                    job_ids = [item["job_id"] for item in jobs_list.json()]
                    self.assertIn(run_job["job_id"], job_ids)
                    self.assertIn(robustness_job["job_id"], job_ids)

    async def test_run_job_failure_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "experiments.sqlite"
            missing_config = Path(temp_dir) / "missing.yaml"

            app = create_app()
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                enqueue = await client.post(
                    "/jobs/runs",
                    json={"config_path": str(missing_config), "db_path": str(db_path)},
                )
                self.assertEqual(enqueue.status_code, 202, msg=enqueue.text)
                job_id = enqueue.json()["job_id"]

                final_payload = await _poll_job_result(client, job_id)
                self.assertEqual(final_payload["status"], "failed")
                error_payload = final_payload.get("error") or {}
                self.assertEqual(error_payload.get("error_code"), "config_error")
                self.assertIn("not found", str(error_payload.get("message", "")).lower())

    async def test_missing_job_returns_404(self) -> None:
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/jobs/job_999999")
            self.assertEqual(response.status_code, 404, msg=response.text)


if __name__ == "__main__":
    unittest.main()
