"""Run manifest utilities for diagnostics and reproducibility."""

from __future__ import annotations

import json
import platform
import sys
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class RunManifestWriter:
    """Incrementally build and persist command run manifests."""

    output_dir: Path
    command: str
    run_id: str
    manifest_name: str = "run_manifest.json"
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    _payload: dict[str, Any] = field(init=False)

    def __post_init__(self) -> None:
        """Initialize base payload metadata."""
        self._payload = {
            "manifest_version": 1,
            "command": self.command,
            "run_id": self.run_id,
            "status": "running",
            "started_at": self.started_at.isoformat(),
            "finished_at": None,
            "duration_seconds": None,
            "environment": {
                "python_version": sys.version.split()[0],
                "platform": platform.platform(),
            },
            "inputs": {},
            "context": {},
            "result": {},
            "failure": {},
        }

    def set_inputs(
        self,
        config_path: Path | None = None,
        source_experiment_id: str | None = None,
        db_path: Path | None = None,
    ) -> None:
        """Set command inputs."""
        self._payload["inputs"] = {
            "config_path": str(config_path.resolve()) if config_path is not None else None,
            "source_experiment_id": source_experiment_id,
            "db_path": str(db_path.resolve()) if db_path is not None else None,
        }

    def set_context(
        self,
        strategy_name: str,
        symbols: list[str],
        start: str,
        end: str,
    ) -> None:
        """Set run context metadata."""
        self._payload["context"] = {
            "strategy_name": strategy_name,
            "symbols": sorted(symbols),
            "date_range": {"start": start, "end": end},
        }

    def mark_success(
        self,
        metrics: dict[str, float],
        artifact_paths: list[str],
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Mark manifest as successful."""
        self._payload["status"] = "success"
        self._payload["result"] = {
            "metrics": dict(metrics),
            "artifact_paths": sorted({str(path) for path in artifact_paths}),
            "extra": extra or {},
        }
        self._payload["failure"] = {}

    def mark_failure(self, exc: Exception) -> None:
        """Mark manifest as failed and capture exception diagnostics."""
        self._payload["status"] = "failed"
        self._payload["result"] = {}
        self._payload["failure"] = {
            "exception_type": exc.__class__.__name__,
            "message": str(exc),
            "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        }

    def write(self) -> Path:
        """Persist manifest and return written path."""
        finished_at = datetime.now(tz=UTC)
        duration = (finished_at - self.started_at).total_seconds()
        self._payload["finished_at"] = finished_at.isoformat()
        self._payload["duration_seconds"] = float(duration)

        self.output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.output_dir / self.manifest_name
        manifest_path.write_text(
            json.dumps(self._payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest_path
