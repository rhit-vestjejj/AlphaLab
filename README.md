# AlphaLab

AlphaLab is a local, CLI-driven Python research program for systematic daily futures strategy development.

It is a research engine, not a live trading or broker execution system.

## What It Can Do Now

- Fetch daily futures data from EODHD (`ES`, `CL`, `GC`) via a provider abstraction.
- Cache normalized OHLCV data in local Parquet files.
- Run deterministic multi-symbol backtests with transaction costs, turnover, and exposure controls.
- Compute required performance metrics.
- Run robustness suites (walk-forward, parameter grid, cost stress, regime splits).
- Persist and query experiments in SQLite (`run`, `list`, `show`, re-run by `--experiment`).
- Emit run manifests and typed failure exit codes for operational reliability.
- Expose core workflows over a local FastAPI service for frontend/API clients.

## Quickstart

1. Create a virtual environment and install dependencies.
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
   - `make install-dev`
2. Configure environment variables.
   - `cp .env.example .env`
   - Set `EODHD_API_KEY=...` in `.env`
3. Run a baseline experiment.
   - `./.venv/bin/alphalab run --config alphalab/configs/example.yaml`
4. Inspect experiments.
   - `./.venv/bin/alphalab list --db-path alphalab/data/experiments.sqlite`
   - `./.venv/bin/alphalab show --experiment <id> --db-path alphalab/data/experiments.sqlite`
5. Run robustness on an experiment.
   - `./.venv/bin/alphalab robustness --experiment <id> --db-path alphalab/data/experiments.sqlite`
6. Start the local API server.
   - `./.venv/bin/alphalab-api`
   - Open `http://127.0.0.1:8020/docs`
   - If `8020` is occupied, the launcher auto-selects the next free port.

## API Endpoints

- `GET /health`
- `GET /experiments?db_path=...&limit=...`
- `GET /experiments/{experiment_id}?db_path=...`
- `POST /runs` with JSON body:
  - `{"config_path":"...","db_path":"..."}` or `{"source_experiment_id":"...","db_path":"..."}`
- `POST /robustness` with JSON body:
  - `{"experiment_id":"...","db_path":"..."}`

## Product Status

- [x] Data abstraction and EODHD provider
- [x] Deterministic Parquet caching
- [x] YAML config loading and validation
- [x] Strategy interface and loader
- [x] Deterministic backtest engine + required metrics
- [x] Robustness suite + artifacts
- [x] Experiment tracking and reproducible re-runs
- [x] CLI command surface (`run`, `robustness`, `list`, `show`)
- [x] Local API layer for frontend integration
- [x] CI, release workflow, and quality gates

## Documentation

- Core docs: `alphalab/README.md`
- Operations and runtime diagnostics: `OPERATIONS.md`
- Contribution guide: `CONTRIBUTING.md`
- Release process: `RELEASE.md`
- Agent workflow: `AGENTS.md` and `agents/`
