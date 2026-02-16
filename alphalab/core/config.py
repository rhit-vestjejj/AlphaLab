"""Configuration models and YAML loading."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from alphalab.core.utils.errors import ConfigLoadError


class DataConfig(BaseModel):
    """Data settings for a research run."""

    provider: Literal["eodhd"] = "eodhd"
    symbols: list[str] = Field(min_length=1)
    start: date
    end: date
    cache_dir: Path = Path("../data/cache")

    @model_validator(mode="after")
    def validate_dates_and_symbols(self) -> DataConfig:
        """Ensure date boundaries and symbols are valid."""
        if self.start > self.end:
            raise ValueError("data.start must be before or equal to data.end.")
        normalized_symbols = [symbol.strip() for symbol in self.symbols if symbol.strip()]
        if not normalized_symbols:
            raise ValueError("data.symbols must contain at least one non-empty symbol.")
        self.symbols = normalized_symbols
        return self


class StrategyConfig(BaseModel):
    """Strategy configuration."""

    module: str = "alphalab.strategies.examples.trend_following"
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_module(self) -> StrategyConfig:
        """Ensure strategy module path is valid."""
        if not self.module.strip():
            raise ValueError("strategy.module must be a non-empty import path.")
        return self


class BacktestConfig(BaseModel):
    """Backtest engine configuration."""

    transaction_cost_bps: float = 5.0
    leverage_cap: float = 1.0
    max_position: float = 1.0
    annualization_factor: int = 252

    @model_validator(mode="after")
    def validate_backtest(self) -> BacktestConfig:
        """Validate deterministic backtest constraints."""
        if self.transaction_cost_bps < 0:
            raise ValueError("backtest.transaction_cost_bps must be >= 0.")
        if self.leverage_cap <= 0:
            raise ValueError("backtest.leverage_cap must be > 0.")
        if self.max_position <= 0:
            raise ValueError("backtest.max_position must be > 0.")
        if self.annualization_factor <= 0:
            raise ValueError("backtest.annualization_factor must be > 0.")
        return self


class OutputConfig(BaseModel):
    """Output and artifact settings."""

    artifacts_dir: Path = Path("../artifacts")
    save_equity_plot: bool = True
    equity_plot_filename: str = "equity_curve.png"

    @model_validator(mode="after")
    def validate_output(self) -> OutputConfig:
        """Ensure output filenames are valid."""
        if not self.equity_plot_filename.strip():
            raise ValueError("output.equity_plot_filename must be non-empty.")
        return self


class RobustnessConfig(BaseModel):
    """Robustness suite configuration."""

    walk_forward_splits: int = 4
    parameter_grid: dict[str, list[Any]] = Field(default_factory=dict)
    cost_stress_bps: list[float] = Field(default_factory=lambda: [0.0, 5.0, 10.0, 25.0, 50.0])
    volatility_window: int = 20
    trend_window: int = 50

    @model_validator(mode="after")
    def validate_robustness(self) -> RobustnessConfig:
        """Validate robustness settings."""
        if self.walk_forward_splits < 2:
            raise ValueError("robustness.walk_forward_splits must be >= 2.")
        if self.volatility_window < 2:
            raise ValueError("robustness.volatility_window must be >= 2.")
        if self.trend_window < 2:
            raise ValueError("robustness.trend_window must be >= 2.")
        if not self.cost_stress_bps:
            raise ValueError("robustness.cost_stress_bps must contain at least one value.")
        if any(value < 0 for value in self.cost_stress_bps):
            raise ValueError("robustness.cost_stress_bps values must be >= 0.")
        for key, values in self.parameter_grid.items():
            if not key.strip():
                raise ValueError("robustness.parameter_grid keys must be non-empty.")
            if not isinstance(values, list) or not values:
                raise ValueError(
                    f"robustness.parameter_grid['{key}'] must be a non-empty list of values."
                )
        return self


class ExperimentsConfig(BaseModel):
    """Experiment tracking configuration."""

    db_path: Path = Path("../data/experiments.sqlite")
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_experiments(self) -> ExperimentsConfig:
        """Validate experiment settings."""
        normalized_tags = sorted({tag.strip() for tag in self.tags if tag.strip()})
        self.tags = normalized_tags
        return self


class AppConfig(BaseModel):
    """Top-level application configuration."""

    data: DataConfig
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    robustness: RobustnessConfig = Field(default_factory=RobustnessConfig)
    experiments: ExperimentsConfig = Field(default_factory=ExperimentsConfig)


def _resolve_config_path(path: Path) -> Path:
    """Resolve and validate a config file path."""
    resolved_path = path.expanduser().resolve()
    if not resolved_path.exists():
        raise ConfigLoadError(f"Config file not found: {resolved_path}")
    if not resolved_path.is_file():
        raise ConfigLoadError(f"Config path is not a file: {resolved_path}")
    return resolved_path


def load_config(path: Path) -> AppConfig:
    """
    Load and validate application config from YAML.

    Relative paths are resolved from the YAML file parent directory.

    Args:
        path: YAML config file path.

    Returns:
        Validated application config.
    """
    config_path = _resolve_config_path(path)
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            raw_config: Any = yaml.safe_load(handle) or {}
    except OSError as exc:
        raise ConfigLoadError(f"Failed to read config file {config_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"Invalid YAML in config file {config_path}: {exc}") from exc

    if not isinstance(raw_config, dict):
        raise ConfigLoadError("YAML root must be a mapping/object.")

    return _build_config(raw_config, config_path.parent)


def _build_config(raw_config: dict[str, Any], base_dir: Path) -> AppConfig:
    """Build and path-resolve config from raw data."""
    try:
        config = AppConfig.model_validate(raw_config)
    except Exception as exc:
        raise ConfigLoadError(f"Config validation failed: {exc}") from exc
    cache_dir = config.data.cache_dir
    resolved_cache_dir = (
        cache_dir.expanduser().resolve()
        if cache_dir.is_absolute()
        else (base_dir / cache_dir).resolve()
    )
    artifacts_dir = config.output.artifacts_dir
    resolved_artifacts_dir = (
        artifacts_dir.expanduser().resolve()
        if artifacts_dir.is_absolute()
        else (base_dir / artifacts_dir).resolve()
    )
    db_path = config.experiments.db_path
    resolved_db_path = (
        db_path.expanduser().resolve() if db_path.is_absolute() else (base_dir / db_path).resolve()
    )

    updated_data = config.data.model_copy(update={"cache_dir": resolved_cache_dir})
    updated_output = config.output.model_copy(update={"artifacts_dir": resolved_artifacts_dir})
    updated_experiments = config.experiments.model_copy(update={"db_path": resolved_db_path})
    return config.model_copy(
        update={"data": updated_data, "output": updated_output, "experiments": updated_experiments}
    )


def load_config_from_yaml_text(yaml_text: str, base_dir: Path | None = None) -> AppConfig:
    """
    Load and validate config from YAML text.

    Args:
        yaml_text: YAML string.
        base_dir: Base directory for relative paths.

    Returns:
        Validated application config.
    """
    try:
        raw_config: Any = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"Invalid YAML text: {exc}") from exc
    if not isinstance(raw_config, dict):
        raise ConfigLoadError("YAML root must be a mapping/object.")
    resolved_base_dir = (base_dir or Path.cwd()).expanduser().resolve()
    return _build_config(raw_config, resolved_base_dir)


def dump_config_to_yaml(config: AppConfig) -> str:
    """
    Serialize config to canonical YAML for reproducibility.

    Args:
        config: App config.

    Returns:
        YAML string.
    """
    payload = config.model_dump(mode="json")
    return yaml.safe_dump(payload, sort_keys=True, default_flow_style=False)
