# data-quality-reporting Specification

## Purpose
TBD - created by archiving change add-gx-data-docs. Update Purpose after archive.
## Requirements
### Requirement: gx-real-engine-runner
When `ENABLE_GX_DATA_DOCS=1` is set for a Spark CDC job, the job SHALL run a second-pass validation via the real Great Expectations engine (`SparkDFDataset`, pinned to `great_expectations>=0.18,<0.19`) on every micro-batch, in addition to the inline gate. The GX runner SHALL be invoked with the pre-gate DataFrame (so per-expectation success ratios reflect the actual population, including rows the gate is about to drop). The GX runner SHALL NOT influence the row-drop decision; the inline gate remains the authoritative gate.

#### Scenario: GX runs alongside the gate when opt-in
- **WHEN** a Spark CDC job runs with `ENABLE_GX_GATE=1 ENABLE_GX_DATA_DOCS=1`
- **THEN** for every micro-batch the inline gate SHALL execute AND `GxSuiteRunner.validate_and_persist(batch_df, table)` SHALL execute
- **AND** the set of rows written to ClickHouse SHALL match the set the inline gate produced (GX cannot influence row landing)

#### Scenario: GX does not run when opt-out
- **WHEN** `ENABLE_GX_DATA_DOCS` is unset or not `"1"`
- **THEN** `great_expectations` SHALL NOT be imported by the Spark job (verified by no GX log lines and no writes to `gx-runtime/uncommitted/`)

### Requirement: gx-validation-store-filesystem
Every `ValidationResult` produced by the GX runner SHALL be persisted to a filesystem-backed store rooted at `/opt/gx/uncommitted/validations/<suite_name>/` inside the Spark container, which SHALL be bind-mounted from `data-platform/governance/gx-runtime/uncommitted/validations/` on the host so results survive container restarts. The GX project configuration SHALL live at `data-platform/governance/gx-runtime/great_expectations.yml` (co-located with the store root, so `/opt/gx/great_expectations.yml` inside the container) and declare `TupleFilesystemStoreBackend` for `expectations_store`, `validations_store`, and `checkpoint_store`.

#### Scenario: validation persists after container restart
- **WHEN** a validation runs, then the Spark container is restarted
- **THEN** the `ValidationResult` JSON SHALL still be readable at `data-platform/governance/gx-runtime/uncommitted/validations/<suite>/*.json` on the host

#### Scenario: retention keeps store bounded
- **WHEN** more than 100 `ValidationResult` files exist for a given suite in the store
- **THEN** the runner SHALL delete the oldest entries so that at most 100 per suite AND entries older than 24 hours are pruned

### Requirement: gx-data-docs-http-site
An HTTP site SHALL serve the compiled GX Data Docs at `http://localhost:8890`. The site SHALL be served by an `nginx:alpine` sidecar container `gx-data-docs-server` declared in `infrastructure/docker/docker-compose.gx-docs.yml`, bind-mounted read-only against `data-platform/governance/gx-runtime/uncommitted/data_docs/local_site/`. The site SHALL be opt-in — not started by `make up`, but by dedicated `make up-gx-docs` / `make down-gx-docs` targets.

#### Scenario: site available after up-gx-docs
- **WHEN** `make up-gx-docs` runs and at least one validation has produced Data Docs output
- **THEN** `curl -sf http://localhost:8890/` SHALL return HTTP 200 with the site index

#### Scenario: site absent by default
- **WHEN** `make up` completes without invoking `up-gx-docs`
- **THEN** no `gx-data-docs-server` container SHALL appear in `docker ps`

### Requirement: gx-prometheus-metrics-textfile
The GX runner SHALL write a Prometheus text-format file at `/opt/gx/textfile/gx.prom` (host path: `data-platform/governance/gx-runtime/textfile/gx.prom`) at the tail of every validation call, using an atomic write (temp file + rename) to avoid partial reads. The metrics exposed SHALL be `gx_suite_success_ratio{table,suite}` and `gx_expectation_success_ratio{table,expectation_type,column}`. The `node-exporter` service (from `add-infra-observability`) SHALL be extended by this change: (a) its `command:` gains `--collector.textfile.directory=/etc/textfile_collector`, and (b) the same host directory `data-platform/governance/gx-runtime/textfile/` SHALL be bind-mounted read-only at `/etc/textfile_collector/` on `node-exporter`. Prometheus SHALL then scrape these metrics via the existing node-exporter job.

#### Scenario: metrics visible in Prometheus
- **WHEN** a validation has completed successfully with `ENABLE_GX_DATA_DOCS=1`
- **THEN** `curl -sG http://localhost:9090/api/v1/query --data-urlencode 'query=gx_suite_success_ratio' | jq '.data.result | length'` SHALL return a value > 0

#### Scenario: metric labels match spec
- **WHEN** a metric line for `gx_expectation_success_ratio` is inspected
- **THEN** it SHALL carry the labels `table`, `expectation_type`, and `column`

### Requirement: gx-suite-two-representations
Suites SHALL exist in two representations during the transition period: the inline-gate format at `data-platform/governance/expectations/{table}_cdc_suite.json` (unchanged from `add-data-governance` Phase 3) AND the GX canonical format at `data-platform/governance/gx-runtime/expectations/{table}_cdc_suite.json`. A convertor script `scripts/gx_convert_suites.py` SHALL generate the second from the first idempotently.

#### Scenario: both representations stay in sync via convertor
- **WHEN** an operator edits a suite JSON at the inline-gate path and runs `python scripts/gx_convert_suites.py`
- **THEN** the corresponding GX-format file SHALL be regenerated with the same expectations set
- **AND** re-running the convertor SHALL produce a byte-identical output (idempotent)

