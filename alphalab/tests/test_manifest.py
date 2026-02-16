"""Unit tests for run manifest writer."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from alphalab.core.utils.manifest import RunManifestWriter


class TestRunManifestWriter(unittest.TestCase):
    """Validate success and failure manifest serialization."""

    def test_success_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            writer = RunManifestWriter(output_dir=output_dir, command="run", run_id="exp_1")
            writer.set_inputs(config_path=Path("config.yaml"), db_path=Path("db.sqlite"))
            writer.set_context(
                strategy_name="trend_following",
                symbols=["ES"],
                start="2020-01-01",
                end="2020-01-31",
            )
            writer.mark_success(
                metrics={"sharpe_ratio": 1.0},
                artifact_paths=["/tmp/a.png"],
                extra={"experiment_id": "exp_1"},
            )
            manifest_path = writer.write()
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["status"], "success")
            self.assertEqual(payload["command"], "run")
            self.assertEqual(payload["run_id"], "exp_1")
            self.assertIn("sharpe_ratio", payload["result"]["metrics"])
            self.assertIn("/tmp/a.png", payload["result"]["artifact_paths"])

    def test_failure_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            writer = RunManifestWriter(
                output_dir=output_dir,
                command="robustness",
                run_id="exp_2",
                manifest_name="robustness_manifest.json",
            )
            writer.mark_failure(RuntimeError("boom"))
            manifest_path = writer.write()
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["failure"]["exception_type"], "RuntimeError")
            self.assertIn("boom", payload["failure"]["message"])
            self.assertTrue(payload["failure"]["traceback"])


if __name__ == "__main__":
    unittest.main()
