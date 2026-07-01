## Why

The project has no test coverage anywhere and two overlapping dependency manifests (`pyproject.toml` and `requirements.txt`) that have already silently diverged — `pyspark==3.3.0` lives only in `requirements.txt` and is missing from `pyproject.toml`. Setup is driven by an imperative shell script (`setup_venv.sh`) that creates a `venv/` alongside the code, disconnected from Poetry despite Poetry being installed on the host and referenced in `pyproject.toml`.

This makes onboarding fragile (two ways to install, only one is authoritative for any given tool), blocks any future CI (no test target, no lockfile), and prevents governance work in `add-data-governance` from carrying test coverage into the pipeline.

This is currently a **design-only proposal**. DESIGN.md captures the direction (three pillars — deps / venv / tests — phased over three ship windows). Implementation begins only after user approval.

## What Changes

- Add a new `python-tooling` OpenSpec capability covering: dependency management single-source-of-truth, virtual environment location convention, and test infrastructure.
- MODIFY the existing `infrastructure` capability where tooling touches its observable behavior:
  - `setup_venv.sh` and the `venv/` directory retire; `.venv/` in-project (Poetry-managed) becomes the sole convention.
  - Six venv-related Makefile targets (`setup-venv`, `activate-venv`, `clean-venv`, `check-venv`, `install-deps`, `setup-python`) collapse into three Poetry-based targets, plus a new `make test`.
  - `infrastructure/docker/streamlit/Dockerfile` builds via Poetry instead of `pip install -r requirements.txt`.
- Retire `requirements.txt`. `pyproject.toml` becomes the single source of dependency truth, with `poetry.lock` committed for reproducibility.
- New `tests/` directory at repo root with per-codebase subpackages (`tests/spark/`, `tests/streamlit/`), Spark-session fixtures, and mock-based tests for the pure-function surface.
- Phased rollout (see DESIGN.md): Poetry migration → test infrastructure → initial tests. Each phase ships independently.

## Capabilities

### New Capabilities
- `python-tooling`: Owns dependency management (Poetry as single source of truth, lockfile committed), virtual environment convention (`.venv/` in-project), and test infrastructure (pytest layout, fixtures, `make test`, coverage targets for pure-function surfaces).

### Modified Capabilities
- `infrastructure`: Retires venv-related Makefile targets and `setup_venv.sh`; Streamlit Dockerfile builds via Poetry; new `make test` target enters the canonical target list.

## Impact

- Adds `openspec/changes/add-python-tooling/DESIGN.md`, `PROPOSAL.md`, `TASKS.md`, `specs/python-tooling/spec.md`, `specs/infrastructure/spec.md` (this turn).
- Future implementation will: add `pyspark` and a `dev` dependency group to `pyproject.toml`, add a project-local `poetry.toml` for in-project venv, commit `poetry.lock`, delete `requirements.txt` and `setup_venv.sh`, rewrite the venv-family Makefile targets, refactor `infrastructure/docker/streamlit/Dockerfile`, create `tests/spark/` and `tests/streamlit/` with `conftest.py` files, add `[tool.pytest.ini_options]` to `pyproject.toml`, and write happy-path unit tests for Spark transformers, UDFs, and UI managers.
- No code or configuration files outside this change directory are modified in this design-only turn.
- Non-goals include CI/CD, pre-commit/linter setup, e2e or Streamlit-view tests, and Python-version bumps — those are separate future changes.
