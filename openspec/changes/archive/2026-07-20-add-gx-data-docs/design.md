## Context

The inline GX gate in `data-platform/streaming/spark/src/governance/quality.py` is a hand-written subset of Great Expectations: it understands `expect_column_values_to_not_be_null`, `expect_column_values_to_be_in_set`, `expect_column_values_to_be_between`, and `expect_column_value_lengths_to_be_between` with per-expectation `mostly` semantics. It is fast (pure Spark, no JVM crossings, no serialization) and it is authoritative — a row that fails goes to DLQ, full stop. What it doesn't do is *report*: no HTML pages, no per-expectation success ratios, no batch-over-batch trending, no browseable suite documentation.

Great Expectations proper ships all of the above via **Data Docs**: HTML pages built from `ValidationResult` objects that get persisted to a `validations_store`. Wiring GX proper into a Spark streaming job has two well-known frictions:

1. **`SparkDFDataset` is memory-hungry** — GX evaluates the full DataFrame into a plan that materializes intermediate results. On a 10s micro-batch this is fine; on backpressure-driven larger batches it can spike.
2. **`ValidationResult` write is synchronous** — happens on the driver, blocks the next batch. Filesystem write of ~5-30KB per validation is trivial in practice but must not race with the Data Docs *rebuild* which reads the same directory.

Both are known and manageable. The approach here isolates GX proper to a **second-pass validation** that runs *after* the inline gate has already made the row-drop decision. GX sees whatever the inline gate would have written to ClickHouse (i.e. `valid` DataFrame post-filter) — meaning:
- GX validation cannot influence what lands in ClickHouse (inline gate is authoritative).
- GX's `success_ratio` computation matches what the inline gate does (both look at the same rows), so operator reports don't contradict pipeline behavior.
- If GX crashes or times out, the gate has already committed the decision.

Alternative rejected: swap the inline gate for real GX entirely. Would eliminate the "two implementations of the same expectation" duplication, but at the cost of losing sub-second latency and forcing GX as a hard dep. Not worth it for a demo stack; the follow-up `add-gx-only-mode` change can reconsider.

## Goals / Non-Goals

**Goals:**
- Enable a **Data Docs site** at `http://localhost:8890` browsable per-suite, per-batch, per-expectation.
- Persist every batch's `ValidationResult` to a filesystem store that survives container restarts.
- Emit Prometheus metrics `gx_suite_success_ratio{table,suite}` and `gx_expectation_success_ratio{table,expectation_type,column}` for Grafana consumption.
- Two new Grafana panels on the existing `Data Governance Overview` dashboard.
- Zero impact on the pipeline hot path when `ENABLE_GX_DATA_DOCS` is unset.

**Non-Goals:**
- Replacing the inline gate. GX proper is a second-pass reporter, not the gate.
- CI-time suite linting (a separate `add-gx-ci-checks` change).
- Automatic suite generation from data profiling. Operators author suites by hand; profiling is a future concern.
- Suite versioning / migration between GX 0.18 and 1.x. Pin to 0.18.x and revisit.
- Cross-batch aggregation window in the site itself (GX only shows per-batch); trending is Grafana's job.

## Decisions

### D1. Two-pass validation, GX runs after the gate

```
batch_df ──▶ _validate_with_gx (inline)  ──┬──▶ valid_df ──▶ ClickHouse
                                            └──▶ invalid_df ──▶ DLQ

  (sequential, same driver thread, when ENABLE_GX_DATA_DOCS=1:)
                            ▼
              GxSuiteRunner.validate_and_persist(batch_df)
                            ▼
              /opt/gx/uncommitted/validations/<suite>/<ts>.json
                            ▼
              Data Docs rebuild → /opt/gx/data-docs/
```

Rationale for running GX on `batch_df` (the pre-gate df), not `valid_df`:
- We want GX's per-expectation success ratio to reflect the *actual* population, including the rows the gate is about to drop. Otherwise every ratio would show 100% (the gate already filtered failures out).
- Cost: GX re-does work the inline gate did. Accepted: this is opt-in observability, latency is not on the critical path.

**Call-site contract**: `with_gx_gate` retains a reference to the original `batch_df` (the DataFrame it received as input) and passes *that* to `GxSuiteRunner.validate_and_persist`, not `valid_df`. The runner call happens *after* the inline gate's `valid_df`/`invalid_df` split so that any inline-gate exceptions surface first, but the DataFrame handed to GX is always the pre-gate population.

### D2. Filesystem-backed stores, bind-mounted

Every GX store (`expectations_store`, `validations_store`, `checkpoint_store`) uses `class_name: TupleFilesystemStoreBackend` rooted at `/opt/gx/` inside the Spark container. `/opt/gx/` bind-mounts from `data-platform/governance/gx-runtime/` on the host, so:

- Suite definitions live in `expectations/` (checked into git alongside the JSON suites — the two representations coexist during the transition).
- `ValidationResult`s land in `uncommitted/validations/` (git-ignored — high churn, ~1 file per batch × ~360 batches/hour).
- Data Docs render to `uncommitted/data_docs/local_site/` (git-ignored — regenerable from validations).

Nginx sidecar bind-mounts `data-platform/governance/gx-runtime/uncommitted/data_docs/local_site/` read-only and serves `index.html`.

Alternative rejected: S3-backed stores. Adds an S3 dep to a purely-local stack; the filesystem store is what GX ships and works exactly the same shape for `docker-compose`.

### D3. Nginx sidecar, opt-in via `docker-compose.gx-docs.yml`

Runs `nginx:alpine` (~10MB image, ~15MB memory) mounted at port 8890. Not included in `make up` — separate `make up-gx-docs` / `down-gx-docs`, mirroring the `up-governance` / `down-governance` model for OpenMetadata.

Rationale for opt-in-not-default:
- Data Docs is a diagnostic tool, not steady-state observability like Grafana. Operators reach for it during an incident.
- Adds a port + container to `make up` for a feature most sessions won't use.
- Enabling later is trivial: `make up-gx-docs`.

The nginx image is amd64+arm64 native so no `platform:` pin needed.

### D4. Prometheus metrics via textfile collector

Instead of standing up yet-another exporter, extend the existing `node-exporter` service (in `docker-compose.observability.yml`) with the `textfile` collector, then have the runner drop a `gx.prom` file that node-exporter picks up on its next scrape.

**Shared bind-mount** (both containers see the same directory):
- Host path: `data-platform/governance/gx-runtime/textfile/`
- Spark container: mounted at `/opt/gx/textfile/` — the runner writes `gx.prom` here.
- node-exporter container: mounted at `/etc/textfile_collector/` — read-only.
- node-exporter `command:` gains `--collector.textfile.directory=/etc/textfile_collector`.

Both the compose change (add `--collector.textfile.directory` flag + the read-only mount to node-exporter) and the Spark-side write path are part of this change; the current node-exporter service does *not* yet have the textfile collector wired up.

The write happens **inline** at the end of every `GxSuiteRunner.validate_and_persist` call — no threading, no cron. Contents:

```
# HELP gx_suite_success_ratio Fraction of expectations that passed in the latest ValidationResult per suite.
# TYPE gx_suite_success_ratio gauge
gx_suite_success_ratio{table="products",suite="products_cdc_suite"} 0.85

# HELP gx_expectation_success_ratio Latest per-expectation success ratio.
# TYPE gx_expectation_success_ratio gauge
gx_expectation_success_ratio{table="products",expectation_type="expect_column_values_to_not_be_null",column="id"} 1.0
gx_expectation_success_ratio{table="products",expectation_type="expect_column_values_to_be_between",column="price"} 0.82
```

Alternative rejected: parse `ValidationResult` on the Prometheus scrape side (e.g. a mini HTTP endpoint). Two extra things to maintain; textfile is idiomatic for offline exporters.

### D5. Store transition: keep the JSON suites, add GX-format suites

Existing `data-platform/governance/expectations/{table}_cdc_suite.json` are hand-authored in a hybrid schema that the inline gate understands. GX proper needs its canonical schema (with `meta`, `data_asset_type`, `expectations` array of concrete Python-class references). Rather than converting one format to the other at runtime — which risks drift — we ship *both* representations:

- `data-platform/governance/expectations/{table}_cdc_suite.json` — inline-gate format (unchanged).
- `data-platform/governance/gx-runtime/expectations/{table}_cdc_suite.json` — GX canonical format (new).

Convertor script `scripts/gx_convert_suites.py` runs during Phase 1 to generate the GX format from the inline format. Suites are hand-reviewed once; both files are committed. Drift concern: the convertor is idempotent, so re-running it after a suite edit keeps them in sync. Long-term: `add-gx-only-mode` collapses to one format.

### D6. Grafana panel wiring

Extend the existing `data-governance-overview.json` dashboard (already provisioned by `add-data-governance` Phase 3) with:

**Panel A — "GX Suite Success Rate (24h)"**  
Query: `avg_over_time(gx_suite_success_ratio[24h])` grouped by `table`. Bar gauge. Thresholds: red < 0.9, yellow 0.9-0.98, green >= 0.98.

**Panel B — "Top 5 Failing Expectations"**  
Query: `bottomk(5, gx_expectation_success_ratio)`. Table with columns `table`, `expectation_type`, `column`, `success_ratio`.

Both panels include a `links` array pointing at `http://localhost:8890` for drilldown.

Alternative rejected: separate dedicated dashboard. The existing "Data Governance Overview" is the right place — operators already look there for gate metrics.

### D7. Package version pinning

`great_expectations[spark] == 0.18.19` (latest of the 0.18 line at time of writing), declared in a project-local uv optional-dependency extra named `gx-docs`. Install with `uv sync --extra gx-docs`. Pinning matters here because GX 1.x rewrote the whole checkpoint / datasource API, and this design is written against 0.18's `SparkDFDataset`. A future `add-gx-1x-upgrade` change handles the transition when we're ready.

The `[spark]` marker pulls in GX's Spark integration; `spark = "3.5.0"` is already vendored.

## Risks / Trade-offs

- **[Risk] GX validation on large backpressure batches slows the streaming query** → Mitigation: `ENABLE_GX_DATA_DOCS` is opt-in. If enabled and slow, operators disable and the pipeline goes back to inline-gate-only. Also, `SparkDFDataset` evaluates lazily; the actual cost is bounded by the batch size which the trigger interval caps.
- **[Risk] Filesystem store fills over time** → Mitigation: `uncommitted/validations/` grows ~1 file per batch × 360 batches/hour × 24h × 7 days = ~60k files. At ~10KB each = ~600MB. Ship a lightweight cleanup: retain last 24h + last 100 per suite, invoked at the tail of every validate call. Simpler than an external cron.
- **[Risk] Nginx sidecar reads files that GX is still writing** → Mitigation: Data Docs writes are atomic (GX writes to a temp file + rename). Reads during a rename see either the pre- or post-image, never a partial. Standard filesystem semantics.
- **[Risk] Textfile collector picks up stale `gx.prom` when Spark job is off** → Mitigation: node-exporter's textfile collector emits `node_textfile_mtime_seconds` and `node_textfile_scrape_error` metrics; an alert can fire if `gx.prom` mtime is > 15 min old (deferred to a separate observability tuning change).
- **[Trade-off] Two suite representations (inline JSON + GX canonical)** → Accepted: one-time convertor cost, no runtime cost. Aligns with the "coexist during transition" pattern used elsewhere in this repo (legacy `{table}_dlq` topics alongside `{table}_cdc_dlq`).
- **[Trade-off] GX 0.18 pinned, not the latest** → Accepted: GX 1.x API rewrite is a bigger change than this one. Deferred.
