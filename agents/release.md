# Release Agent

## Objective

Confirm merge/release readiness for GitHub.

## Checklist

- CI workflow exists and is current:
  - `.github/workflows/ci.yml`
  - `.github/workflows/release.yml`
- Local gate passes:
  - `make check`
- Release gate passes:
  - `make release-check`
- README command examples reflect current CLI.
- Experiment/robustness artifacts are documented.
- No secrets are committed (`.env` excluded).

## Release Handoff

- Version/tag proposal
- Change summary
- Risk and rollback notes
