"""Backtest metrics calculations."""

from __future__ import annotations

import math

import pandas as pd


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    """
    Calculate max drawdown from an equity curve.

    Args:
        equity_curve: Cumulative equity curve where 1.0 is starting equity.

    Returns:
        Minimum drawdown as a negative decimal.
    """
    if equity_curve.empty:
        return 0.0

    running_max = equity_curve.cummax()
    drawdowns = equity_curve / running_max - 1.0
    return float(drawdowns.min())


def calculate_metrics(
    daily_returns: pd.Series,
    equity_curve: pd.Series,
    turnover: pd.Series,
    gross_exposure: pd.Series,
    annualization_factor: int = 252,
) -> dict[str, float]:
    """
    Calculate required deterministic performance metrics.

    Args:
        daily_returns: Daily net return series.
        equity_curve: Cumulative equity curve.
        turnover: Daily turnover series.
        gross_exposure: Daily gross exposure series.
        annualization_factor: Trading-day annualization factor.

    Returns:
        Metrics dictionary.
    """
    sample_size = int(daily_returns.shape[0])
    if sample_size == 0:
        return {
            "annualized_return": 0.0,
            "annualized_volatility": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "calmar_ratio": 0.0,
            "average_daily_turnover": 0.0,
            "average_gross_exposure": 0.0,
            "percentage_positive_days": 0.0,
        }

    final_equity = float(equity_curve.iloc[-1])
    annualized_return = final_equity ** (annualization_factor / sample_size) - 1.0
    annualized_volatility = float(daily_returns.std(ddof=0) * math.sqrt(annualization_factor))
    sharpe_ratio = annualized_return / annualized_volatility if annualized_volatility > 0 else 0.0
    max_drawdown = calculate_max_drawdown(equity_curve)
    calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown < 0 else 0.0

    positive_days = float((daily_returns > 0.0).mean())

    return {
        "annualized_return": float(annualized_return),
        "annualized_volatility": annualized_volatility,
        "sharpe_ratio": float(sharpe_ratio),
        "max_drawdown": float(max_drawdown),
        "calmar_ratio": float(calmar_ratio),
        "average_daily_turnover": float(turnover.mean()) if not turnover.empty else 0.0,
        "average_gross_exposure": float(gross_exposure.mean()) if not gross_exposure.empty else 0.0,
        "percentage_positive_days": positive_days,
    }
