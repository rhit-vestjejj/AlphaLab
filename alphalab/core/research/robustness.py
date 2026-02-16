"""Robustness suite for systematic strategy validation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any

import pandas as pd

from alphalab.core.backtest.engine import run_backtest
from alphalab.core.backtest.metrics import calculate_metrics
from alphalab.core.research.strategy import StrategyDefinition
from alphalab.core.utils.errors import RobustnessError
from alphalab.core.utils.plotting import get_matplotlib_pyplot, save_equity_curve_plot

_METRIC_KEYS: tuple[str, ...] = (
    "annualized_return",
    "annualized_volatility",
    "sharpe_ratio",
    "max_drawdown",
    "calmar_ratio",
    "average_daily_turnover",
    "average_gross_exposure",
    "percentage_positive_days",
)


@dataclass(frozen=True)
class RobustnessSettings:
    """Robustness execution settings."""

    walk_forward_splits: int = 4
    parameter_grid: dict[str, list[Any]] = field(default_factory=dict)
    cost_stress_bps: list[float] = field(default_factory=lambda: [0.0, 5.0, 10.0, 25.0, 50.0])
    volatility_window: int = 20
    trend_window: int = 50


@dataclass(frozen=True)
class RobustnessResult:
    """Robustness outputs and artifact references."""

    baseline_metrics: dict[str, float]
    aggregated_metrics: dict[str, float]
    walk_forward_results: list[dict[str, Any]]
    parameter_grid_results: list[dict[str, Any]]
    cost_stress_results: list[dict[str, Any]]
    regime_results: list[dict[str, Any]]
    report_path: Path
    summary_json_path: Path
    artifact_paths: list[Path]


def _common_index(data_by_symbol: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    """Return intersection of all symbol indices in deterministic sorted order."""
    common_index: pd.DatetimeIndex | None = None
    for symbol in sorted(data_by_symbol):
        index = data_by_symbol[symbol].index
        if not isinstance(index, pd.DatetimeIndex):
            raise RobustnessError(f"Data for symbol '{symbol}' must use DatetimeIndex.")
        common_index = index if common_index is None else common_index.intersection(index)

    if common_index is None or common_index.empty:
        raise RobustnessError("No common dates found across symbol datasets.")
    return common_index.sort_values()


def _split_index(index: pd.DatetimeIndex, splits: int) -> list[pd.DatetimeIndex]:
    """Split index into contiguous chunks."""
    chunk_count = min(max(1, splits), len(index))
    base_size = len(index) // chunk_count
    remainder = len(index) % chunk_count

    chunks: list[pd.DatetimeIndex] = []
    cursor = 0
    for chunk_id in range(chunk_count):
        chunk_size = base_size + (1 if chunk_id < remainder else 0)
        if chunk_size == 0:
            continue
        next_cursor = cursor + chunk_size
        chunks.append(index[cursor:next_cursor])
        cursor = next_cursor
    return chunks


def _subset_data_by_index(
    data_by_symbol: dict[str, pd.DataFrame],
    index: pd.DatetimeIndex,
) -> dict[str, pd.DataFrame]:
    """Subset all symbols to a shared index."""
    subset: dict[str, pd.DataFrame] = {}
    for symbol in sorted(data_by_symbol):
        frame = data_by_symbol[symbol].reindex(index)
        if frame.empty:
            raise RobustnessError(f"Subset data is empty for symbol '{symbol}'.")
        subset[symbol] = frame
    return subset


def _ordered_unique(values: list[float]) -> list[float]:
    """Return unique values while preserving original order."""
    seen: set[float] = set()
    unique_values: list[float] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(float(value))
    return unique_values


def _parameter_combinations(
    base_params: dict[str, Any],
    parameter_grid: dict[str, list[Any]],
) -> list[tuple[str, dict[str, Any]]]:
    """Generate deterministic parameter combinations."""
    if not parameter_grid:
        return [("baseline", dict(base_params))]

    keys = sorted(parameter_grid)
    combinations: list[tuple[str, dict[str, Any]]] = []
    for values in product(*(parameter_grid[key] for key in keys)):
        params = dict(base_params)
        label_parts: list[str] = []
        for key, value in zip(keys, values, strict=True):
            params[key] = value
            label_parts.append(f"{key}={value}")
        combinations.append((",".join(label_parts), params))
    return combinations


def _mean_metric(rows: list[dict[str, Any]], metric_key: str) -> float:
    """Compute mean metric value across result rows."""
    if not rows:
        return 0.0
    return float(sum(float(row[metric_key]) for row in rows) / len(rows))


def _metrics_for_mask(
    mask: pd.Series,
    daily_returns: pd.Series,
    turnover: pd.Series,
    gross_exposure: pd.Series,
    annualization_factor: int,
) -> tuple[int, dict[str, float]]:
    """Calculate metrics for a boolean regime mask."""
    aligned_mask = mask.reindex(daily_returns.index).fillna(False).astype(bool)
    subset_returns = daily_returns.loc[aligned_mask]
    subset_turnover = turnover.loc[aligned_mask]
    subset_exposure = gross_exposure.loc[aligned_mask]
    subset_equity = (1.0 + subset_returns).cumprod()
    metrics = calculate_metrics(
        daily_returns=subset_returns,
        equity_curve=subset_equity,
        turnover=subset_turnover,
        gross_exposure=subset_exposure,
        annualization_factor=annualization_factor,
    )
    return (int(subset_returns.shape[0]), metrics)


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    """Render markdown table lines."""
    if not rows:
        return ["_No rows_"]

    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    body: list[str] = []
    for row in rows:
        rendered_values: list[str] = []
        for column in columns:
            value = row.get(column, "")
            if isinstance(value, float):
                rendered_values.append(f"{value:.6f}")
            else:
                rendered_values.append(str(value))
        body.append("| " + " | ".join(rendered_values) + " |")
    return [header, separator, *body]


def _save_walk_forward_plot(rows: list[dict[str, Any]], output_path: Path) -> Path:
    """Save walk-forward Sharpe ratio bar plot."""
    plt = get_matplotlib_pyplot()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    labels = [f"S{int(row['split'])}" for row in rows]
    values = [float(row["sharpe_ratio"]) for row in rows]

    figure, axis = plt.subplots(figsize=(10, 4))
    axis.bar(labels, values, color="#22577A")
    axis.set_title("Walk-Forward Sharpe Ratio")
    axis.set_xlabel("Split")
    axis.set_ylabel("Sharpe Ratio")
    axis.grid(alpha=0.2, axis="y", linestyle="--", linewidth=0.7)
    figure.tight_layout()
    figure.savefig(output_path, dpi=150)
    plt.close(figure)
    return output_path


def _save_parameter_grid_plot(rows: list[dict[str, Any]], output_path: Path) -> Path:
    """Save parameter sensitivity Sharpe ratio plot."""
    plt = get_matplotlib_pyplot()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    labels = [str(row["parameter_set"]) for row in rows]
    values = [float(row["sharpe_ratio"]) for row in rows]

    figure, axis = plt.subplots(figsize=(max(8, len(labels) * 1.3), 4))
    axis.bar(labels, values, color="#38A3A5")
    axis.set_title("Parameter Grid Sensitivity (Sharpe)")
    axis.set_xlabel("Parameter Set")
    axis.set_ylabel("Sharpe Ratio")
    axis.tick_params(axis="x", rotation=35)
    axis.grid(alpha=0.2, axis="y", linestyle="--", linewidth=0.7)
    figure.tight_layout()
    figure.savefig(output_path, dpi=150)
    plt.close(figure)
    return output_path


def _save_cost_stress_plot(rows: list[dict[str, Any]], output_path: Path) -> Path:
    """Save cost stress line plot."""
    plt = get_matplotlib_pyplot()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    costs = [float(row["cost_bps"]) for row in rows]
    sharpe = [float(row["sharpe_ratio"]) for row in rows]

    figure, axis = plt.subplots(figsize=(10, 4))
    axis.plot(costs, sharpe, marker="o", color="#2B9348", linewidth=1.5)
    axis.set_title("Cost Stress Test (Sharpe vs Cost)")
    axis.set_xlabel("Transaction Cost (bps)")
    axis.set_ylabel("Sharpe Ratio")
    axis.grid(alpha=0.25, linestyle="--", linewidth=0.7)
    figure.tight_layout()
    figure.savefig(output_path, dpi=150)
    plt.close(figure)
    return output_path


def _save_regime_plot(rows: list[dict[str, Any]], output_path: Path) -> Path:
    """Save regime annualized return bar plot."""
    plt = get_matplotlib_pyplot()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    labels = [str(row["regime"]) for row in rows]
    values = [float(row["annualized_return"]) for row in rows]

    figure, axis = plt.subplots(figsize=(9, 4))
    axis.bar(labels, values, color="#D4A373")
    axis.set_title("Regime Split Annualized Return")
    axis.set_xlabel("Regime")
    axis.set_ylabel("Annualized Return")
    axis.grid(alpha=0.25, axis="y", linestyle="--", linewidth=0.7)
    figure.tight_layout()
    figure.savefig(output_path, dpi=150)
    plt.close(figure)
    return output_path


def _write_markdown_report(
    experiment_id: str,
    output_dir: Path,
    baseline_metrics: dict[str, float],
    aggregated_metrics: dict[str, float],
    walk_forward_rows: list[dict[str, Any]],
    parameter_grid_rows: list[dict[str, Any]],
    cost_stress_rows: list[dict[str, Any]],
    regime_rows: list[dict[str, Any]],
    artifact_paths: list[Path],
) -> Path:
    """Write robustness markdown report and return path."""
    report_path = output_dir / "robustness_report.md"

    lines: list[str] = [
        f"# Robustness Report: {experiment_id}",
        "",
        f"Generated: {datetime.now(tz=UTC).isoformat()}",
        "",
        "## Baseline Metrics",
    ]
    baseline_rows = [{"metric": key, "value": value} for key, value in baseline_metrics.items()]
    lines.extend(_markdown_table(baseline_rows, ["metric", "value"]))

    lines.extend(["", "## Aggregated Metrics"])
    aggregate_rows = [{"metric": key, "value": value} for key, value in aggregated_metrics.items()]
    lines.extend(_markdown_table(aggregate_rows, ["metric", "value"]))

    lines.extend(["", "## Walk-Forward Splits"])
    lines.extend(
        _markdown_table(
            walk_forward_rows,
            ["split", "start", "end", "observations", *_METRIC_KEYS],
        )
    )

    lines.extend(["", "## Parameter Grid Sensitivity"])
    lines.extend(_markdown_table(parameter_grid_rows, ["parameter_set", *_METRIC_KEYS]))

    lines.extend(["", "## Cost Stress Test"])
    lines.extend(_markdown_table(cost_stress_rows, ["cost_bps", *_METRIC_KEYS]))

    lines.extend(["", "## Regime Splits"])
    lines.extend(_markdown_table(regime_rows, ["regime", "observations", *_METRIC_KEYS]))

    lines.extend(["", "## Artifacts"])
    for path in artifact_paths:
        lines.append(f"- {path}")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def run_robustness_suite(
    experiment_id: str,
    data_by_symbol: dict[str, pd.DataFrame],
    strategy: StrategyDefinition,
    strategy_params: dict[str, Any],
    transaction_cost_bps: float,
    leverage_cap: float,
    max_position: float,
    annualization_factor: int,
    settings: RobustnessSettings,
    output_dir: Path,
    save_plots: bool = True,
) -> RobustnessResult:
    """
    Run full robustness suite and persist artifacts.

    Args:
        experiment_id: Experiment identifier for report labeling.
        data_by_symbol: Symbol -> OHLCV dataframe mapping.
        strategy: Strategy definition.
        strategy_params: Baseline strategy parameters.
        transaction_cost_bps: Baseline transaction cost in bps.
        leverage_cap: Gross exposure cap.
        max_position: Per-symbol absolute max position.
        annualization_factor: Trading-day annualization factor.
        settings: Robustness settings.
        output_dir: Output artifact directory.
        save_plots: Whether to save chart artifacts.

    Returns:
        Full robustness result object.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline = run_backtest(
        data_by_symbol=data_by_symbol,
        strategy=strategy,
        strategy_params=dict(strategy_params),
        transaction_cost_bps=transaction_cost_bps,
        leverage_cap=leverage_cap,
        max_position=max_position,
        annualization_factor=annualization_factor,
    )

    common_index = _common_index(data_by_symbol)
    walk_chunks = _split_index(common_index, settings.walk_forward_splits)
    walk_forward_rows: list[dict[str, Any]] = []

    for split_id, split_index in enumerate(walk_chunks, start=1):
        split_data = _subset_data_by_index(data_by_symbol, split_index)
        split_result = run_backtest(
            data_by_symbol=split_data,
            strategy=strategy,
            strategy_params=dict(strategy_params),
            transaction_cost_bps=transaction_cost_bps,
            leverage_cap=leverage_cap,
            max_position=max_position,
            annualization_factor=annualization_factor,
        )
        walk_forward_rows.append(
            {
                "split": split_id,
                "start": split_index.min().date().isoformat(),
                "end": split_index.max().date().isoformat(),
                "observations": int(split_index.shape[0]),
                **split_result.metrics,
            }
        )

    parameter_grid_rows: list[dict[str, Any]] = []
    for label, params in _parameter_combinations(strategy_params, settings.parameter_grid):
        grid_result = run_backtest(
            data_by_symbol=data_by_symbol,
            strategy=strategy,
            strategy_params=params,
            transaction_cost_bps=transaction_cost_bps,
            leverage_cap=leverage_cap,
            max_position=max_position,
            annualization_factor=annualization_factor,
        )
        parameter_grid_rows.append({"parameter_set": label, **grid_result.metrics})

    cost_stress_rows: list[dict[str, Any]] = []
    for cost_bps in _ordered_unique(settings.cost_stress_bps):
        cost_result = run_backtest(
            data_by_symbol=data_by_symbol,
            strategy=strategy,
            strategy_params=dict(strategy_params),
            transaction_cost_bps=cost_bps,
            leverage_cap=leverage_cap,
            max_position=max_position,
            annualization_factor=annualization_factor,
        )
        cost_stress_rows.append({"cost_bps": float(cost_bps), **cost_result.metrics})

    symbol_returns = pd.concat(
        [
            data_by_symbol[symbol]["close"].astype(float).pct_change().fillna(0.0).rename(symbol)
            for symbol in sorted(data_by_symbol)
        ],
        axis=1,
    )
    portfolio_proxy_returns = (
        symbol_returns.mean(axis=1).reindex(baseline.daily_returns.index).fillna(0.0)
    )

    volatility_signal = portfolio_proxy_returns.rolling(
        window=settings.volatility_window,
        min_periods=settings.volatility_window,
    ).std()
    trend_signal = (
        portfolio_proxy_returns.rolling(
            window=settings.trend_window,
            min_periods=settings.trend_window,
        )
        .mean()
        .abs()
    )

    volatility_valid = volatility_signal.notna()
    trend_valid = trend_signal.notna()

    high_vol_mask = pd.Series(False, index=baseline.daily_returns.index)
    low_vol_mask = pd.Series(False, index=baseline.daily_returns.index)
    trend_mask = pd.Series(False, index=baseline.daily_returns.index)
    non_trend_mask = pd.Series(False, index=baseline.daily_returns.index)

    if volatility_valid.any():
        vol_threshold = float(volatility_signal.loc[volatility_valid].median())
        high_vol_mask = volatility_valid & (volatility_signal >= vol_threshold)
        low_vol_mask = volatility_valid & (volatility_signal < vol_threshold)
    if trend_valid.any():
        trend_threshold = float(trend_signal.loc[trend_valid].median())
        trend_mask = trend_valid & (trend_signal >= trend_threshold)
        non_trend_mask = trend_valid & (trend_signal < trend_threshold)

    baseline_exposure = baseline.positions.abs().sum(axis=1)
    regime_rows: list[dict[str, Any]] = []
    for regime_name, mask in [
        ("high_volatility", high_vol_mask),
        ("low_volatility", low_vol_mask),
        ("trend", trend_mask),
        ("non_trend", non_trend_mask),
    ]:
        observations, metrics = _metrics_for_mask(
            mask=mask,
            daily_returns=baseline.daily_returns,
            turnover=baseline.turnover,
            gross_exposure=baseline_exposure,
            annualization_factor=annualization_factor,
        )
        regime_rows.append({"regime": regime_name, "observations": observations, **metrics})

    aggregated_metrics = {
        "baseline_sharpe_ratio": float(baseline.metrics["sharpe_ratio"]),
        "walk_forward_average_sharpe_ratio": _mean_metric(walk_forward_rows, "sharpe_ratio"),
        "parameter_grid_average_sharpe_ratio": _mean_metric(parameter_grid_rows, "sharpe_ratio"),
        "cost_stress_average_sharpe_ratio": _mean_metric(cost_stress_rows, "sharpe_ratio"),
        "regime_average_sharpe_ratio": _mean_metric(regime_rows, "sharpe_ratio"),
    }

    artifact_paths: list[Path] = []
    if save_plots:
        artifact_paths.append(
            save_equity_curve_plot(
                equity_curve=baseline.equity_curve,
                output_dir=output_dir,
                filename="baseline_equity_curve.png",
            )
        )
        artifact_paths.append(
            _save_walk_forward_plot(walk_forward_rows, output_dir / "walk_forward.png")
        )
        artifact_paths.append(
            _save_parameter_grid_plot(parameter_grid_rows, output_dir / "parameter_grid.png")
        )
        artifact_paths.append(
            _save_cost_stress_plot(cost_stress_rows, output_dir / "cost_stress.png")
        )
        artifact_paths.append(_save_regime_plot(regime_rows, output_dir / "regimes.png"))

    report_path = _write_markdown_report(
        experiment_id=experiment_id,
        output_dir=output_dir,
        baseline_metrics=baseline.metrics,
        aggregated_metrics=aggregated_metrics,
        walk_forward_rows=walk_forward_rows,
        parameter_grid_rows=parameter_grid_rows,
        cost_stress_rows=cost_stress_rows,
        regime_rows=regime_rows,
        artifact_paths=artifact_paths,
    )

    summary_json_path = output_dir / "robustness_summary.json"
    summary_payload = {
        "experiment_id": experiment_id,
        "baseline_metrics": baseline.metrics,
        "aggregated_metrics": aggregated_metrics,
        "walk_forward_results": walk_forward_rows,
        "parameter_grid_results": parameter_grid_rows,
        "cost_stress_results": cost_stress_rows,
        "regime_results": regime_rows,
        "artifact_paths": [str(path) for path in artifact_paths],
        "report_path": str(report_path),
    }
    summary_json_path.write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return RobustnessResult(
        baseline_metrics=baseline.metrics,
        aggregated_metrics=aggregated_metrics,
        walk_forward_results=walk_forward_rows,
        parameter_grid_results=parameter_grid_rows,
        cost_stress_results=cost_stress_rows,
        regime_results=regime_rows,
        report_path=report_path,
        summary_json_path=summary_json_path,
        artifact_paths=artifact_paths,
    )
