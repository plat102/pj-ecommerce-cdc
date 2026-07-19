## 0. Design (this turn)

- [x] 0.1 Write proposal.md
- [x] 0.2 Write design.md — 7 decisions covering two-pass validation, filesystem store, nginx sidecar, textfile Prometheus metrics, dual suite representations, Grafana panels, GX 0.18 pinning
- [x] 0.3 Write tasks.md (this file)
- [x] 0.4 Write specs deltas: new capability `data-quality-reporting` with 5 requirements; MODIFIED `data-governance/gx-batch-validation` for the opt-in second-pass; MODIFIED `analytics/grafana-dashboard-provisioning` for the two new panels; MODIFIED `infrastructure/per-service-targets` for the gx-docs targets
- [ ] 0.5 User approves design direction before implementation begins

## 1. Phase 1 — GX runtime + suite conversion

- [ ] 1.1 Pin `great_expectations = "0.18.19"` in `pyproject.toml` under a new `[tool.uv.optional-dependencies]` extra `gx-docs` so the ~200MB dep stays opt-in for developers who don't need it.
- [ ] 1.2 Author `data-platform/governance/gx/great_expectations.yml` declaring three stores (`expectations_store`, `validations_store`, `checkpoint_store`) via `TupleFilesystemStoreBackend` rooted at `/opt/gx/`. Declare one Data Docs site `local_site` targeting `local_site/`. Declare the `runtime_environment` variables the runner will pass.
- [ ] 1.3 Write `scripts/gx_convert_suites.py` — reads `data-platform/governance/expectations/{table}_cdc_suite.json` (inline format) and emits `data-platform/governance/gx-runtime/expectations/{table}_cdc_suite.json` (GX canonical). Idempotent. Handles the 4 expectation kinds the inline gate supports (`not_null`, `in_set`, `between`, `length_between`) plus the `mostly` field.
- [ ] 1.4 Run the convertor manually and commit the 3 generated files as the initial GX-format suite baseline.
- [ ] 1.5 Add `.gitignore` entries: `data-platform/governance/gx-runtime/uncommitted/`, `data-platform/governance/gx-runtime/textfile/gx.prom`.

## 2. Phase 2 — Runner + textfile metrics

- [ ] 2.1 Add `SchemaRegistryConfig`-style `GxDataDocsConfig` to `data-platform/streaming/spark/src/config/app_config.py` reading `ENABLE_GX_DATA_DOCS`, `GX_PROJECT_DIR` (default `/opt/gx/`).
- [ ] 2.2 Implement `data-platform/streaming/spark/src/governance/gx_runner.py` with `GxSuiteRunner.validate_and_persist(batch_df, table)`:
  - Lazy-imports `great_expectations` (only fires when `ENABLE_GX_DATA_DOCS=1`).
  - Loads the GX-format suite from `gx-runtime/expectations/`.
  - Wraps `batch_df` in `SparkDFDataset`, calls `.validate(expectation_suite=...)`.
  - Persists the `ValidationResult` to `uncommitted/validations/<suite>/<ts>.json`.
  - Rebuilds Data Docs via `context.build_data_docs()`.
  - Writes Prometheus textfile at `<textfile>/gx.prom` with `gx_suite_success_ratio` + `gx_expectation_success_ratio` metrics.
  - Prunes validations store: keep last 100 per suite + entries younger than 24h.
- [ ] 2.3 Wire `GxSuiteRunner` call site inside `with_gx_gate` in `quality.py` — invoke after inline gate, guarded by `ENABLE_GX_DATA_DOCS=1`. Failures in the runner SHALL NOT propagate (best-effort second pass).
- [ ] 2.4 Unit tests `tests/spark/test_gx_runner.py` — mock the GX context, verify the runner:
  - Correctly names the persisted file per suite.
  - Emits Prometheus textfile with expected metric lines.
  - Prunes when validations count > 100.
  - Swallows GX errors (never re-raises).
- [ ] 2.5 Update `data-platform/streaming/spark/scripts/submit_job.sh` — bind-mount `/opt/gx/` from `data-platform/governance/gx-runtime/` inside the spark container (already achievable via `docker-compose.spark.yml` volume declaration; add if missing).

## 3. Phase 3 — Nginx sidecar + Grafana panels

- [ ] 3.1 Write `infrastructure/docker/docker-compose.gx-docs.yml` — one service `gx-data-docs-server` on `nginx:alpine`, port `8890:80`, bind-mount `data-platform/governance/gx-runtime/uncommitted/data_docs/local_site/` read-only at `/usr/share/nginx/html`. External network `ecommerce-network`.
- [ ] 3.2 Add `infrastructure/docker/gx-docs/nginx.conf` if the default nginx config needs any tweaks (probably not; nginx:alpine serves `/usr/share/nginx/html` out of the box).
- [ ] 3.3 Add Makefile targets `up-gx-docs`, `down-gx-docs`, `logs-gx-docs`, `sh-gx-docs` mirroring the `up-governance` pattern. Update `.PHONY` list.
- [ ] 3.4 Extend `infrastructure/docker/grafana/provisioning/dashboards/files/data-governance/data-governance-overview.json` — add the two new panels (`GX Suite Success Rate (24h)` bar-gauge on `avg_over_time(gx_suite_success_ratio[24h])`; `Top 5 Failing Expectations` table on `bottomk(5, gx_expectation_success_ratio)`). Include `links` array pointing at `http://localhost:8890/`.
- [ ] 3.5 Update `docs/observability.md` — new "GX Data Docs" section: what the site is, how to enable (`ENABLE_GX_DATA_DOCS=1 make cdc-run-*-prod`, then `make up-gx-docs`), how to read per-expectation success ratios vs the row-level DLQ, one paragraph.
- [ ] 3.6 Update `.env.example` — commented `ENABLE_GX_DATA_DOCS` placeholder with one-line note.

## 4. Phase 4 — Live smoke

- [ ] 4.1 Cold path: `ENABLE_GX_GATE=1 ENABLE_GX_DATA_DOCS=1 make cdc-run-products-prod` — after ~30s, verify `data-platform/governance/gx-runtime/uncommitted/validations/products_cdc_suite/` contains at least one JSON.
- [ ] 4.2 `make up-gx-docs`, then `curl -sI http://localhost:8890/` returns `200 OK`, and the browser view shows the `products_cdc_suite` suite.
- [ ] 4.3 Trigger a DLQ-inducing row (insert a Postgres row with `price < 0` if the suite has a range expectation, or `name IS NULL` for a not-null check) and verify:
  - Inline gate routes the bad row to `products_cdc_dlq` (existing behavior, unchanged).
  - GX validation records the same failure in the next `ValidationResult` JSON.
  - `curl -sG http://localhost:9090/api/v1/query --data-urlencode 'query=gx_expectation_success_ratio' | jq '.data.result | length'` returns > 0.
  - Grafana `Data Governance Overview` dashboard shows the two new panels populated.
- [ ] 4.4 Idempotency: kill Spark, restart it, confirm the runner picks up the same suite and continues writing without re-uploading old validations.
- [ ] 4.5 Opt-out sanity: unset `ENABLE_GX_DATA_DOCS`, restart Spark, verify no writes to `uncommitted/validations/` after new batches.

## 5. Archive

- [ ] 5.1 Run `openspec validate --changes --specs` — all pass.
- [ ] 5.2 `openspec archive add-gx-data-docs --yes`.
- [ ] 5.3 Verify main specs post-archive: new `data-quality-reporting` capability with 5 requirements; `data-governance/gx-batch-validation`, `analytics/grafana-dashboard-provisioning`, `infrastructure/per-service-targets` all MODIFIED.
- [ ] 5.4 Tick post-archive tasks in the archived file.
