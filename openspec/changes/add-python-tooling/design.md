## Context

The project runs two Python codebases (`application/cdc-testing-ui/` — 16 modules; `data-platform/streaming/spark/src/` — 27 modules + `apps/run_cdc_job.py`) and has none of the machinery that usually surrounds Python code at this scale:

- No tests. No `pytest.ini`, no `conftest.py`, no `tests/` directory. Nothing is unit-checked; regressions surface only when the stack runs end-to-end.
- Two dependency manifests. `pyproject.toml` has a Poetry-1.x block with six deps; `requirements.txt` pins the same six *plus* `pyspark==3.3.0`. The manifests are already out of sync in a load-bearing way — Poetry cannot install what Spark needs today.
- `setup_venv.sh` creates `venv/` (not `.venv/`) via plain `python -m venv` + `pip install -r requirements.txt`. Poetry is installed on the host (2.3.2) but not used by the setup path — the pyproject file exists as a decorative artifact.
- Makefile encodes the venv convention across seven targets, all of which will need to move together.

This document is the design for a new `python-tooling` OpenSpec capability that consolidates these concerns. It does **not** create the file tree or edit any Python packaging files yet — those follow once the design direction is approved.

## Goals / Non-Goals

**Goals:**
- Single source of dependency truth: `pyproject.toml`. `poetry.lock` is committed for reproducibility.
- Single virtual-environment convention: `.venv/` in-project, managed by Poetry.
- A working `make test` target that runs `pytest` inside the Poetry venv and succeeds even before any tests exist.
- Unit tests for the pure-function surface of both codebases — enough to catch a broken transformer or a broken database-manager call in seconds instead of minutes.
- All governance guarantees expressible as OpenSpec requirements so `make spec-validate` can verify them structurally.

**Non-Goals:**
- CI/CD (GitHub Actions, GitLab CI). Deferred to a separate later change.
- Pre-commit hooks or linters (black, ruff, mypy). Separate later change.
- End-to-end tests that require a running stack (Docker Compose, real Kafka, real ClickHouse).
- Streamlit view tests. Streamlit's testing framework is worth it later, but views are 80% of `application/cdc-testing-ui/` and would inflate this change past its useful weight.
- Migrating the Spark container's Python. `ed-pyspark-jupyter` uses a pre-built image with `pyspark` baked in, and mounts source as a volume — no pip step to migrate.
- Bumping `python = "^3.9"` or any pinned version. This change reorganizes tooling; it does not upgrade libraries.

## Three Pillars

Tooling is structured into three pillars, each independently shippable. Ship in order; stop at any phase if value is sufficient.

### Pillar 1 — Dependency Management (Poetry)

**Tool choice:** Poetry 2.3.2 (already installed on host).

**Behavior the spec will encode:**
- `pyproject.toml` declares all runtime dependencies (Streamlit UI + Spark). `pyspark = "3.3.0"` (currently missing) joins the main group.
- A `[tool.poetry.group.dev.dependencies]` group declares `pytest`, `pytest-mock`, and `pytest-cov`. Optional groups can be added later (docs, lint) without touching this contract.
- `poetry.lock` is committed to the repo. Reproducible installs across machines mean "works on my box" is a genuine claim, not a probability.
- `requirements.txt` no longer exists. Any tool that needs a pip-compatible manifest generates it via `poetry export --without-hashes -o requirements.txt` at build time (used by the Streamlit Dockerfile if we can't run Poetry inside the build).

**Where it plugs in (reuse, don't rebuild):**
- `pyproject.toml` — extend the existing `[tool.poetry]` section. Add `pyspark`, then the dev group, then a `[tool.pytest.ini_options]` block (Pillar 3).
- `infrastructure/docker/streamlit/Dockerfile` — replace the `COPY requirements.txt` + `pip install -r` pair with either (a) `pip install poetry && poetry install --no-root --only main` in the build stage, or (b) a multi-stage build that generates `requirements.txt` via `poetry export` before pip installs it. Option (b) keeps the container thin.

**New files:**
- `poetry.toml` — project-scoped Poetry config (`[virtualenvs] in-project = true`). Enforces `.venv/` inside the repo regardless of the developer's global Poetry config.
- `poetry.lock` — committed lockfile.

### Pillar 2 — Virtual Environment Convention (`.venv/`)

**Tool choice:** Poetry's in-project venv mode, enforced by `poetry.toml`.

**Behavior the spec will encode:**
- The canonical venv path is `.venv/` at the repo root. `venv/` is retired.
- `setup_venv.sh` is deleted. It has one job — create a venv and pip-install — which `poetry install` now does with a lockfile.
- Seven venv-family Makefile targets collapse into a smaller Poetry-based set:
  - `setup-venv`, `activate-venv`, `clean-venv`, `check-venv`, `install-deps`, `setup-python` → **removed**.
  - New: `poetry-install` (main + dev), `poetry-shell` (activate), `poetry-clean` (rm `.venv poetry.lock`).
  - `run-ui-local`, `demo-data` — help text updated; they now assume Poetry venv rather than the old `source venv/bin/activate` prerequisite.
- `.gitignore` includes `.venv/` (and, defensively, `venv/` for prior local state).

**Where it plugs in:**
- `Makefile` — one Python-Environment section rewrite.
- `README.md` and `AGENTS.md` — "Local Python env" bullets updated to reference Poetry commands.
- `CLAUDE.md` — the same references.

**Tradeoff:** Some developers keep venvs in a central location (`~/.venvs/`, `pyenv virtualenv`, etc.). Forcing in-project is opinionated but eliminates a class of "which env did I install into" bugs. The `poetry.toml` file makes the choice repo-scoped, not developer-global — teammates who prefer central venvs elsewhere are unaffected in other projects.

### Pillar 3 — Test Infrastructure

**Tool choice:** pytest + pytest-mock, session-scoped local `SparkSession` for Spark tests.

**Behavior the spec will encode:**
- Test directory layout:
  ```
  tests/
    conftest.py                 # shared fixtures (paths, env)
    spark/
      conftest.py               # SparkSession fixture, sample DataFrames
      test_kafka_parser.py
      test_customers_transformer.py
      test_products_transformer.py
      test_orders_transformer.py
      test_udfs.py              # decode_decimal_udf and future PII UDFs
    streamlit/
      conftest.py               # mock psycopg2 / kafka connections
      test_database_manager.py
      test_kafka_manager.py
  ```
- `pyproject.toml` gains `[tool.pytest.ini_options]`:
  ```toml
  testpaths = ["tests"]
  pythonpath = [
    "data-platform/streaming/spark/src",
    "application/cdc-testing-ui",
  ]
  addopts = "-ra --strict-markers"
  ```
- `make test` runs `poetry run pytest`. Succeeds with `no tests ran` (exit 5 mapped to green — pytest's `--exitfirst-strict` is off by default). Once tests exist, exit 0 is the target.
- Phase 3 initial test surface:
  - Each per-table transformer (`customers_cdc_transformer.py`, `product_cdc_transformer.py`, `order_cdc_transformer.py`) has at least one happy-path test that builds a sample Kafka payload DataFrame, runs the transformer, and asserts the output schema and one row's `_version` / `_deleted` values.
  - `decode_decimal_udf` in `src/utils/udfs.py` has round-trip tests (encode a decimal → decode → assert equality) plus null-handling.
  - `DatabaseManager` (Streamlit) has one connection-context test with a mocked `psycopg2.connect`.
  - `KafkaManager` (Streamlit) has one message-produce test with a mocked producer.

**Where it plugs in:**
- `data-platform/streaming/spark/src/` — imported via `pythonpath` from pytest config. No `__init__.py` gymnastics; no `pip install -e .` needed.
- `application/cdc-testing-ui/` — same treatment.

**Tradeoff:** A session-scoped local Spark session takes ~5s to start on the first test. Fine for a `make test` cycle. Not fine for TDD ping-pong; developers who want fast feedback can filter with `pytest -k transformer` to skip UDF tests, or use `pytest --lf`. Documented in the tests/spark conftest docstring.

## Decisions

**Poetry, not pip-tools or uv**
Poetry is already installed and already partially in the pyproject. Switching to uv would be faster at install time but introduces a *third* tool state (uv, pip, poetry). Sticking with Poetry closes the loop with the least new muscle memory. uv is worth revisiting when the team wants CI speed more than familiarity.

**In-project `.venv/`, enforced by `poetry.toml`**
Global Poetry config varies across developers. A `poetry.toml` inside the repo pins the choice to this project only. Also plays well with IDE Python interpreters, which reliably pick up `.venv/` at the workspace root.

**`poetry.lock` committed**
Reproducibility is the whole point. The alternative (add `poetry.lock` to `.gitignore`) turns "same commit, same deps" into a probability. Not worth the bytes saved.

**One `python-tooling` capability, not requirements scattered across `infrastructure`**
Dep management, venv convention, and test infrastructure are one concern (how Python is developed). Splitting them across `infrastructure` (venv) and elsewhere (tests) makes it impossible to audit "what does Python tooling guarantee" in one place. The `python-tooling` capability owns the requirements; `infrastructure` carries MODIFIED deltas where tooling changes its observable behavior (Makefile, Dockerfile).

**Tests live at repo root, not per-codebase**
An alternative layout would be `application/cdc-testing-ui/tests/` + `data-platform/streaming/spark/tests/`. That plays better if we ever split those into separate Python packages. Today they're one repo with one Poetry venv; a single `tests/` tree at the root is simpler for `pytest` discovery, coverage aggregation, and `make test`. If we ever split the repo, the tests split with the source.

**Streamlit views are out of scope**
Views are `st.columns()` + `st.metric()` calls with `st.session_state` mutation. Testing them meaningfully requires either Streamlit's testing framework (which was still labeled experimental at the time of writing) or an e2e stack. Neither belongs in a change that's already juggling three pillars. Views get a later change.

## Risks / Trade-offs

**Poetry `install --no-root` in the Dockerfile still installs Poetry**
The Streamlit Dockerfile switching to Poetry means the build image gets ~30MB heavier (Poetry itself). Mitigation: multi-stage build where the first stage runs `poetry export` and the second stage runs `pip install -r requirements.txt` on the generated file. Container stays lean; `requirements.txt` still exists at build time but not in the repo.

**pyspark install failure with certain Python versions**
`pyspark==3.3.0` on Python 3.12+ has known compatibility issues. Current pin is `python = "^3.9"`, so 3.12 is technically allowed but not exercised. Mitigation: keep the caret constraint; document that CI (when it arrives) should pin to 3.11.

**Deleting `venv/` on machines that have one**
Developers who ran `make setup-venv` before this change have `venv/` in their working tree. It's gitignored, so deleting the target won't touch it — but they should be told to `rm -rf venv && poetry install`. Mitigation: `poetry-clean` target removes both `.venv/` and any stale `venv/` (best-effort), and the PROPOSAL.md's user-facing rollout note calls this out.

**Streamlit Dockerfile's install-time behavior changes**
The image tag will shift because layers change. Cached builds may need `--no-cache` on first rebuild. Low-frequency issue; documented in the rollout note.

**Adding pyspark to `pyproject.toml` produces a heavy install**
`pyspark==3.3.0` is ~200MB. Every developer running `poetry install` downloads it, even those touching only the Streamlit UI. Mitigation: put `pyspark` in an optional group (`[tool.poetry.group.spark.dependencies]`) so `poetry install` installs only main+dev and Spark work requires `poetry install --with spark`. Trade-off: adds a `--with` flag to onboarding docs. Decision below.

**Decision on optional Spark group:** Ship `pyspark` in the *main* dependency group. The project's whole reason to exist is Spark streaming; the Streamlit UI is a testing harness. Optionality would optimize for a use case that doesn't exist here.

**Spark UDFs and PySpark session in unit tests are slow**
Local Spark sessions take 3–7s to spin up. Multiplying that across many test files is annoying. Mitigation: `session_spark` fixture is `scope="session"` in `tests/spark/conftest.py` — spun up once per `pytest` invocation. Individual tests use `spark_session` locally, which just returns the shared instance.

**`pythonpath = [...]` in pyproject means IDE auto-import may not know where to look**
Some IDEs read `sys.path` from a `.pth` file or a `[tool.pyright]` config, not from `[tool.pytest.ini_options]`. Mitigation: add both `src` roots to `[tool.pyright]` (or equivalent) later if IDE ergonomics become a friction point. Not in scope for this change.

## Phased Rollout

Each phase is independently shippable; ship in order, but stop at any phase if value is sufficient.

**Phase 1 — Poetry + `.venv/` Migration (Pillar 1 + Pillar 2)**
- Pure tooling; no test code.
- Exit criteria: `poetry install` succeeds; `.venv/` exists at repo root and is what Poetry uses; `make up-ui` still builds and runs (Streamlit container works via Poetry-based build); `make run-ui-local` works from `.venv/` with no manual `source` needed (Poetry-shell or `poetry run streamlit run …`); `requirements.txt` and `setup_venv.sh` are gone; `poetry.lock` is committed.
- Highest risk-reduction per line of code: eliminates the manifest-divergence footgun.

**Phase 2 — Test Infrastructure (Pillar 3 skeleton)**
- Zero test code; only the scaffolding.
- Exit criteria: `tests/` directory tree exists; `conftest.py` files exist (empty is fine); `[tool.pytest.ini_options]` block declares `testpaths` and `pythonpath`; `make test` runs `poetry run pytest` and exits 0 with "no tests ran".
- Low risk. Sets up the surface for Phase 3.

**Phase 3 — Initial Unit Tests (Pillar 3 content)**
- The actual test payload. Covers pure-function surfaces of both codebases.
- Exit criteria: `make test` collects >= 20 tests and they all pass. Coverage report (via `pytest --cov=data-platform/streaming/spark/src --cov=application/cdc-testing-ui`) shows > 30% on Spark src (limited by the untested job classes) and > 50% on Streamlit managers (excluding views).
- Highest ongoing value: this is where regressions start to be catchable in seconds.

## Requirements That Will Be Declared

These will become `### Requirement:` blocks in `openspec/specs/python-tooling/spec.md` once the change is archived. Listed here for review; **not** authoritative until they exist as scenarios with WHEN/THEN.

| Pillar | Requirement (kebab-name) | One-line summary |
|--------|--------------------------|------------------|
| 1 | `poetry-single-source-deps` | `pyproject.toml` is the single source of dep truth; no `requirements.txt` in the repo |
| 1 | `poetry-in-project-venv` | Poetry configured via `poetry.toml` to place `.venv/` in the project root |
| 1 | `poetry-lock-committed` | `poetry.lock` is tracked in git for reproducible installs |
| 1 | `streamlit-dockerfile-poetry` | Streamlit Dockerfile builds via Poetry (`poetry export` + pip, or direct `poetry install`) |
| 2 | `pytest-config-in-pyproject` | `[tool.pytest.ini_options]` declares `testpaths` and both codebases in `pythonpath` |
| 2 | `tests-directory-layout` | `tests/spark/` and `tests/streamlit/` exist with `conftest.py` files |
| 2 | `make-test-target` | `make test` runs `poetry run pytest` and exits 0 even with zero collected tests |
| 3 | `spark-transformer-tests` | Each per-table transformer has at least one happy-path unit test |
| 3 | `spark-udf-tests` | `decode_decimal_udf` (and any future PII UDFs) has round-trip and null-handling tests |
| 3 | `streamlit-manager-tests` | `DatabaseManager` and `KafkaManager` have mocked-client happy-path tests |

## Cross-Capability Modifications

Tooling changes observable behavior already covered by other specs. Repo convention (see `openspec/changes/baseline/specs/` and `openspec/changes/add-data-governance/specs/`) is to keep MODIFIED requirements under `openspec/changes/add-python-tooling/specs/<capability>/spec.md`, using `## MODIFIED Requirements` sections that mirror the shape of the corresponding blocks in `openspec/specs/<capability>/spec.md`. On archive, those sections are merged back into the main specs.

Tooling-driven MODIFIED requirements land in:

- **`infrastructure`**: Seven venv-related Makefile targets retire in favor of three Poetry-based ones plus `make test`; `setup_venv.sh` is deleted; `infrastructure/docker/streamlit/Dockerfile` builds via Poetry rather than `pip install -r requirements.txt`.

No other capability is touched. `cdc-pipeline`, `analytics`, `streamlit-ui`, and `data-governance` are unaffected in their observable behavior — those capabilities describe *what the system does*, and this change reorganizes *how developers work on it*.

## Out of Scope

- CI/CD (GitHub Actions or similar). Ships as a separate later change once test coverage exists to run against.
- Pre-commit hooks, linters, formatters (black, ruff, isort, mypy).
- End-to-end tests that require a live Compose stack.
- Streamlit view tests — deferred until Streamlit's testing framework matures and until the manager surface is fully covered.
- Migrating the Spark container's Python packaging. The image is pre-built (`easewithdata/pyspark-jupyter-lab`) and source is mounted; there's nothing to migrate there.
- Python version bumps.
- Documentation site generators (Sphinx, MkDocs).
- Splitting the repo into per-codebase Python packages. Considered and rejected; not worth the churn today.
