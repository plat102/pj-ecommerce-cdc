## ADDED Requirements

> **Status:** Placeholder additions for the design-only phase of `add-python-tooling`. The existing `infrastructure` spec (see `openspec/specs/infrastructure/spec.md`) covers Docker Compose lifecycle but does NOT currently declare a Python-environment convention or a `make test` target. This change adds those requirements to the `infrastructure` capability so that the Makefile-level behavior is spec-visible.
>
> On archive, these requirements merge into `openspec/specs/infrastructure/spec.md` under a new subsection.

### Requirement: python-environment-convention
The canonical Python virtual environment for local development SHALL be `.venv/` at the repo root, managed by Poetry. Poetry's `virtualenvs.in-project = true` setting SHALL be pinned by a project-scoped `poetry.toml` file. `setup_venv.sh` and any `venv/` directory SHALL NOT exist as canonical entry points — `make poetry-install` is the sole setup command.

#### Scenario: fresh clone installs via Poetry
- **WHEN** a developer clones the repo and runs `make poetry-install`
- **THEN** a `.venv/` directory SHALL be created at the repo root with all main and dev dependencies from `pyproject.toml` installed

#### Scenario: no legacy venv script
- **WHEN** the repo is inspected for setup scripts
- **THEN** `setup_venv.sh` SHALL NOT exist and no Makefile target SHALL reference `venv/` (only `.venv/`)

### Requirement: makefile-poetry-targets
The Makefile SHALL provide `poetry-install`, `poetry-shell`, `poetry-clean`, and `test` targets. The retired venv-family targets (`setup-venv`, `activate-venv`, `clean-venv`, `check-venv`, `install-deps`, `setup-python`) SHALL NOT reappear.

#### Scenario: make test runs pytest via Poetry
- **WHEN** `make test` is run
- **THEN** the target SHALL execute `poetry run pytest` and exit 0 when tests pass (or when zero tests are collected)

#### Scenario: retired targets absent
- **WHEN** `make help` output is inspected
- **THEN** none of `setup-venv`, `activate-venv`, `clean-venv`, `check-venv`, `install-deps`, `setup-python` SHALL appear

### Requirement: streamlit-image-python-source-of-truth
The Streamlit application container defined by `infrastructure/docker/streamlit/Dockerfile` SHALL install Python dependencies from `pyproject.toml` (via Poetry, either through `poetry install --no-root --only main` or via `poetry export` + `pip install`). It SHALL NOT reference a repo-tracked `requirements.txt`.

#### Scenario: streamlit build uses Poetry
- **WHEN** the Streamlit Docker image is rebuilt
- **THEN** the build steps SHALL read dependencies from `pyproject.toml` and `poetry.lock`, not from a tracked `requirements.txt`
