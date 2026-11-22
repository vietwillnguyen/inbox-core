# Contributing

Thank you for helping.
This repository is public, so the rules below are about keeping it safe to be public as much as about code quality.

## The rules

- **No real data, ever.**
  No client data, real names, email addresses, phone numbers, URLs of real organisations, keys or internal paths anywhere, including test fixtures, examples, documentation and commit messages.
  Examples use made-up organisations and `example.com` or `.example` addresses.
- **Never commit `.env` files or credentials.**
  Stage files by name and read the staged list (`git status`, `git diff --cached --stat`) before every commit; do not use `git add -A` blindly.
  CI runs a secret scan over the full history on every push and pull request.
- **Message content never reaches a log, an exception or an audit record.**
  Log identifiers, categories, tiers, decisions and counts only.
  The privacy sweep in `inbox_core.testing` exists to catch a slip; run it against any corpus you add.
- **The tier is decided in code.**
  A classifier reports signals; `derive_tier` decides.
  Do not add any path where a model's output chooses a tier, a recipient or a delivery mode.
- **Fail closed.**
  Every failure, from a malformed classifier answer to a crashed handler, ends with a person being told, never with a guessed answer.
- **Test first.**
  Write the test, watch it fail for the right reason, then make it pass.
  Never weaken a test to make it pass, and fix a flaky test rather than retrying it.
- **No network in the test suite.**
  Model adapters are tested with fakes.
  The evaluation runners that call real models are run on demand, never in CI.

## Style

- Python 3.12 or newer, managed with `uv`.
- `ruff` for lint and format, `mypy --strict` for types, `pytest` with a 90 percent coverage floor.
- Every public symbol has a docstring.
- Use a plain hyphen, never an em dash.
- In long Markdown, put each full sentence on its own line.

## Commits

Conventional Commits: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`, `ci:`.
The description is imperative, lower-case and has no trailing period.
No co-author or attribution trailers.

## Running the checks

```sh
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov
```
