# Repository Guidelines

## Project Structure & Module Organization
This repository is currently a minimal Python project managed with `uv`. Today, the tracked files are:
- `pyproject.toml`: project metadata and dev tooling dependencies.
- `uv.lock`: locked dependency graph.

When adding code, follow a standard layout:
- `src/homi/` for application modules.
- `tests/` for automated tests.
- `assets/` for non-code resources if needed.

Keep modules small and focused (one responsibility per file), and mirror source paths in tests (for example, `src/homi/api/client.py` -> `tests/api/test_client.py`).

## Build, Test, and Development Commands
- `uv sync --dev`: install runtime and development dependencies.
- `uv run black .`: format Python code.
- `uv run isort .`: normalize import ordering.
- `uv run pre-commit run --all-files`: run all configured repository hooks.

No application entrypoint or packaging workflow is currently defined. Add project-specific run/build commands here as soon as they are introduced.

If a web or mobile app is added, run it locally after changes and capture a visual of the latest version. Add the exact run command here once it exists.

## Coding Style & Naming Conventions
Target Python `>=3.9` (see `pyproject.toml`). Use:
- 4-space indentation.
- `snake_case` for functions, variables, and modules.
- `PascalCase` for classes.
- clear, descriptive names over abbreviations.

Use `black` and `isort` as the source of truth for formatting. Prefer explicit type hints on public functions and keep functions short enough to read without scrolling.

## Testing Guidelines
No test framework is configured yet. Standardize on `pytest` when tests are added.
- Name files `tests/test_<module>.py`.
- Name tests `test_<behavior>()`.
- Add or update tests with every behavioral change.

Before opening a PR, run formatting/hooks locally and run tests (once configured) through `uv run`.

## Commit & Pull Request Guidelines
Existing history uses short, imperative subjects (for example, `Add ...`, `Update ...`, `Fix ...`). Follow that style:
- Keep commit subjects concise and action-oriented.
- Group related changes into a single commit when practical.

PRs should include:
- a brief summary of what changed and why.
- linked issue/ticket when applicable.
- local verification steps and outcomes.
- screenshots/log snippets for visible behavior changes.

## Security & Configuration Tips
Never commit secrets, tokens, or local credentials. Use environment variables and document required keys in project docs when new integrations are added.
