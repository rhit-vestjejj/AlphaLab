"""Pydantic schemas for AlphaLab API endpoints."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class HealthResponse(BaseModel):
    """Health endpoint response."""

    status: str = "ok"
    service: str = "alphalab-api"


class ErrorResponse(BaseModel):
    """Error payload for typed API failures."""

    error_code: str
    message: str


class ExperimentSummaryResponse(BaseModel):
    """Summary view of one experiment."""

    experiment_id: str
    timestamp: datetime
    strategy_name: str
    sharpe_ratio: float
    tags: list[str]


class ExperimentDetailResponse(BaseModel):
    """Full experiment payload."""

    experiment_id: str
    timestamp: datetime
    strategy_name: str
    config_yaml: str
    metrics: dict[str, float]
    artifact_paths: list[str]
    tags: list[str]


class RunRequest(BaseModel):
    """Run endpoint request payload."""

    config_path: Path | None = None
    source_experiment_id: str | None = None
    db_path: Path = Path("alphalab/data/experiments.sqlite")

    @model_validator(mode="after")
    def validate_source(self) -> RunRequest:
        """Enforce exactly one run source."""
        has_config = self.config_path is not None
        has_source_id = bool(self.source_experiment_id)
        if has_config == has_source_id:
            raise ValueError("Provide exactly one of config_path or source_experiment_id.")
        return self


class RunResponse(BaseModel):
    """Run endpoint response payload."""

    experiment_id: str
    strategy_name: str
    symbols: list[str]
    metrics: dict[str, float]
    experiments_db: str
    artifact_paths: list[str]
    source_experiment_id: str | None = None
    manifest_path: str


class RobustnessRequest(BaseModel):
    """Robustness endpoint request payload."""

    experiment_id: str = Field(min_length=1)
    db_path: Path = Path("alphalab/data/experiments.sqlite")


class RobustnessResponse(BaseModel):
    """Robustness endpoint response payload."""

    experiment_id: str
    strategy_name: str
    report_path: str
    summary_json_path: str
    baseline_metrics: dict[str, float]
    aggregated_metrics: dict[str, float]
    artifact_paths: list[str]
    manifest_path: str


class JobErrorResponse(BaseModel):
    """Background job error payload."""

    error_code: str
    message: str
    traceback: str | None = None


class JobRecordResponse(BaseModel):
    """Background job status payload."""

    job_id: str
    job_type: Literal["run", "robustness"]
    status: Literal["queued", "running", "succeeded", "failed"]
    submitted_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    request: dict[str, Any]
    result: dict[str, Any] | None = None
    error: JobErrorResponse | None = None
