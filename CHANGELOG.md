# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

### Added
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
