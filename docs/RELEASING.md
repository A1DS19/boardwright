# Releasing Boardwright to PyPI

This is the actual checklist for shipping a release. Treat the order as load-bearing.

## One-time setup

1. **Create PyPI accounts** on both:
   - https://test.pypi.org/account/register/ (for staging — recommended for the first ever upload)
   - https://pypi.org/account/register/ (for production)
2. **Enable 2FA** on both accounts. Required for new accounts.
3. **Create API tokens** under each account → "Account settings" → "API tokens":
   - Scope each token to `boardwright` once the project exists. For the *first* upload, scope to "Entire account" — narrow it down after.
4. **Save the tokens** in `~/.pypirc`:
   ```ini
   [pypi]
   username = __token__
   password = pypi-AgEIcHlwaS5vcmcCJDAxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3OAACKlszLCJjMjVjMjUtMjVjMi0yNWMyLTI1YzItMjVjMjI1YzIyNWMyIl0AAAYg...

   [testpypi]
   repository = https://test.pypi.org/legacy/
   username = __token__
   password = pypi-AgENd...
   ```
   Make sure `~/.pypirc` is `chmod 600`.

## Pre-flight checks

Run from the project root:

```bash
# All tests pass on the current Python
pytest tests/ -v

# Lint clean (advisory but worth a look)
ruff check boardwright/

# Tool counts haven't drifted
python3 -c "from boardwright import dispatcher; print(len(dispatcher.ALL_HANDLERS), 'handlers')"
```

## Bumping the version

Boardwright follows semver. Pre-1.0 means breaking changes can land on minor bumps; we still avoid them gratuitously.

1. Edit `pyproject.toml` and bump `version = "X.Y.Z"`.
2. (Optional but strongly recommended) Add a one-line entry to `CHANGELOG.md` under a new dated heading.
3. Commit:
   ```bash
   git add pyproject.toml CHANGELOG.md
   git commit -m "release: vX.Y.Z"
   git tag vX.Y.Z
   ```
4. **Do not push the tag yet.** Push after the upload succeeds.

## Building

```bash
# Clean prior artifacts (manually inspect first; do not blind-rm)
ls dist/ build/ *.egg-info 2>/dev/null
rm -rf dist/ build/ *.egg-info

# Build sdist + wheel
python3 -m build
```

Expected output: `dist/boardwright-X.Y.Z.tar.gz` and `dist/boardwright-X.Y.Z-py3-none-any.whl`.

## Validation

```bash
# Lint the artifacts (catches missing README, bad metadata, broken description)
python3 -m twine check dist/*

# Smoke-test the wheel in a fresh venv
python3 -m venv /tmp/bw-smoke
/tmp/bw-smoke/bin/pip install dist/boardwright-X.Y.Z-py3-none-any.whl
/tmp/bw-smoke/bin/python -c "from boardwright import TOOLS; print(len(TOOLS), 'tools')"
# Expected: 21 (17 direct + 4 router meta-tools) as of 0.3.0
rm -rf /tmp/bw-smoke
```

If any of these fail, **do not upload**. Fix the issue, re-tag, re-build.

## Upload to TestPyPI first (always, for major releases)

```bash
python3 -m twine upload --repository testpypi dist/*
```

Then verify the install path works for a real user:

```bash
python3 -m venv /tmp/bw-test
/tmp/bw-test/bin/pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  boardwright
/tmp/bw-test/bin/python -c "from boardwright import TOOLS; print(len(TOOLS))"
rm -rf /tmp/bw-test
```

The `--extra-index-url` is required because TestPyPI doesn't mirror dependencies (mcp, kicad-python, etc.).

## Upload to production PyPI

Once TestPyPI validates:

```bash
python3 -m twine upload dist/*
```

That's it. The package is live within 1–2 minutes.

## After a successful upload

```bash
git push origin main
git push origin vX.Y.Z
```

Then **draft a GitHub Release** at https://github.com/A1DS19/boardwright/releases/new, attaching the tag. Paste the CHANGELOG entry as the release notes. Optionally upload the `.tar.gz` and `.whl` from `dist/` so the release page mirrors the artifacts.

## If something goes wrong

PyPI uploads are **immutable**. You cannot replace `boardwright-X.Y.Z`. You must:

1. Yank the broken release on PyPI (Account settings → boardwright → Manage → Yank release X.Y.Z). Yanking hides it from `pip install boardwright` but leaves it for users who pinned.
2. Bump to `X.Y.Z+1` and re-release with the fix. Never reuse a version number.

For pre-release iteration use `0.3.0a1`, `0.3.0a2`, `0.3.0rc1` — these don't compete with the eventual `0.3.0`.

## What this checklist intentionally skips

- **Signed releases (sigstore / GPG).** Not worth the friction at our scale yet. Revisit when we have >1000 downloads / week.
- **Automated CI release pipelines.** Manual is fine for one maintainer at <weekly cadence. The day this becomes a chore, wire up `pypa/gh-action-pypi-publish` with trusted publishing — no API token in the runner.
- **Homebrew formula.** Filed under "after the validation gate passes" in `docs/PROJECT.md`. PyPI first.
