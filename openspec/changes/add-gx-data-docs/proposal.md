## Why

`add-data-governance` Phase 3 shipped an inline GX-lite gate: rows that fail an expectation route to `{table}_cdc_dlq`, and Spark logs one line per batch (`gx-gate table=X batch=N invalid=yes/no`). That's enough to catch failures but leaves the operator staring at raw JSON DLQ messages to understand *what* broke and *how often*. Concretely, an operator today cannot answer without hand-crafted Kafka reads:

- "Across the last 100 batches on `products_cdc`, what fraction passed each expectation?"
- "Which expectation is the worst offender this week?"
- "For expectation `expect_column_values_to_be_between(price, 0, 10000)`, show me 5 sample violations."
- "What does the `orders_cdc_suite` actually check — do I have to open the JSON?"

Great Expectations proper ships an answer to all of these — **Data Docs**, browsable HTML pages generated from `ValidationResult` objects. We currently have `great_expectations` listed as an optional dep guarded by an `import` in `quality.py`, but the code path that *uses* GX (the `_validate_with_gx` helper) is pure Spark — GX itself is never called. Activating real GX alongside the inline gate closes the observability gap without changing the pipeline hot path.

## What Changes

- Add a `GxSuiteRunner` in `data-platform/streaming/spark/src/governance/gx_runner.py` that runs the *real* Great Expectations engine (via `SparkDFDataset`) on every micro-batch and persists a `ValidationResult` to the GX validations store. Runs alongside the inline gate — never replaces it. Opt-in via `ENABLE_GX_DATA_DOCS=1` (default off) so the ~200MB GX dep stays optional.
- Add a `great_expectations.yml` under `data-platform/governance/gx/` declaring stores (`expectations_store`, `validations_store`, `checkpoint_store`) backed by the filesystem at `/opt/gx/` inside the Spark container (bind-mounted from `data-platform/governance/gx-runtime/` on the host). GX rebuilds the Data Docs site into `/opt/gx/data-docs/` after each validation.
- Add an `nginx:alpine` sidecar container `gx-data-docs-server` that serves the built site at `http://localhost:8890`. New compose file `docker-compose.gx-docs.yml` (opt-in — not in `make up` by default; adds ~10MB and a port).
- Add a small Prometheus text-collector script `scripts/gx_metrics_exporter.py` that reads the latest `ValidationResult` JSONs, computes per-suite / per-expectation success ratios, and writes a Prometheus text-format file that node-exporter picks up via its `textfile_collector` directory. Metric names: `gx_suite_success_ratio{table,suite}`, `gx_expectation_success_ratio{table,expectation_type,column}`.
- Extend the existing Grafana `Data Governance Overview` dashboard (from `add-data-governance` Phase 3) with 2 new panels: "GX Suite Success Rate (24h)" and "Top 5 Failing Expectations". Include panel links pointing at the Data Docs site.
- Add `docs/data-governance.md` (if absent) or extend `docs/observability.md` with a "GX Data Docs" section explaining opt-in, the localhost:8890 site, and how to interpret per-expectation success ratios vs the row-level DLQ.

## Capabilities

### New Capabilities
- `data-quality-reporting`: covers the runner, the persisted validation store, the Data Docs site, and the Prometheus metrics exposure. Sibling to `data-governance` (which owns the *gate*) and `observability` (which owns *infra* metrics).

### Modified Capabilities
- `data-governance`: extends `gx-batch-validation` to note that when `ENABLE_GX_DATA_DOCS=1` a second validation pass runs via the real GX engine alongside the inline gate; the inline gate remains the *authoritative* row-drop decision.
- `analytics`: extends the `Data Governance Overview` dashboard requirement to include the two new panels.
- `infrastructure`: extends `per-service-targets` for the new `up-gx-docs` / `down-gx-docs` targets; the gx-docs server is explicitly excluded from `make up` for the same reason `up-governance` is (opt-in features that cost RAM / disk).

## Impact

**New code**:
- `data-platform/streaming/spark/src/governance/gx_runner.py` (the real-GX pass)
- `data-platform/governance/gx/great_expectations.yml` (project config)
- `data-platform/governance/gx/expectations/` — GX-format suite files converted from the 3 existing JSON suites (`{table}_cdc_suite.json`) into the GX-canonical format
- `scripts/gx_metrics_exporter.py` (Prometheus text collector, cron-driven from host or invoked on each batch)
- `infrastructure/docker/docker-compose.gx-docs.yml` (nginx sidecar)
- `infrastructure/docker/gx-docs/nginx.conf` (thin static-file server config)
- `infrastructure/docker/grafana/provisioning/dashboards/files/data-governance/data-governance-overview.json` — updated with 2 new panels

**Modified code**:
- `Makefile` — add `COMPOSE_GX_DOCS`, `up-gx-docs`, `down-gx-docs`, `logs-gx-docs`, `sh-gx-docs` targets (mirroring `up-governance` pattern)
- `data-platform/streaming/spark/src/governance/quality.py` — add call site for `GxSuiteRunner.validate_and_persist` inside `with_gx_gate`, gated by `ENABLE_GX_DATA_DOCS=1`
- `data-platform/streaming/spark/src/config/app_config.py` — add `GxDataDocsConfig` reading `ENABLE_GX_DATA_DOCS`, `GX_PROJECT_DIR`
- `pyproject.toml` — bump `great_expectations` to a pinned version + add `great_expectations[spark]` extra
- `.env.example` — `ENABLE_GX_DATA_DOCS` placeholder + one-line doc

**Runtime behavior**:
- Default: nothing changes. `ENABLE_GX_DATA_DOCS` unset means only the inline gate runs; no GX import, no filesystem writes, no sidecar container needed.
- Opt-in: `ENABLE_GX_DATA_DOCS=1 make cdc-run-products-prod` produces one `ValidationResult` JSON per batch in `data-platform/governance/gx-runtime/uncommitted/validations/`. `make up-gx-docs` serves the compiled Data Docs site at `http://localhost:8890`.
- Prometheus scrape picks up `gx_*` metrics via node-exporter's textfile collector; Grafana panels populate.

**No breaking changes.** Existing `ENABLE_GX_GATE=1` behavior is untouched — the inline gate remains the row-drop authority. `ENABLE_GX_DATA_DOCS=1` is purely additive observability.

**Deferred / non-goals**:
- CI-driven suite validation on schema changes (a `add-gx-ci-checks` change later).
- Auto-repair suggestions (GX doesn't emit them; a separate LLM-driven change).
- Real-time streaming Data Docs updates — the site rebuilds once per batch, which is fine for the ~10s batch cadence.
