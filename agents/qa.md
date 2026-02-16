# QA Agent

## Objective

Execute deterministic quality and smoke checks.

## Required Checks

- `make check`
- CLI help:
  - `./.venv/bin/alphalab --help`
- If data/backtest paths changed, run:
  - `./.venv/bin/alphalab run --config alphalab/configs/example.yaml`
- If robustness/experiments changed, run:
  - `./.venv/bin/alphalab list --db-path alphalab/data/experiments.sqlite`
  - `./.venv/bin/alphalab show --experiment <id> --db-path alphalab/data/experiments.sqlite`
  - `./.venv/bin/alphalab robustness --experiment <id> --db-path alphalab/data/experiments.sqlite`

## Handoff

- Commands executed
- Pass/fail summary
- Any reproducible failures with exact command and output
