"""Programmatic service workflows for AlphaLab research operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from alphalab.core.backtest.engine import run_backtest
from alphalab.core.backtest.types import BacktestResult
from alphalab.core.config import (
    AppConfig,
    dump_config_to_yaml,
    load_config,
    load_config_from_yaml_text,
)
from alphalab.core.data.cache import ParquetCache
from alphalab.core.data.eodhd_provider import EODHDProvider
from alphalab.core.experiments.store import ExperimentRecord, ExperimentStore
from alphalab.core.research.robustness import RobustnessSettings, run_robustness_suite
from alphalab.core.research.strategy import StrategyDefinition, load_strategy
from alphalab.core.utils.errors import ConfigLoadError, DataValidationError, ExperimentStoreError
from alphalab.core.utils.logging import get_logger
from alphalab.core.utils.manifest import RunManifestWriter
from alphalab.core.utils.plotting import save_equity_curve_plot

DEFAULT_DB_PATH = Path("alphalab/data/experiments.sqlite")
ProgressCallback = Callable[[str], None]
_LOGGER_NAME = "alphalab.core.services.research_service"


@dataclass(frozen=True)
class RunOutcome:
    """Result payload for one completed backtest run."""

    experiment_id: str
    strategy_name: str
    symbols: list[str]
    metrics: dict[str, float]
    experiment_db_path: Path
    artifact_paths: list[str]
    source_experiment_id: str | None
    manifest_path: Path


@dataclass(frozen=True)
class RobustnessOutcome:
    """Result payload for one completed robustness run."""

    experiment_id: str
    strategy_name: str
    report_path: Path
    summary_json_path: Path
    baseline_metrics: dict[str, float]
    aggregated_metrics: dict[str, float]
    artifact_paths: list[str]
    manifest_path: Path


def _emit_progress(callback: ProgressCallback | None, message: str) -> None:
    """Emit optional progress messages."""
    if callback is not None:
        callback(message)


def _format_date_range(frame_index: object) -> tuple[str, str]:
    """Return a printable date range from a datetime index."""
    if getattr(frame_index, "empty", True):
        return ("None", "None")
    min_date = frame_index.min().date().isoformat()
    max_date = frame_index.max().date().isoformat()
    return (min_date, max_date)


def _load_data_by_symbol(
    symbols: list[str],
    start: str,
    end: str,
    cache: ParquetCache,
    provider: EODHDProvider,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch and cache symbol data for a date range."""
    logger = get_logger(_LOGGER_NAME)
    data_by_symbol: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        logger.info("Loading %s data from %s to %s", symbol, start, end)
        _emit_progress(progress_callback, f"Loading {symbol} data from {start} to {end}")
        frame = cache.get_ohlcv(symbol=symbol, start=start, end=end, fetcher=provider.fetch_ohlcv)
        if frame.empty:
            raise DataValidationError(f"Fetched no data for symbol '{symbol}'.")
        data_by_symbol[symbol] = frame
        min_date, max_date = _format_date_range(frame.index)
        _emit_progress(
            progress_callback,
            f"{symbol}: shape={frame.shape}, date_range=[{min_date}, {max_date}]",
        )
    return data_by_symbol


def _load_strategy_and_data(
    app_config: AppConfig,
    progress_callback: ProgressCallback | None = None,
) -> tuple[StrategyDefinition, dict[str, pd.DataFrame]]:
    """Load strategy and fetch data for all configured symbols."""
    strategy = load_strategy(app_config.strategy.module)
    start = app_config.data.start.isoformat()
    end = app_config.data.end.isoformat()

    cache = ParquetCache(app_config.data.cache_dir)
    provider = EODHDProvider()
    data_by_symbol = _load_data_by_symbol(
        symbols=app_config.data.symbols,
        start=start,
        end=end,
        cache=cache,
        provider=provider,
        progress_callback=progress_callback,
    )
    return strategy, data_by_symbol


def _run_backtest_with_config(
    app_config: AppConfig,
    progress_callback: ProgressCallback | None = None,
) -> tuple[StrategyDefinition, dict[str, pd.DataFrame], BacktestResult]:
    """Run baseline backtest from an in-memory app config."""
    strategy, data_by_symbol = _load_strategy_and_data(
        app_config,
        progress_callback=progress_callback,
    )
    result = run_backtest(
        data_by_symbol=data_by_symbol,
        strategy=strategy,
        strategy_params=app_config.strategy.params,
        transaction_cost_bps=app_config.backtest.transaction_cost_bps,
        leverage_cap=app_config.backtest.leverage_cap,
        max_position=app_config.backtest.max_position,
        annualization_factor=app_config.backtest.annualization_factor,
    )
    return strategy, data_by_symbol, result


def _load_config_for_run(
    config_path: Path | None,
    source_experiment_id: str | None,
    db_path: Path,
) -> tuple[AppConfig, str | None]:
    """Load config for a run from file or stored experiment."""
    has_config = config_path is not None
    has_source_experiment = bool(source_experiment_id)
    if has_config and has_source_experiment:
        raise ConfigLoadError("Use either config_path or source_experiment_id, not both.")
    if not has_config and not has_source_experiment:
        raise ConfigLoadError("Either config_path or source_experiment_id must be provided.")

    if source_experiment_id:
        store = ExperimentStore(db_path)
        record = store.get_experiment(source_experiment_id)
        if record is None:
            raise ExperimentStoreError(
                f"Experiment '{source_experiment_id}' not found in {store.db_path}."
            )
        app_config = load_config_from_yaml_text(record.config_yaml)
        return app_config, source_experiment_id

    assert config_path is not None
    app_config = load_config(config_path)
    return app_config, None


def run_experiment(
    config_path: Path | None = None,
    source_experiment_id: str | None = None,
    db_path: Path = DEFAULT_DB_PATH,
    progress_callback: ProgressCallback | None = None,
) -> RunOutcome:
    """
    Run a deterministic backtest and persist experiment metadata.

    Args:
        config_path: Path to YAML config file.
        source_experiment_id: Optional existing experiment id to re-run.
        db_path: SQLite database path, used for source lookups and reruns.
        progress_callback: Optional callback for status messages.

    Returns:
        Completed run outcome.
    """
    logger = get_logger(_LOGGER_NAME)
    manifest_writer: RunManifestWriter | None = None
    resolved_source_id: str | None = None

    try:
        app_config, resolved_source_id = _load_config_for_run(
            config_path=config_path,
            source_experiment_id=source_experiment_id,
            db_path=db_path,
        )
        store = ExperimentStore(
            db_path if resolved_source_id is not None else app_config.experiments.db_path
        )
        experiment_id = store.next_experiment_id()
        run_artifact_dir = app_config.output.artifacts_dir / experiment_id
        manifest_writer = RunManifestWriter(
            output_dir=run_artifact_dir,
            command="run",
            run_id=experiment_id,
        )
        manifest_writer.set_inputs(
            config_path=config_path,
            source_experiment_id=resolved_source_id,
            db_path=store.db_path,
        )
        start = app_config.data.start.isoformat()
        end = app_config.data.end.isoformat()
        manifest_writer.set_context(
            strategy_name=app_config.strategy.module,
            symbols=list(app_config.data.symbols),
            start=start,
            end=end,
        )

        strategy, data_by_symbol, result = _run_backtest_with_config(
            app_config=app_config,
            progress_callback=progress_callback,
        )
        manifest_writer.set_context(
            strategy_name=strategy.strategy_name,
            symbols=list(app_config.data.symbols),
            start=start,
            end=end,
        )

        artifact_paths: list[str] = []
        if app_config.output.save_equity_plot:
            plot_path = save_equity_curve_plot(
                equity_curve=result.equity_curve,
                output_dir=run_artifact_dir,
                filename=app_config.output.equity_plot_filename,
            )
            artifact_paths.append(str(plot_path))

        tags = list(app_config.experiments.tags)
        if resolved_source_id is not None:
            tags.append(f"rerun_of:{resolved_source_id}")

        saved_record = store.create_experiment(
            experiment_id=experiment_id,
            strategy_name=strategy.strategy_name,
            config_yaml=dump_config_to_yaml(app_config),
            metrics=result.metrics,
            artifact_paths=artifact_paths,
            tags=tags,
        )
        manifest_writer.mark_success(
            metrics=result.metrics,
            artifact_paths=artifact_paths,
            extra={
                "experiment_id": saved_record.experiment_id,
                "source_experiment_id": resolved_source_id,
            },
        )
        manifest_path = manifest_writer.write()
        saved_record = store.append_artifacts(saved_record.experiment_id, [str(manifest_path)])

        return RunOutcome(
            experiment_id=saved_record.experiment_id,
            strategy_name=strategy.strategy_name,
            symbols=sorted(data_by_symbol),
            metrics=dict(result.metrics),
            experiment_db_path=store.db_path,
            artifact_paths=list(saved_record.artifact_paths),
            source_experiment_id=resolved_source_id,
            manifest_path=manifest_path,
        )
    except Exception as exc:
        if manifest_writer is not None:
            try:
                manifest_writer.mark_failure(exc)
                manifest_writer.write()
            except Exception as manifest_exc:
                logger.error(
                    "Failed to write failure manifest for run_experiment: %s", manifest_exc
                )
        raise


def run_robustness(
    experiment_id: str,
    db_path: Path = DEFAULT_DB_PATH,
    progress_callback: ProgressCallback | None = None,
) -> RobustnessOutcome:
    """
    Run robustness suite for an existing experiment and persist artifacts.

    Args:
        experiment_id: Existing experiment id.
        db_path: SQLite experiment database path.
        progress_callback: Optional callback for status messages.

    Returns:
        Completed robustness outcome.
    """
    logger = get_logger(_LOGGER_NAME)
    manifest_writer: RunManifestWriter | None = None

    try:
        store = ExperimentStore(db_path)
        record = store.get_experiment(experiment_id)
        if record is None:
            raise ExperimentStoreError(
                f"Experiment '{experiment_id}' not found in {store.db_path}."
            )

        app_config = load_config_from_yaml_text(record.config_yaml)
        output_dir = app_config.output.artifacts_dir / experiment_id
        manifest_writer = RunManifestWriter(
            output_dir=output_dir,
            command="robustness",
            run_id=experiment_id,
            manifest_name="robustness_manifest.json",
        )
        manifest_writer.set_inputs(
            config_path=None,
            source_experiment_id=experiment_id,
            db_path=store.db_path,
        )

        start = app_config.data.start.isoformat()
        end = app_config.data.end.isoformat()
        manifest_writer.set_context(
            strategy_name=app_config.strategy.module,
            symbols=list(app_config.data.symbols),
            start=start,
            end=end,
        )

        strategy, data_by_symbol = _load_strategy_and_data(
            app_config=app_config,
            progress_callback=progress_callback,
        )
        manifest_writer.set_context(
            strategy_name=strategy.strategy_name,
            symbols=list(app_config.data.symbols),
            start=start,
            end=end,
        )

        settings = RobustnessSettings(
            walk_forward_splits=app_config.robustness.walk_forward_splits,
            parameter_grid=dict(app_config.robustness.parameter_grid),
            cost_stress_bps=list(app_config.robustness.cost_stress_bps),
            volatility_window=app_config.robustness.volatility_window,
            trend_window=app_config.robustness.trend_window,
        )
        robustness_result = run_robustness_suite(
            experiment_id=experiment_id,
            data_by_symbol=data_by_symbol,
            strategy=strategy,
            strategy_params=app_config.strategy.params,
            transaction_cost_bps=app_config.backtest.transaction_cost_bps,
            leverage_cap=app_config.backtest.leverage_cap,
            max_position=app_config.backtest.max_position,
            annualization_factor=app_config.backtest.annualization_factor,
            settings=settings,
            output_dir=output_dir,
            save_plots=True,
        )

        new_artifacts = [
            *[str(path) for path in robustness_result.artifact_paths],
            str(robustness_result.report_path),
            str(robustness_result.summary_json_path),
        ]
        manifest_writer.mark_success(
            metrics=robustness_result.aggregated_metrics,
            artifact_paths=new_artifacts,
            extra={"baseline_metrics": robustness_result.baseline_metrics},
        )
        manifest_path = manifest_writer.write()
        new_artifacts.append(str(manifest_path))
        updated_record = store.append_artifacts(
            experiment_id=experiment_id, artifact_paths=new_artifacts
        )

        return RobustnessOutcome(
            experiment_id=experiment_id,
            strategy_name=strategy.strategy_name,
            report_path=robustness_result.report_path,
            summary_json_path=robustness_result.summary_json_path,
            baseline_metrics=dict(robustness_result.baseline_metrics),
            aggregated_metrics=dict(robustness_result.aggregated_metrics),
            artifact_paths=list(updated_record.artifact_paths),
            manifest_path=manifest_path,
        )
    except Exception as exc:
        if manifest_writer is not None:
            try:
                manifest_writer.mark_failure(exc)
                manifest_writer.write()
            except Exception as manifest_exc:
                logger.error(
                    "Failed to write failure manifest for run_robustness: %s", manifest_exc
                )
        raise


def list_experiments(db_path: Path = DEFAULT_DB_PATH, limit: int = 50) -> list[ExperimentRecord]:
    """
    List experiments from a SQLite store.

    Args:
        db_path: SQLite experiment database path.
        limit: Maximum row count.

    Returns:
        Experiment records in reverse chronological order.
    """
    store = ExperimentStore(db_path)
    return store.list_experiments(limit=limit)


def get_experiment(experiment_id: str, db_path: Path = DEFAULT_DB_PATH) -> ExperimentRecord:
    """
    Load one experiment by id.

    Args:
        experiment_id: Experiment identifier.
        db_path: SQLite experiment database path.

    Returns:
        Loaded experiment record.

    Raises:
        ExperimentStoreError: If not found.
    """
    store = ExperimentStore(db_path)
    record = store.get_experiment(experiment_id)
    if record is None:
        raise ExperimentStoreError(f"Experiment '{experiment_id}' not found in {store.db_path}.")
    return record
