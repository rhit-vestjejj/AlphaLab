"""Domain-specific error taxonomy for AlphaLab."""

from __future__ import annotations


class AlphaLabError(Exception):
    """Base AlphaLab error with CLI exit-code metadata."""

    exit_code: int = 1
    error_code: str = "alphalab_error"


class ConfigLoadError(AlphaLabError, ValueError):
    """Configuration loading/validation error."""

    exit_code = 2
    error_code = "config_error"


class DataFetchError(AlphaLabError, ConnectionError):
    """Data fetch transport/retry error."""

    exit_code = 3
    error_code = "data_fetch_error"


class DataValidationError(AlphaLabError, ValueError):
    """Data schema/integrity validation error."""

    exit_code = 4
    error_code = "data_validation_error"


class CacheError(AlphaLabError, RuntimeError):
    """Cache read/write error."""

    exit_code = 5
    error_code = "cache_error"


class StrategyError(AlphaLabError, ValueError):
    """Strategy loading/execution error."""

    exit_code = 6
    error_code = "strategy_error"


class BacktestError(AlphaLabError, ValueError):
    """Backtest execution error."""

    exit_code = 7
    error_code = "backtest_error"


class ExperimentStoreError(AlphaLabError, ValueError):
    """Experiment tracking storage/query error."""

    exit_code = 8
    error_code = "experiment_store_error"


class RobustnessError(AlphaLabError, ValueError):
    """Robustness suite execution error."""

    exit_code = 9
    error_code = "robustness_error"


class ArtifactError(AlphaLabError, RuntimeError):
    """Artifact write/read error."""

    exit_code = 10
    error_code = "artifact_error"


def exit_code_for_exception(exc: Exception) -> int:
    """
    Resolve process exit code for an exception.

    Args:
        exc: Raised exception.

    Returns:
        Integer process exit code.
    """
    return int(getattr(exc, "exit_code", 1))
