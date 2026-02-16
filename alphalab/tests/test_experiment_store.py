"""Unit tests for SQLite experiment store."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alphalab.core.experiments.store import ExperimentStore


class TestExperimentStore(unittest.TestCase):
    """Validate create/get/list/update experiment operations."""

    def test_create_get_list_append(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "experiments.sqlite"
            store = ExperimentStore(db_path)

            first = store.create_experiment(
                experiment_id="exp_a",
                strategy_name="strategy_a",
                config_yaml="data:\n  symbols: [ES]\n",
                metrics={"sharpe_ratio": 1.23},
                artifact_paths=["/tmp/a.png"],
                tags=["baseline", " baseline ", ""],
            )
            second = store.create_experiment(
                experiment_id="exp_b",
                strategy_name="strategy_b",
                config_yaml="data:\n  symbols: [CL]\n",
                metrics={"sharpe_ratio": 0.45},
                artifact_paths=["/tmp/b.png"],
                tags=["candidate"],
            )

            loaded_first = store.get_experiment("exp_a")
            self.assertIsNotNone(loaded_first)
            assert loaded_first is not None
            self.assertEqual(loaded_first.experiment_id, "exp_a")
            self.assertEqual(loaded_first.tags, ["baseline"])

            listing = store.list_experiments(limit=10)
            self.assertEqual(len(listing), 2)
            self.assertEqual({item.experiment_id for item in listing}, {"exp_a", "exp_b"})

            updated = store.append_artifacts("exp_a", ["/tmp/c.png", "/tmp/a.png"])
            self.assertEqual(sorted(updated.artifact_paths), ["/tmp/a.png", "/tmp/c.png"])

            self.assertEqual(first.experiment_id, "exp_a")
            self.assertEqual(second.experiment_id, "exp_b")


if __name__ == "__main__":
    unittest.main()
