# Operations Guide

This document describes runtime reliability behavior for AlphaLab CLI commands.

## Error Taxonomy

AlphaLab raises typed domain errors with deterministic CLI exit codes.

- `ConfigLoadError` -> `2`
- `DataFetchError` -> `3`
- `DataValidationError` -> `4`
- `CacheError` -> `5`
- `StrategyError` -> `6`
- `BacktestError` -> `7`
- `ExperimentStoreError` -> `8`
- `RobustnessError` -> `9`
- `ArtifactError` -> `10`
- untyped/unknown errors -> `1`

## Data Provider Retry Policy

`EODHDProvider` uses deterministic exponential backoff for transient failures.

- Retryable status codes: `429`, `500`, `502`, `503`, `504`
- Parameters:
  - `max_retries` (default `3`)
  - `retry_backoff_seconds` (default `0.5`)
- Delay sequence: `base * 2^attempt`

Schema and integrity validations are enforced before data is accepted.

## Run Manifests

Each `run` and `robustness` command writes a manifest JSON artifact containing:

- command metadata (`run_id`, start/finish timestamps, duration)
- environment metadata (python/platform)
- inputs (config path, source experiment id, db path)
- execution context (strategy, symbols, date range)
- result metrics and artifact paths (on success)
- exception type/message/traceback (on failure)

Manifest files:

- `run_manifest.json` for `alphalab run`
- `robustness_manifest.json` for `alphalab robustness`

## Failure Triage

1. Inspect CLI output for typed exit behavior and manifest path.
2. Open the generated manifest and review:
   - `failure.exception_type`
   - `failure.message`
   - `failure.traceback`
3. Reproduce with the exact command/config from manifest `inputs`.
4. Validate environment and config before code changes.
