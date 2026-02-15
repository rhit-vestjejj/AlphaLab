# AlphaLab — Systematic Futures Research Program (V1 Master Spec)

You are building a local Python research program for systematic daily futures strategy development.

This is NOT:
- A trading bot
- A broker integration
- A web SaaS platform
- An options engine
- A live execution system

This IS:
- A reproducible research engine
- A backtesting framework
- An automated robustness testing system
- An experiment tracking program

Everything must run locally via CLI on Linux or macOS.

---

# Environment

- Python 3.11+
- Virtual environment required
- CLI-driven only
- No notebooks in core engine
- Full type hints
- Deterministic execution

---

# Data Source

Primary data provider:

EOD Historical Data (REST API)

Requirements:

- Implement abstract base class:

```python
class DataProvider(ABC):
    def fetch_ohlcv(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        ...
```

- Implement:

```python
class EODHDProvider(DataProvider):
    ...
```

- Cache all fetched data as Parquet:
  data/cache/{symbol}.parquet

- If cached data exists and covers requested range, do not re-fetch.
- Normalize output to:
  - UTC datetime index
  - Columns: open, high, low, close, volume

Assume continuous back-adjusted contracts are provided by vendor.
Do NOT implement roll logic.

Initial symbols:

- ES
- CL
- GC

Daily frequency only.

---

# Strategy Interface

Each strategy module must contain:

```python
STRATEGY_NAME: str

def required_columns() -> list[str]:
    ...

def generate_positions(df: pd.DataFrame, params: dict) -> pd.Series:
    ...
```

Rules:

- No lookahead bias
- Execution assumption: next-day close
- Positions scaled between -1 and +1 unless otherwise specified
- Positions must align to dataframe index

---

# Backtest Engine

Must support:

- Daily frequency
- Execution at next-day close
- Fixed bps transaction cost
- Turnover calculation
- Leverage cap
- Max position constraint

Outputs:

- Daily returns
- Equity curve
- Metrics dict
- Exposure stats
- Turnover stats

---

# Required Metrics

- Annualized return
- Annualized volatility
- Sharpe ratio (rf=0)
- Max drawdown
- Calmar ratio
- Average daily turnover
- Average gross exposure
- Percentage positive days

All deterministic.

---

# Robustness Suite

Automatically run:

- Walk-forward split
- Parameter grid sensitivity
- Cost stress test (0 / 5 / 10 / 25 / 50 bps)
- Regime splits:
  - High vs low volatility
  - Trend vs non-trend proxy

Output:

- Aggregated metrics
- Markdown report
- Plots saved to artifacts/{experiment_id}/

---

# Experiment Tracking

Store each run in SQLite with:

- experiment_id
- timestamp
- strategy_name
- config_yaml
- metrics_json
- artifact_paths
- tags

Must support:

- List experiments
- Show experiment
- Re-run experiment from stored config

---

# CLI Commands

- alphalab run --config configs/example.yaml
- alphalab robustness --experiment <id>
- alphalab list
- alphalab show --experiment <id>

---

# Repository Structure

alphalab/
  core/
    data/
    backtest/
    research/
    experiments/
    utils/
  strategies/
    examples/
  configs/
  data/cache/
  artifacts/
  tests/
  cli.py
  README.md

---

# Coding Standards

- Type hints everywhere
- Black formatting
- Ruff linting
- Clear error handling
- Unit tests for:
  - PnL
  - Cost model
  - Turnover
  - Drawdown

---

# Success Criteria

User can:

1. Pull ES/CL/GC daily futures from EODHD
2. Cache locally
3. Run a strategy backtest
4. Generate metrics + plots
5. Run robustness tests
6. Store experiments in SQLite
7. Reproduce results via config

Everything must enforce serious quant research discipline.

---

# FIRST IMPLEMENTATION TASK

Build only:

- Project directory structure
- DataProvider base class
- EODHDProvider
- Parquet caching logic
- YAML config loader
- Basic CLI stub with "run" command
- Logging utilities

Do NOT implement backtesting yet.

Focus on clean data abstraction and local caching.
All code must be production-style and deterministic.
No notebooks.
No UI.
No shortcuts.
