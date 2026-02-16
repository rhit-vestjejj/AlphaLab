"""Test helpers for deterministic backtest cases."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from alphalab.core.research.strategy import StrategyDefinition


def make_price_frame(close_values: Sequence[float]) -> pd.DataFrame:
    """Build deterministic OHLCV dataframe from close values."""
    index = pd.date_range("2020-01-01", periods=len(close_values), freq="D", tz="UTC")
    close = pd.Series(close_values, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1_000.0,
        },
        index=index,
    )


def strategy_from_positions(name: str, positions: Sequence[float]) -> StrategyDefinition:
    """Create a strategy definition returning fixed signal positions."""
    values = list(float(value) for value in positions)

    def required_columns() -> list[str]:
        return ["close"]

    def generate_positions(df: pd.DataFrame, params: dict[str, object]) -> pd.Series:
        if len(values) != len(df.index):
            raise ValueError("Position sequence length must match dataframe length.")
        return pd.Series(values, index=df.index, dtype=float)

    return StrategyDefinition(
        strategy_name=name,
        required_columns=required_columns,
        generate_positions=generate_positions,
    )
