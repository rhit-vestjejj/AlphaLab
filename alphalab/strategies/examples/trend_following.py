"""Simple deterministic trend-following example strategy."""

from __future__ import annotations

from typing import Any

import pandas as pd

STRATEGY_NAME: str = "trend_following"


def required_columns() -> list[str]:
    """Return required market data columns."""
    return ["close"]


def generate_positions(df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
    """
    Generate positions from normalized momentum signal.

    Signal uses close-to-close lookback return at date ``t``.
    Backtest engine executes at next-day close, so no lookahead is introduced.

    Args:
        df: Input market data dataframe indexed by UTC datetime.
        params: Strategy parameters. Supported keys:
            - ``lookback``: integer lookback window (default 20)

    Returns:
        Position series in [-1, 1] aligned to ``df.index``.
    """
    lookback = int(params.get("lookback", 20))
    if lookback < 1:
        raise ValueError("lookback must be >= 1.")

    close = pd.to_numeric(df["close"], errors="coerce")
    momentum = close.pct_change(periods=lookback)
    signal = momentum.fillna(0.0).apply(
        lambda value: 1.0 if value > 0 else (-1.0 if value < 0 else 0.0)
    )

    positions = signal.astype(float).clip(lower=-1.0, upper=1.0)
    return positions.reindex(df.index).fillna(0.0)
