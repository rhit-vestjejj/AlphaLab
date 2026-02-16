"""Data structures for backtest results."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class BacktestResult:
    """Container for deterministic backtest outputs."""

    daily_returns: pd.Series
    equity_curve: pd.Series
    positions: pd.DataFrame
    turnover: pd.Series
    metrics: dict[str, float]
    exposure_stats: dict[str, float]
    turnover_stats: dict[str, float]
