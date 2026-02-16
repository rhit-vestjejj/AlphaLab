"""AlphaLab command-line interface."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

import pandas as pd
import typer

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
from alphalab.core.utils.env import load_dotenv
from alphalab.core.utils.errors import (
    ConfigLoadError,
    DataValidationError,
    ExperimentStoreError,
    exit_code_for_exception,
)
from alphalab.core.utils.logging import configure_logging, get_logger
from alphalab.core.utils.manifest import RunManifestWriter
from alphalab.core.utils.plotting import save_equity_curve_plot

app = typer.Typer(help="AlphaLab CLI", no_args_is_help=True)
DEFAULT_DB_PATH = Path("alphalab/data/experiments.sqlite")

RUN_CONFIG_OPTION = typer.Option(
    None,
    "--config",
    file_okay=True,
    dir_okay=False,
    resolve_path=True,
    help="Path to YAML configuration file.",
)
RUN_EXPERIMENT_OPTION = typer.Option(
    None,
    "--experiment",
    help="Existing experiment id to re-run from stored config.",
)
RUN_DB_PATH_OPTION = typer.Option(
    DEFAULT_DB_PATH,
    "--db-path",
    file_okay=True,
    dir_okay=False,
    resolve_path=True,
    help="SQLite experiment database path (used with --experiment).",
)

ROBUSTNESS_EXPERIMENT_OPTION = typer.Option(
    ...,
    "--experiment",
    help="Experiment identifier.",
)
ROBUSTNESS_DB_PATH_OPTION = typer.Option(
    DEFAULT_DB_PATH,
    "--db-path",
    file_okay=True,
    dir_okay=False,
    resolve_path=True,
    help="SQLite experiment database path.",
)

LIST_DB_PATH_OPTION = typer.Option(
    DEFAULT_DB_PATH,
    "--db-path",
    file_okay=True,
    dir_okay=False,
    resolve_path=True,
    help="SQLite experiment database path.",
)
LIST_LIMIT_OPTION = typer.Option(50, "--limit", min=1, help="Maximum rows to show.")

SHOW_EXPERIMENT_OPTION = typer.Option(
    ...,
    "--experiment",
    help="Experiment identifier.",
)
SHOW_DB_PATH_OPTION = typer.Option(
    DEFAULT_DB_PATH,
    "--db-path",
    file_okay=True,
    dir_okay=False,
    resolve_path=True,
    help="SQLite experiment database path.",
)


@app.callback()
def callback() -> None:
    """AlphaLab CLI commands."""


def _format_date_range(frame_index: object) -> tuple[str, str]:
    """Return a printable date range from a datetime index."""
    if getattr(frame_index, "empty", True):
        return ("None", "None")
    min_date = frame_index.min().date().isoformat()
    max_date = frame_index.max().date().isoformat()
    return (min_date, max_date)


def _print_metrics(metrics: dict[str, float]) -> None:
    """Print core backtest metrics in deterministic order."""
    metric_order = [
        "annualized_return",
        "annualized_volatility",
        "sharpe_ratio",
        "max_drawdown",
        "calmar_ratio",
        "average_daily_turnover",
        "average_gross_exposure",
        "percentage_positive_days",
    ]
    for key in metric_order:
        if key in metrics:
            typer.echo(f"{key}={metrics[key]:.6f}")


def _handle_cli_exception(
    logger_name: str,
    context: str,
    exc: Exception,
    manifest_writer: RunManifestWriter | None = None,
) -> None:
    """Write failure manifest (if available), log diagnostics, and exit with typed code."""
    logger = get_logger(logger_name)
    manifest_path: Path | None = None
    if manifest_writer is not None:
        try:
            manifest_writer.mark_failure(exc)
            manifest_path = manifest_writer.write()
        except Exception as manifest_exc:
            logger.error("Failed to write failure manifest for %s: %s", context, manifest_exc)

    logger.exception("%s failed: %s", context, exc)
    if manifest_path is not None:
        typer.echo(f"manifest={manifest_path}")
    raise typer.Exit(code=exit_code_for_exception(exc)) from None


def _load_data_by_symbol(
    symbols: list[str],
    start: str,
    end: str,
    cache: ParquetCache,
    provider: EODHDProvider,
    logger_name: str,
) -> dict[str, pd.DataFrame]:
    """Fetch and cache symbol data for a date range."""
    logger = get_logger(logger_name)
    data_by_symbol: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        logger.info("Loading %s data from %s to %s", symbol, start, end)
        frame = cache.get_ohlcv(symbol=symbol, start=start, end=end, fetcher=provider.fetch_ohlcv)
        if frame.empty:
            raise DataValidationError(f"Fetched no data for symbol '{symbol}'.")
        data_by_symbol[symbol] = frame
        min_date, max_date = _format_date_range(frame.index)
        typer.echo(f"{symbol}: shape={frame.shape}, date_range=[{min_date}, {max_date}]")
    return data_by_symbol


def _load_strategy_and_data(
    app_config: AppConfig,
    logger_name: str,
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
        logger_name=logger_name,
    )
    return strategy, data_by_symbol


def _run_backtest_with_config(
    app_config: AppConfig,
    logger_name: str,
) -> tuple[StrategyDefinition, dict[str, pd.DataFrame], BacktestResult]:
    """Run baseline backtest from an in-memory app config."""
    strategy, data_by_symbol = _load_strategy_and_data(app_config, logger_name)
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
    """Load config for run command from file or stored experiment."""
    has_config = config_path is not None
    has_source_experiment = bool(source_experiment_id)
    if has_config and has_source_experiment:
        raise ConfigLoadError("Use either --config or --experiment, not both.")
    if not has_config and not has_source_experiment:
        raise ConfigLoadError("Either --config or --experiment must be provided.")

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


def _print_experiment_row(record: ExperimentRecord) -> None:
    """Print one experiment row in list format."""
    timestamp = record.timestamp.astimezone(UTC).isoformat()
    sharpe = float(record.metrics.get("sharpe_ratio", 0.0))
    tags = ",".join(record.tags) if record.tags else "-"
    typer.echo(
        f"{record.experiment_id} | {timestamp} | {record.strategy_name} | "
        f"sharpe={sharpe:.6f} | tags={tags}"
    )


@app.command("run")
def run(
    config: Path | None = RUN_CONFIG_OPTION,
    experiment: str | None = RUN_EXPERIMENT_OPTION,
    db_path: Path = RUN_DB_PATH_OPTION,
) -> None:
    """
    Run a full deterministic strategy backtest and persist experiment metadata.

    Provide one of:
    - ``--config`` to run from YAML config
    - ``--experiment`` to re-run from stored config
    """
    load_dotenv(Path(".env"))
    configure_logging()
    logger_name = __name__
    manifest_writer: RunManifestWriter | None = None
    source_experiment_id: str | None = None

    try:
        app_config, source_experiment_id = _load_config_for_run(
            config_path=config,
            source_experiment_id=experiment,
            db_path=db_path,
        )
        store = ExperimentStore(
            db_path if source_experiment_id is not None else app_config.experiments.db_path
        )
        experiment_id = store.next_experiment_id()
        run_artifact_dir = app_config.output.artifacts_dir / experiment_id
        manifest_writer = RunManifestWriter(
            output_dir=run_artifact_dir,
            command="run",
            run_id=experiment_id,
        )
        manifest_writer.set_inputs(
            config_path=config,
            source_experiment_id=source_experiment_id,
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
            logger_name=logger_name,
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
        if source_experiment_id is not None:
            tags.append(f"rerun_of:{source_experiment_id}")

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
                "source_experiment_id": source_experiment_id,
            },
        )
        manifest_path = manifest_writer.write()
        saved_record = store.append_artifacts(saved_record.experiment_id, [str(manifest_path)])
    except Exception as exc:
        _handle_cli_exception(
            logger_name=logger_name,
            context="Run command",
            exc=exc,
            manifest_writer=manifest_writer,
        )

    typer.echo(f"strategy={strategy.strategy_name}")
    typer.echo(f"symbols={','.join(sorted(data_by_symbol))}")
    _print_metrics(result.metrics)
    typer.echo(f"experiment_id={saved_record.experiment_id}")
    typer.echo(f"experiments_db={store.db_path}")

    if saved_record.artifact_paths:
        for path in saved_record.artifact_paths:
            typer.echo(f"artifact={path}")
    if source_experiment_id is not None:
        typer.echo(f"rerun_from={source_experiment_id}")


@app.command("robustness")
def robustness(
    experiment: str = ROBUSTNESS_EXPERIMENT_OPTION,
    db_path: Path = ROBUSTNESS_DB_PATH_OPTION,
) -> None:
    """Run full robustness suite and persist artifacts."""
    load_dotenv(Path(".env"))
    configure_logging()
    logger_name = __name__
    manifest_writer: RunManifestWriter | None = None

    try:
        store = ExperimentStore(db_path)
        record = store.get_experiment(experiment)
        if record is None:
            raise ExperimentStoreError(f"Experiment '{experiment}' not found in {store.db_path}.")

        app_config = load_config_from_yaml_text(record.config_yaml)
        output_dir = app_config.output.artifacts_dir / experiment
        manifest_writer = RunManifestWriter(
            output_dir=output_dir,
            command="robustness",
            run_id=experiment,
            manifest_name="robustness_manifest.json",
        )
        manifest_writer.set_inputs(
            config_path=None,
            source_experiment_id=experiment,
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
            logger_name=logger_name,
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
            experiment_id=experiment,
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
        store.append_artifacts(experiment_id=experiment, artifact_paths=new_artifacts)
    except Exception as exc:
        _handle_cli_exception(
            logger_name=logger_name,
            context="Robustness command",
            exc=exc,
            manifest_writer=manifest_writer,
        )

    typer.echo(f"experiment={experiment}")
    typer.echo(f"strategy={strategy.strategy_name}")
    typer.echo(f"report={robustness_result.report_path}")
    typer.echo(f"summary_json={robustness_result.summary_json_path}")
    typer.echo("baseline_metrics:")
    _print_metrics(robustness_result.baseline_metrics)
    typer.echo("aggregated_metrics:")
    for key in sorted(robustness_result.aggregated_metrics):
        typer.echo(f"{key}={robustness_result.aggregated_metrics[key]:.6f}")


@app.command("list")
def list_experiments(
    db_path: Path = LIST_DB_PATH_OPTION,
    limit: int = LIST_LIMIT_OPTION,
) -> None:
    """List stored experiments."""
    load_dotenv(Path(".env"))
    configure_logging()
    logger_name = __name__

    try:
        store = ExperimentStore(db_path)
        records = store.list_experiments(limit=limit)
    except Exception as exc:
        _handle_cli_exception(
            logger_name=logger_name,
            context="List command",
            exc=exc,
            manifest_writer=None,
        )

    if not records:
        typer.echo(f"No experiments found in {store.db_path}.")
        return

    typer.echo("experiment_id | timestamp | strategy | sharpe | tags")
    for record in records:
        _print_experiment_row(record)


@app.command("show")
def show_experiment(
    experiment: str = SHOW_EXPERIMENT_OPTION,
    db_path: Path = SHOW_DB_PATH_OPTION,
) -> None:
    """Show one stored experiment."""
    load_dotenv(Path(".env"))
    configure_logging()
    logger_name = __name__

    try:
        store = ExperimentStore(db_path)
        record = store.get_experiment(experiment)
        if record is None:
            raise ExperimentStoreError(f"Experiment '{experiment}' not found in {store.db_path}.")
    except Exception as exc:
        _handle_cli_exception(
            logger_name=logger_name,
            context="Show command",
            exc=exc,
            manifest_writer=None,
        )

    typer.echo(f"experiment_id={record.experiment_id}")
    typer.echo(f"timestamp={record.timestamp.astimezone(UTC).isoformat()}")
    typer.echo(f"strategy={record.strategy_name}")
    typer.echo(f"tags={','.join(record.tags) if record.tags else ''}")
    typer.echo("metrics:")
    _print_metrics(record.metrics)
    typer.echo("artifact_paths:")
    if record.artifact_paths:
        for path in record.artifact_paths:
            typer.echo(f"- {path}")
    else:
        typer.echo("-")
    typer.echo("config_yaml:")
    typer.echo(record.config_yaml.rstrip())


def main() -> None:
    """CLI entrypoint."""
    app()


if __name__ == "__main__":
    main()
