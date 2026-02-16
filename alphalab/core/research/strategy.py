"""Strategy interface utilities."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from types import ModuleType
from typing import Any

import pandas as pd

from alphalab.core.utils.errors import StrategyError

RequiredColumnsFn = Callable[[], list[str]]
GeneratePositionsFn = Callable[[pd.DataFrame, dict[str, Any]], pd.Series]


@dataclass(frozen=True)
class StrategyDefinition:
    """Validated strategy module interface."""

    strategy_name: str
    required_columns: RequiredColumnsFn
    generate_positions: GeneratePositionsFn


def _validate_required_columns(fn: RequiredColumnsFn, module_path: str) -> None:
    """Validate `required_columns` return value from a strategy module."""
    required = fn()
    if not isinstance(required, list) or not all(isinstance(value, str) for value in required):
        raise StrategyError(
            f"Strategy module '{module_path}' returned invalid required_columns(). "
            "Expected list[str]."
        )
    if not required:
        raise StrategyError(f"Strategy module '{module_path}' returned empty required_columns().")


def _load_module(module_path: str) -> ModuleType:
    """Import a strategy module by path."""
    try:
        return import_module(module_path)
    except Exception as exc:  # pragma: no cover - import errors are environment-dependent.
        raise StrategyError(f"Unable to import strategy module '{module_path}': {exc}") from exc


def load_strategy(module_path: str) -> StrategyDefinition:
    """
    Load and validate a strategy module.

    Required module attributes:
    - ``STRATEGY_NAME: str``
    - ``required_columns() -> list[str]``
    - ``generate_positions(df: pd.DataFrame, params: dict) -> pd.Series``

    Args:
        module_path: Python import path for the strategy module.

    Returns:
        Validated strategy definition.
    """
    module = _load_module(module_path)

    strategy_name = getattr(module, "STRATEGY_NAME", None)
    required_columns = getattr(module, "required_columns", None)
    generate_positions = getattr(module, "generate_positions", None)

    if not isinstance(strategy_name, str) or not strategy_name.strip():
        raise StrategyError(
            f"Strategy module '{module_path}' is missing a valid STRATEGY_NAME string."
        )
    if not callable(required_columns):
        raise StrategyError(
            f"Strategy module '{module_path}' is missing callable required_columns()."
        )
    if not callable(generate_positions):
        raise StrategyError(
            f"Strategy module '{module_path}' is missing callable generate_positions()."
        )

    _validate_required_columns(required_columns, module_path)
    return StrategyDefinition(
        strategy_name=strategy_name.strip(),
        required_columns=required_columns,
        generate_positions=generate_positions,
    )
