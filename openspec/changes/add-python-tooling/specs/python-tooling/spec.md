## ADDED Requirements

> **Status:** Placeholder requirements for the design-only phase of this proposal. Detailed scenarios for each phase (Poetry migration, test infrastructure skeleton, initial tests) will be filled in as that phase reaches implementation. See `design.md` for the full direction.
>
> **On archive**, each broad placeholder below decomposes into the phase-scoped requirements listed in `design.md` § "Requirements That Will Be Declared":
>
> | Placeholder here | Decomposes into (on archive) |
> |---|---|
> | `dependency-management` | `uv-single-source-deps`, `uv-in-project-venv`, `uv-lock-committed`, `streamlit-dockerfile-uv` |
> | `test-infrastructure` | `pytest-config-in-pyproject`, `tests-directory-layout`, `make-test-target` |
> | `initial-test-coverage` | `spark-transformer-tests`, `spark-udf-tests`, `streamlit-manager-tests` |

### Requirement: dependency-management
Python dependencies for this project SHALL be declared in a single source of truth (`pyproject.toml` using the PEP 621 `[project]` table) and installed via uv into an in-project `.venv/`. A committed `uv.lock` SHALL guarantee reproducible installs across machines, and every image that packages Python code SHALL build from the same source of truth.

#### Scenario: single source of truth
- **WHEN** a developer inspects the repo for Python dependency declarations
- **THEN** `pyproject.toml` SHALL be the only manifest present, and no `requirements.txt` file SHALL exist in the repo (though it MAY be generated ephemerally at container build time)

#### Scenario: reproducible install
- **WHEN** two developers on different machines run `uv sync` against the same commit
- **THEN** both SHALL end up with the same resolved dependency versions as determined by `uv.lock`

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
