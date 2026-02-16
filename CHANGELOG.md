# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

### Added
- FastAPI API layer for local frontend/client integration:
  - `GET /health`
  - `GET /experiments`
  - `GET /experiments/{experiment_id}`
  - `POST /runs`
  - `POST /robustness`
- Async API job queue endpoints for non-blocking execution:
  - `POST /jobs/runs`
  - `POST /jobs/robustness`
  - `GET /jobs/{job_id}`
  - `GET /jobs`
- Local frontend dashboard scaffold served by FastAPI:
  - `GET /` dashboard page
  - queue run/robustness jobs
  - live job polling
  - experiment list/detail view
- Service-layer workflow module shared by API use-cases.
- API integration tests using ASGI transport.
- Typed robustness validation errors (`RobustnessError`) for deterministic CLI exit handling.
- CLI failure-path integration tests covering typed exit codes and failure manifest generation.
- Expanded top-level documentation with quickstart and full-product status checklist.

## [0.1.0] - 2026-02-16

### Added
- Local data provider abstraction and EODHD integration with Parquet caching.
- Deterministic backtest engine with required performance metrics.
- Robustness suite (walk-forward, parameter grid, cost stress, regime splits).
- SQLite experiment tracking with `run`, `list`, `show`, and `robustness` CLI flows.
- Local and CI quality gates (`black`, `ruff`, `unittest`).
- Agent role profiles and repository-level agent operating guide.
