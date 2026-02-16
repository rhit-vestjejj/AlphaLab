"""Deterministic daily backtest engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from alphalab.core.backtest.metrics import calculate_metrics
from alphalab.core.backtest.types import BacktestResult
from alphalab.core.research.strategy import StrategyDefinition
from alphalab.core.utils.errors import BacktestError, StrategyError


def _validate_market_data(
    symbol: str,
    frame: pd.DataFrame,
    required_columns: list[str],
) -> pd.DataFrame:
    """Validate and normalize symbol market data before backtest execution."""
    if frame.empty:
        raise BacktestError(f"Market data for symbol '{symbol}' is empty.")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise BacktestError(f"Market data for symbol '{symbol}' must use DatetimeIndex.")

    normalized = frame.sort_index().copy()
    missing = [column for column in required_columns if column not in normalized.columns]
    if missing:
        raise BacktestError(
            f"Market data for symbol '{symbol}' is missing required columns: {missing}"
        )

    return normalized


def _normalize_positions(
    positions: pd.Series,
    index: pd.DatetimeIndex,
    max_position: float,
    symbol: str,
) -> pd.Series:
    """Normalize strategy positions to numeric bounded values aligned to index."""
    if not isinstance(positions, pd.Series):
        raise StrategyError(f"Strategy generate_positions() must return pd.Series for '{symbol}'.")
    if not positions.index.equals(index):
        positions = positions.reindex(index)

    normalized = pd.to_numeric(positions, errors="coerce").fillna(0.0).astype(float)
    return normalized.clip(lower=-max_position, upper=max_position)


def run_backtest(
    data_by_symbol: Mapping[str, pd.DataFrame],
    strategy: StrategyDefinition,
    strategy_params: dict[str, Any],
    transaction_cost_bps: float,
    leverage_cap: float,
    max_position: float,
    annualization_factor: int = 252,
) -> BacktestResult:
    """
    Run a deterministic multi-symbol daily backtest.

    Execution model:
    - Signals are generated on day ``t``.
    - Trades are executed at next-day close (``t+1`` close).
    - PnL is based on close-to-close return and lagged positions.

    Args:
        data_by_symbol: Mapping of symbol to normalized OHLCV dataframe.
        strategy: Strategy definition.
        strategy_params: Strategy parameter dictionary.
        transaction_cost_bps: Fixed transaction cost in basis points.
        leverage_cap: Max gross exposure cap across all symbols.
        max_position: Max absolute position per symbol.
        annualization_factor: Trading-day annualization factor.

    Returns:
        Backtest result container.
    """
    if not data_by_symbol:
        raise BacktestError("At least one symbol dataset is required for backtest.")
    if leverage_cap <= 0:
        raise BacktestError("leverage_cap must be greater than 0.")
    if max_position <= 0:
        raise BacktestError("max_position must be greater than 0.")
    if transaction_cost_bps < 0:
        raise BacktestError("transaction_cost_bps must be non-negative.")
    if annualization_factor <= 0:
        raise BacktestError("annualization_factor must be greater than 0.")

    required_columns = strategy.required_columns()
    close_returns_map: dict[str, pd.Series] = {}
    signal_positions_map: dict[str, pd.Series] = {}

    for symbol in sorted(data_by_symbol):
        frame = _validate_market_data(symbol, data_by_symbol[symbol], required_columns)
        raw_positions = strategy.generate_positions(frame, dict(strategy_params))
        signal_positions = _normalize_positions(raw_positions, frame.index, max_position, symbol)
        close_returns = frame["close"].astype(float).pct_change().fillna(0.0)

        signal_positions_map[symbol] = signal_positions
        close_returns_map[symbol] = close_returns

    signal_positions_df = pd.DataFrame(signal_positions_map).sort_index().fillna(0.0)
    close_returns_df = (
        pd.DataFrame(close_returns_map).reindex(signal_positions_df.index).fillna(0.0)
    )

    gross_exposure_uncapped = signal_positions_df.abs().sum(axis=1)
    leverage_scaler = pd.Series(1.0, index=signal_positions_df.index)
    over_cap_mask = gross_exposure_uncapped > leverage_cap
    leverage_scaler.loc[over_cap_mask] = leverage_cap / gross_exposure_uncapped.loc[over_cap_mask]

    signal_positions_capped = signal_positions_df.mul(leverage_scaler, axis=0)
    executed_positions = signal_positions_capped.shift(1).fillna(0.0)

    gross_returns = (executed_positions * close_returns_df).sum(axis=1)

    turnover = signal_positions_capped.diff().abs().sum(axis=1)
    if not turnover.empty:
        turnover.iloc[0] = float(signal_positions_capped.iloc[0].abs().sum())

    transaction_cost_rate = transaction_cost_bps / 10_000.0
    net_returns = gross_returns - turnover * transaction_cost_rate
    equity_curve = (1.0 + net_returns).cumprod()

    gross_exposure = signal_positions_capped.abs().sum(axis=1)
    metrics = calculate_metrics(
        daily_returns=net_returns,
        equity_curve=equity_curve,
        turnover=turnover,
        gross_exposure=gross_exposure,
        annualization_factor=annualization_factor,
    )

    exposure_stats = {
        "average_gross_exposure": float(gross_exposure.mean()) if not gross_exposure.empty else 0.0,
        "max_gross_exposure": float(gross_exposure.max()) if not gross_exposure.empty else 0.0,
        "average_net_exposure": (
            float(signal_positions_capped.sum(axis=1).mean())
            if not signal_positions_capped.empty
            else 0.0
        ),
    }
    turnover_stats = {
        "average_daily_turnover": float(turnover.mean()) if not turnover.empty else 0.0,
        "max_daily_turnover": float(turnover.max()) if not turnover.empty else 0.0,
    }

    return BacktestResult(
        daily_returns=net_returns.astype(float),
        equity_curve=equity_curve.astype(float),
        positions=signal_positions_capped.astype(float),
        turnover=turnover.astype(float),
        metrics=metrics,
        exposure_stats=exposure_stats,
        turnover_stats=turnover_stats,
    )
