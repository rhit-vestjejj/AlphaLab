# AlphaLab

AlphaLab is a local, CLI-driven Python research program for systematic daily futures strategy development.

Current scope (V1):
- Project structure
- EODHD data provider abstraction
- Parquet caching
- EODHD hardening:
  - Retry/backoff on transient API failures
  - Strict vendor schema/integrity checks
- YAML configuration via pydantic
- Strategy interface + dynamic loader
- Deterministic daily backtest engine
- Required performance metrics
- Robustness suite:
  - Walk-forward splits
  - Parameter grid sensitivity
  - Cost stress tests
  - Regime split analysis
- Unit and integration tests for:
  - PnL, costs, turnover, drawdown
  - Provider retries/schema validation
  - Cache range coverage behavior
  - CLI run/list/show/robustness flow
  - API health/run/list/show workflow
  - Typed exit-code and failure-manifest behavior
- Typer CLI with `run`, `robustness`, `list`, `show` command surface
- FastAPI service with:
  - `GET /` (dashboard UI)
  - `GET /health`
  - `GET /experiments`
  - `GET /experiments/{experiment_id}`
  - `POST /runs`
  - `POST /robustness`
  - `POST /jobs/runs`
  - `POST /jobs/robustness`
  - `GET /jobs/{job_id}`
  - `GET /jobs`

Master spec status:
- [x] Pull ES/CL/GC daily futures from EODHD
- [x] Cache locally in Parquet
- [x] Run strategy backtest
- [x] Generate metrics and plots
- [x] Run robustness tests
- [x] Store experiments in SQLite
- [x] Reproduce via stored config (`run --experiment`)

CLI examples:
- `./.venv/bin/alphalab run --config alphalab/configs/example.yaml`
- `./.venv/bin/alphalab run --experiment exp_001 --db-path alphalab/data/experiments.sqlite`
- `./.venv/bin/alphalab robustness --experiment exp_001 --db-path alphalab/data/experiments.sqlite`
- `./.venv/bin/alphalab list --db-path alphalab/data/experiments.sqlite`
- `./.venv/bin/alphalab show --experiment exp_001 --db-path alphalab/data/experiments.sqlite`
- `./.venv/bin/alphalab-api` (defaults to `127.0.0.1:8020`, auto-falls forward if occupied)
- dashboard at `http://127.0.0.1:8020/`

Quality workflow:
- Install dev tooling: `make install-dev`
- Format code: `make format`
- Run checks: `make check`
- CI runs `black --check`, `ruff check`, and `unittest` on Python 3.11 and 3.12.

Release workflow:
- Release checklist: `RELEASE.md`
- Contribution guide: `CONTRIBUTING.md`
- Local pre-release gate: `make release-check`
- Tag release: `git tag -a vX.Y.Z -m "AlphaLab vX.Y.Z" && git push origin vX.Y.Z`
- GitHub release workflow validates version/changelog, runs quality checks, builds `dist/*`, and publishes a release.

Operations workflow:
- Runtime reliability and failure triage: `OPERATIONS.md`
- Command manifests:
  - `run_manifest.json` for `run`
  - `robustness_manifest.json` for `robustness`

Agent workflow:
- Project-level agent guide: `AGENTS.md`
- Role profiles: `agents/` (`implementer`, `reviewer`, `qa`, `release`)
