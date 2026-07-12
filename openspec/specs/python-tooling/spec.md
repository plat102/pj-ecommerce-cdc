# python-tooling Specification

## Purpose
TBD - created by archiving change add-python-tooling. Update Purpose after archive.
## Requirements
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

### Requirement: pytest-config-in-pyproject
Pytest configuration for this project SHALL live under `[tool.pytest.ini_options]` in `pyproject.toml`. The block SHALL declare `testpaths = ["tests"]` and `pythonpath` entries covering both codebases (`data-platform/streaming/spark` and `application/cdc-testing-ui`), and it SHALL set `addopts` including `--strict-markers` to catch typos in `@pytest.mark.*` decorators.

#### Scenario: pytest discovers both codebases
- **WHEN** a test file under `tests/spark/` imports from `transformations`
- **AND** a test file under `tests/streamlit/` imports from `managers`
- **THEN** both imports SHALL resolve via the `pythonpath` declared in `[tool.pytest.ini_options]`, without any `pip install -e` step

#### Scenario: config file is pyproject.toml
- **WHEN** `pytest` starts
- **THEN** its "configfile" report line SHALL name `pyproject.toml` (no `pytest.ini` or `setup.cfg` SHALL be tracked)

### Requirement: tests-directory-layout
The project SHALL contain a `tests/` directory at the repo root with `spark/` and `streamlit/` subdirectories. Each subdirectory SHALL contain a `conftest.py` file wiring the fixtures that its test files need (a session-scoped `SparkSession` for `tests/spark/`; mock client fixtures for `tests/streamlit/`).

#### Scenario: tests directory tree exists
- **WHEN** the repo is inspected
- **THEN** `tests/conftest.py`, `tests/spark/conftest.py`, and `tests/streamlit/conftest.py` SHALL all exist

#### Scenario: SparkSession is session-scoped
- **WHEN** multiple test files under `tests/spark/` request the `spark_session` fixture
- **THEN** all requests SHALL receive the same underlying `SparkSession` instance (avoiding the 3–7s startup cost per file)

### Requirement: make-test-target
The Makefile SHALL provide a `test` target that runs `uv run pytest`. The target SHALL exit 0 even when pytest collects no tests (mapping pytest's exit code 5 to 0) so that `make test` can be wired into future CI without failing on an empty tree.

#### Scenario: make test with zero tests
- **WHEN** `make test` is run in a repo state where `tests/` exists but contains no test files
- **THEN** the target SHALL exit 0 (green) with a message indicating no tests were collected

#### Scenario: make test runs pytest via uv
- **WHEN** `make test` is run
- **THEN** the underlying command SHALL be `uv run pytest` (no direct `pytest` invocation, no manual venv activation)

### Requirement: spark-transformer-tests
Each per-table CDC transformer (`CustomersCDCTransformer`, `ProductCDCTransformer`, `OrderCDCTransformer`) SHALL have at least one happy-path unit test that constructs a Debezium-shaped input DataFrame and asserts the output columns, the `_version` value sourced from `ts_ms`, and the `_deleted` flag set correctly for `op=d`. `KafkaMessageParser` SHALL also carry create-and-delete parse tests.

#### Scenario: transformer regression caught by tests
- **WHEN** a per-table CDC transformer's `_version` extraction is changed to reference a wrong field
- **THEN** the corresponding transformer test SHALL fail during `make test` without a live pipeline

#### Scenario: delete op sets deleted flag
- **WHEN** a `CustomersCDCTransformer` (or products / orders) is fed a row with `op=d`
- **THEN** the transformer test SHALL assert `_deleted == 1` and that ID is sourced from `before` (not `after`, which is null)

### Requirement: spark-udf-tests
Pure-function UDF bodies in `src/utils/udfs.py` SHALL have unit tests covering: `decode_decimal` round-trip (encode a Decimal → decode → assert equality) plus its null-handling; `hash_pii` determinism, differentiation across inputs, and null-handling; `tokenize_name` initial-preservation and null/empty-handling.

#### Scenario: decimal round-trip
- **WHEN** a Decimal is encoded into Debezium's two's-complement bytes and decoded via `decode_decimal(scale=2)`
- **THEN** the recovered value SHALL equal the original Decimal

#### Scenario: hash_pii is deterministic
- **WHEN** `hash_pii` is called twice with the same input under the same `PII_SALT`
- **THEN** both calls SHALL return the same SHA-256 hex digest

### Requirement: streamlit-manager-tests
`DatabaseManager` and `KafkaManager` in `application/cdc-testing-ui/managers/` SHALL each carry at least one happy-path test using mocked client libraries (patched at the `managers.database.psycopg2.connect` and `managers.kafka.KafkaConsumer` boundaries).

#### Scenario: execute_query forwards SQL to cursor
- **WHEN** `DatabaseManager.execute_query(sql, params)` is called against a mocked psycopg2 connection
- **THEN** the mocked cursor's `.execute` SHALL be called once with the same `(sql, params)` tuple

#### Scenario: create_consumer wires bootstrap_servers
- **WHEN** `KafkaManager.create_consumer(topics=["pg.public.customers"])` is called with a mocked `KafkaConsumer`
- **THEN** the mock constructor SHALL be invoked with `("pg.public.customers",)` and `bootstrap_servers` equal to the manager's config

