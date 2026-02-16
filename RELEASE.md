# Release Checklist

Use this checklist before tagging a release.

## Pre-Release

- [ ] `make check` passes locally.
- [ ] `CHANGELOG.md` has a new version section with release notes.
- [ ] `pyproject.toml` version matches release target.
- [ ] No secrets or local environment files are tracked.
- [ ] CLI help and README examples reflect current behavior.

## Tag and Publish

1. Create annotated tag:
   - `git tag -a vX.Y.Z -m "AlphaLab vX.Y.Z"`
2. Push tag:
   - `git push origin vX.Y.Z`
3. Verify GitHub release workflow succeeds:
   - Tag/version match check
   - Quality checks
   - Build artifacts (`sdist`, `wheel`)
   - GitHub Release creation with attached artifacts

## Post-Release

- [ ] Validate release notes on GitHub.
- [ ] Confirm downloadable artifacts are present.
- [ ] Record follow-up issues for deferred work.
