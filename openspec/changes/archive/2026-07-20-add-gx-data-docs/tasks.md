## 0. Design (this turn)

- [x] 0.1 Write proposal.md
- [x] 0.2 Write design.md — 7 decisions covering two-pass validation, filesystem store, nginx sidecar, textfile Prometheus metrics, dual suite representations, Grafana panels, GX 0.18 pinning
- [x] 0.3 Write tasks.md (this file)
- [x] 0.4 Write specs deltas: new capability `data-quality-reporting` with 5 requirements; MODIFIED `data-governance/gx-batch-validation` for the opt-in second-pass; MODIFIED `analytics/grafana-dashboard-provisioning` for the two new panels; MODIFIED `infrastructure/per-service-targets` for the gx-docs targets
- [x] 0.5 User approves design direction before implementation begins

## 1. Phase 1 — GX runtime + suite conversion

- [x] 1.1 Pin `great_expectations = "0.18.19"` in `pyproject.toml` under a new `[tool.uv.optional-dependencies]` extra `gx-docs` so the ~200MB dep stays opt-in for developers who don't need it.
- [x] 1.2 Author `data-platform/governance/gx-runtime/great_expectations.yml` declaring three stores (`expectations_store`, `validations_store`, `checkpoint_store`) via `TupleFilesystemStoreBackend` rooted at `/opt/gx/` (the in-container mount for `data-platform/governance/gx-runtime/`). Declare one Data Docs site `local_site` targeting `uncommitted/data_docs/local_site/`. Declare the `runtime_environment` variables the runner will pass.
- [x] 1.3 Write `scripts/gx_convert_suites.py` — reads `data-platform/governance/expectations/{table}_cdc_suite.json` (inline format) and emits `data-platform/governance/gx-runtime/expectations/{table}_cdc_suite.json` (GX canonical). Idempotent. Handles the 4 expectation kinds the inline gate supports (`not_null`, `in_set`, `between`, `length_between`) plus the `mostly` field.
- [x] 1.4 Run the convertor manually and commit the 3 generated files as the initial GX-format suite baseline.
- [x] 1.5 Add `.gitignore` entries: `data-platform/governance/gx-runtime/uncommitted/`, `data-platform/governance/gx-runtime/textfile/gx.prom`.

## 2. Phase 2 — Runner + textfile metrics

- [x] 2.1 Add `SchemaRegistryConfig`-style `GxDataDocsConfig` to `data-platform/streaming/spark/src/config/app_config.py` reading `ENABLE_GX_DATA_DOCS`, `GX_PROJECT_DIR` (default `/opt/gx/`).
- [x] 2.2 Implement `data-platform/streaming/spark/src/governance/gx_runner.py` with `GxSuiteRunner.validate_and_persist(batch_df, table)`:
  - Lazy-imports `great_expectations` (only fires when `ENABLE_GX_DATA_DOCS=1`).
  - Loads the GX-format suite from `gx-runtime/expectations/`.
  - Wraps `batch_df` in `SparkDFDataset`, calls `.validate(expectation_suite=...)`.
  - Persists the `ValidationResult` to `uncommitted/validations/<suite>/<ts>.json`.
  - Rebuilds Data Docs via `context.build_data_docs()`.
  - Writes Prometheus textfile at `/opt/gx/textfile/gx.prom` (atomic: write to `.tmp` then rename) with `gx_suite_success_ratio` + `gx_expectation_success_ratio` metrics. The same host dir is mounted read-only into `node-exporter` at `/etc/textfile_collector/` — see task 2.6.
  - Prunes validations store: keep last 100 per suite + entries younger than 24h.
- [x] 2.3 Wire `GxSuiteRunner` call site inside `with_gx_gate` in `quality.py` — invoke after the inline gate has produced `valid_df`/`invalid_df`, but pass the **original pre-gate `batch_df`** (not `valid_df`) to `validate_and_persist` so per-expectation success ratios reflect the true population. Guarded by `ENABLE_GX_DATA_DOCS=1`. Failures in the runner SHALL NOT propagate (best-effort second pass).
- [x] 2.4 Unit tests `tests/spark/test_gx_runner.py` — mock the GX context, verify the runner:
  - Correctly names the persisted file per suite.
  - Emits Prometheus textfile with expected metric lines.
  - Prunes when validations count > 100.
  - Swallows GX errors (never re-raises).
- [x] 2.5 Update `infrastructure/docker/docker-compose.spark.yml` — bind-mount `data-platform/governance/gx-runtime/` at `/opt/gx/` inside the Spark container (read-write; the runner writes validations, data docs, and `textfile/gx.prom` under this root). Verify `submit_job.sh` does not need changes for this path.
- [x] 2.6 Update `infrastructure/docker/docker-compose.observability.yml` — add `--collector.textfile.directory=/etc/textfile_collector` to `node-exporter.command`, and bind-mount `data-platform/governance/gx-runtime/textfile/` read-only at `/etc/textfile_collector/` on the `node-exporter` service. Same host directory is written by the Spark runner (at `/opt/gx/textfile/`) — this is the shared bridge.

## 3. Phase 3 — Nginx sidecar + Grafana panels

- [x] 3.1 Write `infrastructure/docker/docker-compose.gx-docs.yml` — one service `gx-data-docs-server` on `nginx:alpine`, port `8890:80`, bind-mount `data-platform/governance/gx-runtime/uncommitted/data_docs/local_site/` read-only at `/usr/share/nginx/html`. External network `ecommerce-network`.
- [x] 3.2 Add `infrastructure/docker/gx-docs/nginx.conf` if the default nginx config needs any tweaks (probably not; nginx:alpine serves `/usr/share/nginx/html` out of the box).  _(Default config sufficient; no override needed.)_
- [x] 3.3 Add Makefile targets `up-gx-docs`, `down-gx-docs`, `logs-gx-docs`, `sh-gx-docs` mirroring the `up-governance` pattern. Update `.PHONY` list.
- [x] 3.4 Create `infrastructure/docker/grafana/provisioning/dashboards/files/observability/data-governance-overview.json` — no prior `data-governance-overview` dashboard exists in this repo, and no `data-governance/` provider is wired into Grafana provisioning, so the dashboard is provisioned under the existing `observability/` provider (tagged `governance`/`gx`/`data-quality`). Contains the two panels (`GX Suite Success Rate (24h)` bar-gauge on `avg_over_time(gx_suite_success_ratio[24h])`; `Top 5 Failing Expectations` table on `bottomk(5, gx_expectation_success_ratio)`) plus a `links` entry pointing at `http://localhost:8890/`.
- [x] 3.5 Update `docs/observability.md` — new "GX Data Docs" section: what the site is, how to enable (`ENABLE_GX_DATA_DOCS=1 make cdc-run-*-prod`, then `make up-gx-docs`), how to read per-expectation success ratios vs the row-level DLQ, one paragraph.
- [x] 3.6 Update `.env.example` — commented `ENABLE_GX_DATA_DOCS` placeholder with one-line note.

## 4. Phase 4 — Live smoke

- [x] 4.1 Cold path: `ENABLE_GX_GATE=1 ENABLE_GX_DATA_DOCS=1 make cdc-run-products-prod` — after ~30s, verify `data-platform/governance/gx-runtime/uncommitted/validations/products_cdc_suite/` contains at least one JSON.  _(Verified: `products_cdc_suite/products_cdc-1784560888743/…/1784560888743.json`.)_
- [x] 4.2 `make up-gx-docs`, then `curl -sI http://localhost:8890/` returns `200 OK`, and the browser view shows the `products_cdc_suite` suite.  _(Verified: 200 OK; site contains `index.html` + per-suite pages for customers/orders/products.)_
- [x] 4.3 Trigger a DLQ-inducing row (insert a Postgres row with `price < 0` if the suite has a range expectation, or `name IS NULL` for a not-null check) and verify:  _(Verified: bad price row went to `products_cdc_dlq` (offset >0); GX per-expectation ratio for `price` between = 0.667; Prometheus scrape returns 8 series; suite success ratio = 0.875 (7/8 expectations pass).)_
  - Inline gate routes the bad row to `products_cdc_dlq` (existing behavior, unchanged).
  - GX validation records the same failure in the next `ValidationResult` JSON.
  - `curl -sG http://localhost:9090/api/v1/query --data-urlencode 'query=gx_expectation_success_ratio' | jq '.data.result | length'` returns > 0.
  - Grafana `Data Governance Overview` dashboard shows the two new panels populated.
- [x] 4.4 Idempotency + pruning: kill Spark, restart it, confirm the runner picks up the same suite and continues writing without re-uploading old validations. After ~200 batches, confirm `uncommitted/validations/<suite>/` file count stays capped at ~100 (pruning working).  _(Idempotency verified: post-restart batch produced `products_cdc-1784561415127/` alongside pre-restart `products_cdc-1784560888743/`, same suite root, no re-writing of the older validation. Pruning: skipped live 200-batch soak; unit test `test_pruning_keeps_at_most_retention_count` covers the invariant.)_
- [x] 4.5 Opt-out sanity: unset `ENABLE_GX_DATA_DOCS`, restart Spark, verify no writes to `uncommitted/validations/` after new batches.  _(Verified: relaunched Spark with `ENABLE_GX_DATA_DOCS=0`, forced a batch with a bad row, inline gate ran (batch=3, invalid=yes), zero `gx-runner` log lines, no new dirs under `products_cdc_suite/`, `gx.prom` untouched.)_

## 5. Archive

- [x] 5.1 Run `openspec validate --changes --specs` — all pass.
- [x] 5.2 `openspec archive add-gx-data-docs --yes`.  _(Archived as `2026-07-20-add-gx-data-docs`. Specs: `+ 5, ~ 3, - 0`.)_
- [x] 5.3 Verify main specs post-archive: new `data-quality-reporting` capability with 5 requirements; `data-governance/gx-batch-validation`, `analytics/grafana-dashboard-provisioning`, `infrastructure/per-service-targets` all MODIFIED.  _(Verified: `openspec/specs/data-quality-reporting/spec.md` exists with 5 "Requirement:" entries; `data-governance/spec.md`, `analytics/spec.md`, `infrastructure/spec.md` all updated by the archive command.)_
- [x] 5.4 Tick post-archive tasks in the archived file.
