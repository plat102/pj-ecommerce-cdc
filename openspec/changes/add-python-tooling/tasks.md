## 0. Design (this turn)

- [x] 0.1 Write PROPOSAL.md describing the new `python-tooling` capability and cross-capability deltas
- [x] 0.2 Write DESIGN.md covering three pillars, tool choices, tradeoffs, and phased rollout
- [x] 0.3 Write TASKS.md (this file)
- [x] 0.4 Write initial `specs/python-tooling/spec.md` with placeholder requirements and the placeholder → phase-scoped mapping table
- [x] 0.5 Write `specs/infrastructure/spec.md` (MODIFIED) for the venv/Makefile/Dockerfile changes
- [x] 0.6 User approves design direction before implementation begins

## 1. Phase 1 — uv + `.venv/` Migration

- [x] 1.1 Rewrite `pyproject.toml` to PEP 621: replace `[tool.poetry]` and `[tool.poetry.dependencies]` with `[project]` (name, version, description, `requires-python = ">=3.9,<3.12"`, `dependencies = [...]`). Preserve the existing six deps, add `pyspark==3.3.0` to close the requirements.txt vs pyproject.toml divergence.
- [x] 1.2 Add `[dependency-groups]` block to `pyproject.toml` with a `dev` group containing `pytest`, `pytest-mock`, `pytest-cov`
- [x] 1.3 Run `uv lock` (host has uv 0.11.14 already) and commit the resulting `uv.lock`
- [x] 1.4 Delete `setup_venv.sh`
- [x] 1.5 Delete `requirements.txt`
- [x] 1.6 Rewrite the venv-family Makefile targets: retire `setup-venv`, `activate-venv`, `clean-venv`, `check-venv`, `install-deps`, `setup-python`; add `uv-sync` (runs `uv sync --group dev`), `uv-shell` (opens a subshell in the activated venv or prints activation hint), `uv-clean` (removes `.venv uv.lock` and any stale `venv/`). Update `run-ui-local` and `demo-data` help text to reference `uv run …` rather than the old `source venv/bin/activate` requirement.
- [x] 1.7 Update `infrastructure/docker/streamlit/Dockerfile` to a multi-stage build: stage 1 uses `ghcr.io/astral-sh/uv:0.11.14` (or `pip install uv==0.11.14`) to run `uv export --no-hashes --no-dev -o requirements.txt`; stage 2 runs `pip install -r requirements.txt` on the exported file. Runtime image does not contain uv.
- [x] 1.8 Add `.venv/` to `.gitignore` (retain `venv/` there defensively for developers with pre-migration state)
- [x] 1.9 Update `AGENTS.md` "Local Python env" and `CLAUDE.md` "Common commands / Local Python env" sections to reference the uv-based flow (`make uv-sync`, `uv run …`, or `. .venv/bin/activate`)
- [x] 1.10 Update `README.md` any references to `setup_venv.sh` / `requirements.txt` / `venv/`
- [x] 1.11 Update `specs/python-tooling/spec.md` in this change dir — add `## ADDED Requirements` for `uv-single-source-deps`, `uv-in-project-venv`, `uv-lock-committed`, `streamlit-dockerfile-uv` (decomposed from the `dependency-management` placeholder)
- [x] 1.12 Update `specs/infrastructure/spec.md` in this change dir — record the retired Makefile targets and Dockerfile change under `## MODIFIED Requirements`

## 2. Phase 2 — Test Infrastructure (skeleton, no tests)

- [x] 2.1 Create `tests/conftest.py` (empty is fine; reserves the entry point)
- [x] 2.2 Create `tests/spark/conftest.py` with a session-scoped `SparkSession.builder.master('local[*]').appName('unit-tests').getOrCreate()` fixture and helper fixtures for sample Kafka payload DataFrames
- [x] 2.3 Create `tests/streamlit/conftest.py` with mock fixtures (`mock_psycopg2_connect`, `mock_kafka_producer`, `mock_kafka_consumer`)
- [x] 2.4 Add `[tool.pytest.ini_options]` block to `pyproject.toml`: `testpaths = ["tests"]`, `pythonpath = ["data-platform/streaming/spark", "application/cdc-testing-ui"]` (spark root so `src.xxx` imports resolve like the apps do), `addopts = "-ra --strict-markers"`
- [x] 2.5 Add a `make test` Makefile target that runs `uv run pytest`
- [x] 2.6 Verify: `make test` exits 0 (or maps pytest's "no tests collected" exit 5 to 0 via `pytest --exitfirst` config)
- [x] 2.7 Update `specs/python-tooling/spec.md` — add `## ADDED Requirements` for `pytest-config-in-pyproject`, `tests-directory-layout`, `make-test-target` (decomposed from the `test-infrastructure` placeholder)
- [x] 2.8 Update `specs/infrastructure/spec.md` — add `## MODIFIED Requirements` (or extend the block from 1.12) to mention `make test` as a canonical target

## 3. Phase 3 — Initial Unit Tests

- [x] 3.1 Write `tests/spark/test_kafka_parser.py`: two happy-path tests for `KafkaMessageParser` — one create, one delete
- [x] 3.2 Write `tests/spark/test_customers_transformer.py`: build a Debezium-shaped payload DataFrame, run `CustomersCDCTransformer`, assert output columns + `_version` populated from `ts_ms` + `_deleted` set on op=`d`
- [x] 3.3 Write `tests/spark/test_products_transformer.py`: same shape as 3.2, including one row exercising `decode_decimal_udf` on the `price` column
- [x] 3.4 Write `tests/spark/test_orders_transformer.py`: same shape as 3.2
- [x] 3.5 Write `tests/spark/test_udfs.py`: round-trip test for `decode_decimal_udf` (encode a Decimal to base64+scale, decode, assert equality) plus null-handling
- [x] 3.6 Write `tests/streamlit/test_database_manager.py`: `DatabaseManager` connection context test with `mock_psycopg2_connect`; assert `execute_query` calls `.cursor().execute(...)` with the expected SQL
- [x] 3.7 Write `tests/streamlit/test_kafka_manager.py`: `KafkaManager` produce test with `mock_kafka_producer`; assert one produce call with the expected topic+key+value shape
- [x] 3.8 Verify: `make test` reports >= 20 tests passing (23 collected total; on JDK 17 or lower all pass. On JDK 21+, Spark tests auto-skip because Spark 3.3.0 needs `java.nio.DirectByteBuffer.<init>(long,int)` which was removed in JDK 21 — see `tests/spark/conftest.py::pytest_collection_modifyitems`. Host machines on Java 23 will see "14 passed, 9 skipped").
- [x] 3.9 Update `specs/python-tooling/spec.md` — add `## ADDED Requirements` for `spark-transformer-tests`, `spark-udf-tests`, `streamlit-manager-tests` (decomposed from the `initial-test-coverage` placeholder)

## 4. Archive

- [ ] 4.1 Run `openspec status --change add-python-tooling --json` and confirm `isComplete: true`
- [ ] 4.2 Merge each `specs/<capability>/spec.md` file from this change dir into the corresponding `openspec/specs/<capability>/spec.md`, applying `## MODIFIED Requirements` sections into the existing requirement blocks
- [ ] 4.3 Merge `specs/python-tooling/spec.md` into a new `openspec/specs/python-tooling/spec.md`, decomposing the three broad placeholder requirements into the 10 phase-scoped requirements listed in `design.md` § "Requirements That Will Be Declared"
- [ ] 4.4 Move `openspec/changes/add-python-tooling/` to `openspec/changes/archive/add-python-tooling/`
