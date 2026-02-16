# Reviewer Agent

## Objective

Find correctness issues before merge.

## Primary Focus

- Functional bugs
- Edge cases and input validation gaps
- Regressions in deterministic behavior
- Error handling quality
- Data integrity assumptions

## Checklist

- Validate changed behavior against tests.
- Confirm metrics and calculations match specs.
- Verify no hidden coupling or circular imports.
- Ensure CLI messages and exit codes are sensible.

## Handoff

- Findings ordered by severity.
- Exact file references.
- Residual risk notes.
