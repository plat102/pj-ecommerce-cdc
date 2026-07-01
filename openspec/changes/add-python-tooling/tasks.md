## 0. Design (this turn)

- [x] 0.1 Write PROPOSAL.md describing the new `python-tooling` capability and cross-capability deltas
- [x] 0.2 Write DESIGN.md covering three pillars, tool choices, tradeoffs, and phased rollout
- [x] 0.3 Write TASKS.md (this file)
- [x] 0.4 Write initial `specs/python-tooling/spec.md` with placeholder requirements and the placeholder → phase-scoped mapping table
- [x] 0.5 Write `specs/infrastructure/spec.md` (MODIFIED) for the venv/Makefile/Dockerfile changes
- [ ] 0.6 User approves design direction before implementation begins

## 1. Phase 1 — Poetry + `.venv/` Migration

- [ ] 1.1 Add `pyspark = "3.3.0"` to the main dependency group in `pyproject.toml` (closes the requirements.txt vs pyproject.toml divergence)
- [ ] 1.2 Add `[tool.poetry.group.dev.dependencies]` block to `pyproject.toml` with `pytest`, `pytest-mock`, `pytest-cov`
- [ ] 1.3 Create `poetry.toml` at the repo root with `[virtualenvs] in-project = true` so `.venv/` lives inside the repo regardless of developer global config
- [ ] 1.4 Run `poetry lock` (host has Poetry 2.3.2 already) and commit the resulting `poetry.lock`
- [ ] 1.5 Delete `setup_venv.sh`
- [ ] 1.6 Delete `requirements.txt`
- [ ] 1.7 Rewrite the venv-family Makefile targets: retire `setup-venv`, `activate-venv`, `clean-venv`, `check-venv`, `install-deps`, `setup-python`; add `poetry-install` (runs `poetry install --with dev`), `poetry-shell` (runs `poetry shell`), `poetry-clean` (removes `.venv poetry.lock` and any stale `venv/`). Update `run-ui-local` and `demo-data` help text to reference Poetry rather than the old `source venv/bin/activate` requirement.
- [ ] 1.8 Update `infrastructure/docker/streamlit/Dockerfile`: use a multi-stage build where stage 1 runs `poetry export --without-hashes -o requirements.txt` and stage 2 `pip install -r` the exported file. Alternative acceptable: `pip install poetry && poetry install --no-root --only main` in a single stage.
- [ ] 1.9 Add `.venv/` to `.gitignore` (retain `venv/` there defensively for developers with pre-migration state)
- [ ] 1.10 Update `AGENTS.md` "Local Python env" and `CLAUDE.md` "Common commands / Local Python env" sections to reference the Poetry-based flow (`make poetry-install`, `poetry shell`)
- [ ] 1.11 Update `README.md` any references to `setup_venv.sh` / `requirements.txt` / `venv/`
- [ ] 1.12 Update `specs/python-tooling/spec.md` in this change dir — add `## ADDED Requirements` for `poetry-single-source-deps`, `poetry-in-project-venv`, `poetry-lock-committed`, `streamlit-dockerfile-poetry` (decomposed from the `dependency-management` placeholder)
- [ ] 1.13 Update `specs/infrastructure/spec.md` in this change dir — record the retired Makefile targets and Dockerfile change under `## MODIFIED Requirements`

## 2. Phase 2 — Test Infrastructure (skeleton, no tests)

- [ ] 2.1 Create `tests/conftest.py` (empty is fine; reserves the entry point)
- [ ] 2.2 Create `tests/spark/conftest.py` with a session-scoped `SparkSession.builder.master('local[*]').appName('unit-tests').getOrCreate()` fixture and helper fixtures for sample Kafka payload DataFrames
- [ ] 2.3 Create `tests/streamlit/conftest.py` with mock fixtures (`mock_psycopg2_connect`, `mock_kafka_producer`, `mock_kafka_consumer`)
- [ ] 2.4 Add `[tool.pytest.ini_options]` block to `pyproject.toml`: `testpaths = ["tests"]`, `pythonpath = ["data-platform/streaming/spark/src", "application/cdc-testing-ui"]`, `addopts = "-ra --strict-markers"`
- [ ] 2.5 Add a `make test` Makefile target that runs `poetry run pytest`
- [ ] 2.6 Verify: `make test` exits 0 (or maps pytest's "no tests collected" exit 5 to 0 via `pytest --exitfirst` config)
- [ ] 2.7 Update `specs/python-tooling/spec.md` — add `## ADDED Requirements` for `pytest-config-in-pyproject`, `tests-directory-layout`, `make-test-target` (decomposed from the `test-infrastructure` placeholder)
- [ ] 2.8 Update `specs/infrastructure/spec.md` — add `## MODIFIED Requirements` (or extend the block from 1.13) to mention `make test` as a canonical target

## 3. Phase 3 — Initial Unit Tests

- [ ] 3.1 Write `tests/spark/test_kafka_parser.py`: two happy-path tests for `KafkaMessageParser` — one create, one delete
- [ ] 3.2 Write `tests/spark/test_customers_transformer.py`: build a Debezium-shaped payload DataFrame, run `CustomersCDCTransformer`, assert output columns + `_version` populated from `ts_ms` + `_deleted` set on op=`d`
- [ ] 3.3 Write `tests/spark/test_products_transformer.py`: same shape as 3.2, including one row exercising `decode_decimal_udf` on the `price` column
- [ ] 3.4 Write `tests/spark/test_orders_transformer.py`: same shape as 3.2
- [ ] 3.5 Write `tests/spark/test_udfs.py`: round-trip test for `decode_decimal_udf` (encode a Decimal to base64+scale, decode, assert equality) plus null-handling
- [ ] 3.6 Write `tests/streamlit/test_database_manager.py`: `DatabaseManager` connection context test with `mock_psycopg2_connect`; assert `execute_query` calls `.cursor().execute(...)` with the expected SQL
- [ ] 3.7 Write `tests/streamlit/test_kafka_manager.py`: `KafkaManager` produce test with `mock_kafka_producer`; assert one produce call with the expected topic+key+value shape
- [ ] 3.8 Verify: `make test` reports >= 20 tests passing
- [ ] 3.9 Update `specs/python-tooling/spec.md` — add `## ADDED Requirements` for `spark-transformer-tests`, `spark-udf-tests`, `streamlit-manager-tests` (decomposed from the `initial-test-coverage` placeholder)

## 4. Archive

- [ ] 4.1 Run `openspec status --change add-python-tooling --json` and confirm `isComplete: true`
- [ ] 4.2 Merge each `specs/<capability>/spec.md` file from this change dir into the corresponding `openspec/specs/<capability>/spec.md`, applying `## MODIFIED Requirements` sections into the existing requirement blocks
- [ ] 4.3 Merge `specs/python-tooling/spec.md` into a new `openspec/specs/python-tooling/spec.md`, decomposing the three broad placeholder requirements into the 10 phase-scoped requirements listed in `design.md` § "Requirements That Will Be Declared"
- [ ] 4.4 Move `openspec/changes/add-python-tooling/` to `openspec/changes/archive/add-python-tooling/`
