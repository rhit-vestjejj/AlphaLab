# AlphaLab Agent Operating Guide

This repository supports role-based agent workflows to improve quality and reduce regressions.

## Roles

- Implementer Agent:
  - Build features and refactors.
  - Keep changes scoped to one objective.
  - Provide deterministic outputs and artifacts.
- Reviewer Agent:
  - Focus on bugs, behavior regressions, missing validations, and risk.
  - Verify error handling and edge cases.
  - Require explicit references to affected files and commands.
- QA Agent:
  - Run `make check`.
  - Execute CLI smoke paths (`run`, `list`, `show`, `robustness`).
  - Confirm artifacts and experiment DB records are created correctly.
- Release Agent:
  - Validate CI workflow and release checklist.
  - Prepare release notes and tag summary.

## Standard Agent Loop

1. Plan the smallest complete unit of work.
2. Implement code changes.
3. Run local quality gate:
   - `make format-check`
   - `make lint`
   - `make test`
4. Run command-level smoke checks if CLI behavior changed.
5. Document results in the handoff format below.

## Handoff Format

- Scope:
- Files changed:
- Commands executed:
- Results:
- Risks/open follow-ups:

## Done Criteria

- `make check` passes.
- New behavior has tests (unit or integration).
- CLI behavior is deterministic and documented.
- No TODO stubs are introduced without an explicit follow-up note.
