"""FastAPI application for AlphaLab workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from alphalab.api.schemas import (
    ErrorResponse,
    ExperimentDetailResponse,
    ExperimentSummaryResponse,
    HealthResponse,
    RobustnessRequest,
    RobustnessResponse,
    RunRequest,
    RunResponse,
)
from alphalab.core.services import get_experiment, list_experiments, run_experiment, run_robustness
from alphalab.core.utils.env import load_dotenv
from alphalab.core.utils.errors import (
    AlphaLabError,
    ArtifactError,
    BacktestError,
    CacheError,
    ConfigLoadError,
    DataFetchError,
    DataValidationError,
    ExperimentStoreError,
    RobustnessError,
    StrategyError,
)
from alphalab.core.utils.logging import configure_logging, get_logger

DEFAULT_DB_PATH = Path("alphalab/data/experiments.sqlite")
DB_PATH_QUERY = Query(default=DEFAULT_DB_PATH)
LIMIT_QUERY = Query(default=50, ge=1, le=500)
_LOGGER_NAME = "alphalab.api.app"


def _http_status_for_alphalab_error(exc: AlphaLabError) -> int:
    """Map typed domain exceptions to HTTP status codes."""
    if isinstance(exc, ConfigLoadError):
        return 400
    if isinstance(exc, DataFetchError):
        return 502
    if isinstance(exc, DataValidationError):
        return 422
    if isinstance(exc, CacheError):
        return 500
    if isinstance(exc, (StrategyError, BacktestError, RobustnessError)):
        return 400
    if isinstance(exc, ExperimentStoreError):
        if "not found" in str(exc).lower():
            return 404
        return 500
    if isinstance(exc, ArtifactError):
        return 500
    return 500


def create_app() -> FastAPI:
    """
    Build and return the AlphaLab FastAPI app.

    Returns:
        Configured FastAPI instance.
    """
    load_dotenv(Path(".env"))
    configure_logging()

    app = FastAPI(
        title="AlphaLab API",
        version="0.1.0",
        description="Programmatic API for AlphaLab local research workflows.",
    )
    logger = get_logger(_LOGGER_NAME)
    logger.info("AlphaLab API startup complete.")

    @app.exception_handler(AlphaLabError)
    async def _handle_alphalab_error(_: Any, exc: AlphaLabError) -> JSONResponse:
        """Render typed domain errors as JSON responses."""
        logger = get_logger(_LOGGER_NAME)
        logger.error("AlphaLab API error: %s", exc)
        payload = ErrorResponse(error_code=exc.error_code, message=str(exc))
        return JSONResponse(
            status_code=_http_status_for_alphalab_error(exc),
            content=payload.model_dump(),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(_: Any, exc: Exception) -> JSONResponse:
        """Render unknown errors as deterministic API payloads."""
        logger = get_logger(_LOGGER_NAME)
        logger.exception("Unhandled API error: %s", exc)
        payload = ErrorResponse(error_code="internal_error", message="Internal server error.")
        return JSONResponse(status_code=500, content=payload.model_dump())

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Return API health metadata."""
        return HealthResponse()

    @app.get("/experiments", response_model=list[ExperimentSummaryResponse])
    async def experiments(
        db_path: Path = DB_PATH_QUERY,
        limit: int = LIMIT_QUERY,
    ) -> list[ExperimentSummaryResponse]:
        """List stored experiments."""
        records = list_experiments(db_path=db_path, limit=limit)
        return [
            ExperimentSummaryResponse(
                experiment_id=record.experiment_id,
                timestamp=record.timestamp,
                strategy_name=record.strategy_name,
                sharpe_ratio=float(record.metrics.get("sharpe_ratio", 0.0)),
                tags=list(record.tags),
            )
            for record in records
        ]

    @app.get("/experiments/{experiment_id}", response_model=ExperimentDetailResponse)
    async def experiment_detail(
        experiment_id: str,
        db_path: Path = DB_PATH_QUERY,
    ) -> ExperimentDetailResponse:
        """Get full experiment details by id."""
        record = get_experiment(experiment_id=experiment_id, db_path=db_path)
        return ExperimentDetailResponse(
            experiment_id=record.experiment_id,
            timestamp=record.timestamp,
            strategy_name=record.strategy_name,
            config_yaml=record.config_yaml,
            metrics=dict(record.metrics),
            artifact_paths=list(record.artifact_paths),
            tags=list(record.tags),
        )

    @app.post("/runs", response_model=RunResponse)
    async def runs(request: RunRequest) -> RunResponse:
        """Run a backtest experiment from config or an existing experiment."""
        outcome = run_experiment(
            config_path=request.config_path,
            source_experiment_id=request.source_experiment_id,
            db_path=request.db_path,
        )
        return RunResponse(
            experiment_id=outcome.experiment_id,
            strategy_name=outcome.strategy_name,
            symbols=list(outcome.symbols),
            metrics=dict(outcome.metrics),
            experiments_db=str(outcome.experiment_db_path),
            artifact_paths=list(outcome.artifact_paths),
            source_experiment_id=outcome.source_experiment_id,
            manifest_path=str(outcome.manifest_path),
        )

    @app.post("/robustness", response_model=RobustnessResponse)
    async def robustness(request: RobustnessRequest) -> RobustnessResponse:
        """Run robustness suite for an existing experiment id."""
        outcome = run_robustness(experiment_id=request.experiment_id, db_path=request.db_path)
        return RobustnessResponse(
            experiment_id=outcome.experiment_id,
            strategy_name=outcome.strategy_name,
            report_path=str(outcome.report_path),
            summary_json_path=str(outcome.summary_json_path),
            baseline_metrics=dict(outcome.baseline_metrics),
            aggregated_metrics=dict(outcome.aggregated_metrics),
            artifact_paths=list(outcome.artifact_paths),
            manifest_path=str(outcome.manifest_path),
        )

    return app
