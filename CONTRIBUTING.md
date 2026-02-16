# Contributing

This project uses a deterministic local workflow with CI parity checks.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:
   - `make install-dev`
3. Run quality gate:
   - `make check`

## Development Workflow

1. Keep changes scoped to one objective.
2. Add tests for behavior changes.
3. Run:
   - `make format-check`
   - `make lint`
   - `make test`
4. Update docs and `CHANGELOG.md` as needed.

## Pull Requests

- Use the PR template.
- Include problem statement, approach, and validation commands.
- Ensure CI passes on all supported Python versions.

## Release Workflow

1. Update `pyproject.toml` version.
2. Add release notes under a new version section in `CHANGELOG.md`.
3. Commit the version/changelog changes.
4. Create a Git tag prefixed with `v` (example: `v0.1.1`).
5. Push branch and tag.
6. GitHub Actions release workflow validates, builds artifacts, and publishes a GitHub release.
