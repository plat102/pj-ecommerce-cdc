## ADDED Requirements

> **Status:** Phase 1 requirements (Pillar 1 — Dependency Management) are decomposed below into their phase-scoped form. Phase 2 (`test-infrastructure`) and Phase 3 (`initial-test-coverage`) remain broad placeholders and will be decomposed as those phases reach implementation.
>
> **Decomposition status:**
>
> | Placeholder | Decomposed? | Phase-scoped requirements |
> |---|---|---|
> | `dependency-management` | Yes (Phase 1) | `uv-single-source-deps`, `uv-in-project-venv`, `uv-lock-committed`, `streamlit-dockerfile-uv` |
> | `test-infrastructure` | Not yet | `pytest-config-in-pyproject`, `tests-directory-layout`, `make-test-target` |
> | `initial-test-coverage` | Not yet | `spark-transformer-tests`, `spark-udf-tests`, `streamlit-manager-tests` |

### Requirement: uv-single-source-deps
`pyproject.toml` using the PEP 621 `[project]` table SHALL be the single source of Python dependency truth for this project. No `requirements.txt` file SHALL exist in the repo (though it MAY be generated ephemerally at container build time by `uv export`). The `[tool.poetry]` block SHALL NOT be present.

#### Scenario: single manifest at repo root
- **WHEN** a developer inspects the repo for Python dependency declarations
- **THEN** `pyproject.toml` SHALL declare dependencies under `[project].dependencies` (and dev dependencies under `[dependency-groups]`)
- **AND** no `requirements.txt` SHALL be tracked in git

#### Scenario: pyspark declared in pyproject
- **WHEN** a developer runs `uv sync`
- **THEN** `pyspark==3.3.0` SHALL be installed into `.venv/` as declared under `[project].dependencies`

### Requirement: uv-in-project-venv
The canonical Python virtual environment SHALL be `.venv/` at the repo root, managed by uv. uv's default in-project venv behavior SHALL be relied on with no repo-scoped config file. `venv/` (without leading dot) SHALL NOT be used.

#### Scenario: uv sync creates .venv at repo root
- **WHEN** a developer runs `uv sync --group dev` from the repo root
- **THEN** a `.venv/` directory SHALL be created at the repo root with all main + dev dependencies installed

#### Scenario: no repo-scoped uv config file
- **WHEN** the repo is inspected for uv configuration files
- **THEN** neither `uv.toml` nor `[tool.uv]` in `pyproject.toml` SHALL override the in-project venv default

### Requirement: uv-lock-committed
`uv.lock` SHALL be tracked in git for reproducible installs across machines.

#### Scenario: reproducible install
- **WHEN** two developers on different machines run `uv sync` against the same commit
- **THEN** both SHALL end up with the same resolved dependency versions as determined by `uv.lock`

#### Scenario: lockfile present in repo
- **WHEN** the repo is inspected
- **THEN** `uv.lock` SHALL exist at the repo root and SHALL NOT be listed in `.gitignore`

### Requirement: streamlit-dockerfile-uv
The Streamlit application container defined by `infrastructure/docker/streamlit/Dockerfile` SHALL install Python dependencies from `pyproject.toml` and `uv.lock` via a multi-stage build: stage 1 uses a pinned `ghcr.io/astral-sh/uv` image to run `uv export --frozen --no-hashes --no-dev -o requirements.txt`, and stage 2 runs `pip install -r requirements.txt` on the exported file. The runtime image SHALL NOT contain the `uv` binary and SHALL NOT reference a repo-tracked `requirements.txt`.

#### Scenario: streamlit build reads pyproject via uv export
- **WHEN** the Streamlit Docker image is rebuilt
- **THEN** the build steps SHALL generate `requirements.txt` ephemerally at build time from `pyproject.toml` + `uv.lock`
- **AND** no `requirements.txt` file SHALL be committed to the repo

#### Scenario: uv absent from runtime image
- **WHEN** the built Streamlit image is inspected
- **THEN** the `uv` binary SHALL NOT be present in the final image layer

### Requirement: test-infrastructure
The project SHALL declare a `tests/` directory tree, pytest configuration in `pyproject.toml`, and a `make test` target that runs `pytest` inside the uv-managed venv. This scaffolding SHALL be in place independent of whether any test code exists yet.

#### Scenario: make test with zero tests
- **WHEN** `make test` is run in a repo state where `tests/` exists but contains no test files
- **THEN** the target SHALL exit 0 (green) with a message indicating no tests were collected

#### Scenario: pytest discovers both codebases
- **WHEN** a test file under `tests/spark/` imports from `src.transformations`
- **AND** a test file under `tests/streamlit/` imports from `managers`
- **THEN** both imports SHALL resolve via `pythonpath` declared in `[tool.pytest.ini_options]`, without any `pip install -e` step

### Requirement: initial-test-coverage
Once test infrastructure exists, the pure-function surfaces of the two Python codebases (Spark transformations/UDFs; Streamlit managers) SHALL carry unit tests sufficient to catch a broken transformer or a broken manager call before end-to-end runs.

#### Scenario: transformer regression caught by tests
- **WHEN** a per-table CDC transformer's `_version` extraction is changed to reference a wrong field
- **THEN** the corresponding transformer test SHALL fail during `make test` without a live pipeline

#### Scenario: UDF regression caught by tests
- **WHEN** `decode_decimal_udf` is modified in a way that misinterprets Debezium's base64 encoding
- **THEN** its round-trip test SHALL fail during `make test`
