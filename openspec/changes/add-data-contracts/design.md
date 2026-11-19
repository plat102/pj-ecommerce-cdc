## Context

The CDC pipeline currently maintains schema knowledge in four disconnected artifacts:

| Layer | File | Owns |
|---|---|---|
| Source | `infrastructure/docker/postgres/init.sql` | `SERIAL`, `TEXT`, `NUMERIC(10,2)`, `TIMESTAMP` — Postgres types |
| Stream parse | `data-platform/streaming/spark/src/schemas/cdc_schemas.py` | `IntegerType`, `StringType`, `LongType` on the Debezium `after` envelope |
| Sink | `infrastructure/docker/clickhouse/create_tables.sql` | `Int64`, `String`, `Decimal(10,2)`, plus metadata columns (`_version`, `_deleted`) |
| Wire (runtime) | Apicurio Registry, populated by Debezium | Avro payloads with base64-encoded `Decimal` |

There is no automated check that these four agree. Adding `orders.discount NUMERIC` to Postgres without a matching ClickHouse column silently drops the field at the Spark parser — the row still writes, but the analytics store is missing data.

The existing type mismatches are **intentional** and must survive contract adoption:
- Postgres `SERIAL` (int32) → ClickHouse `Int64` (widening for future volume headroom)
- `NUMERIC` → Debezium base64 → Spark `StringType` → `decode_decimal_udf` → ClickHouse `Decimal(10,2)` (gotcha documented in `docs/governance.md`)
- `TIMESTAMP` → Debezium `LongType` (microseconds since epoch) → ClickHouse `Int64` (stored as int, formatted downstream)

A contract format must express these deliberate transformations, not flag them as drift.

**The reconciliation gap.** With `add-om-ingestion` and `add-spark-openlineage` in flight, the pipeline will soon have three overlapping views of the *same* table graph:

| View | Source | Update cadence | What it claims |
|---|---|---|---|
| Contract (this change) | Hand-written YAML | PR-time | Declared intent (columns, types, PII, ownership) |
| OpenMetadata catalog | `make ingest-all` (on-demand) | Manual / CI-triggered | Observed schema as scraped from live Postgres + ClickHouse |
| GX suites | Hand-written JSON | PR-time | Runtime quality expectations, batch-checked |

DE and DA both consult these views when re-checking data. Without cross-checks, all three can drift independently — three sources of truth means zero. This change closes the schema half of the gap: the drift test treats OM's ingested view as a fifth layer, so a contract change that isn't reflected in OM (because `ingest-all` wasn't re-run) is a PR-blocking signal. The *semantic* half of the gap (contract PII annotations ↔ GX expectation shapes) is explicitly deferred — see Decision 11.

## Goals / Non-Goals

**Goals:**
- One YAML file per CDC table declaring the canonical column list, types, and PII handling — human-readable, machine-parseable.
- Drift test that catches accidental divergence in any of the four layers **at PR time**, not at runtime.
- Zero runtime code changes. Contracts are pure documentation with teeth.
- Alignment with the broader industry: ODCS v3.1 is Linux Foundation-governed; adopting it means downstream tools (catalog import, code generation) become accessible without rework.
- Explicit annotation for cross-layer transformations (PII masking, decimal decoding, ID widening) so drift detection has a signal for "expected difference".

**Non-Goals:**
- Code generation from contracts. Phase 3, if ever. Existing schema files stay hand-maintained; the contract validates them, doesn't replace them.
- Runtime enforcement. GX gate + DLQ topology stay authoritative for row-level rejection. Contracts describe intent, GX enforces it.
- Full Avro/Kafka wire-format validation. Apicurio remains the runtime authority for Kafka payload shape; the contract references topic names only.
- Contract versioning, BACKWARD/FORWARD compatibility rules, schema evolution semantics. Overkill for 3 tables and 1 producer.
- ClickHouse `Decimal` precision/scale exact match. Phase 1+2 compares logical type family (`decimal`), not `(10,2)` specifically.
- **Publishing contracts INTO OpenMetadata** (`datacontract publish` → OM catalog entry). Deferred. This change reads FROM OM to cross-check the observed schema against the declared contract; it does not push contract metadata into OM.
- **Contract ↔ GX semantic reconciliation.** Checking that a contract PII annotation (e.g., `pii=hash`) is matched by a corresponding GX expectation (e.g., `regex_matches` on `^[a-f0-9]{64}$`) requires a project-local PII vocabulary that does not exist yet. Deferred to a follow-up change once we have more than three tables and two PII columns to inform the mapping. See Decision 11.

## Decisions

### Decision 1: ODCS v3.1 as the contract format

**Choice:** Adopt Open Data Contract Standard v3.1 (bitol-io / Linux Foundation) as the YAML format.

**Alternatives considered:**
- **AsyncAPI 3.0** — strong for external event APIs, weak on data-quality/SLA/ownership. Fits Kafka layer but not the full source→sink picture. Would need supplementary format for Postgres/ClickHouse.
- **Custom minimal YAML** — fastest to write, vendor-locked to this repo. Zero downstream tool support. Rejected as false economy.
- **dbt contracts** — tied to dbt, which the repo doesn't use. Coverage is warehouse-only, no source/stream layer.
- **JSON Schema / Avro alone** — schema-only, no ownership/quality/SLA semantics. Better used as a payload block *inside* ODCS.

**Rationale:**
- Linux Foundation governance (via Bitol) — stable, community-maintained, not a single-vendor artifact.
- `datacontract-cli` v1.0.13 (released 2026-07-14) has native connectors for Postgres, Kafka, Spark, and ClickHouse — a direct fit for this stack.
- Covers exactly what's needed: schema + quality + ownership + servers. Not so bloated that a 3-table pipeline chokes on ceremony.
- Migration path: if we later need code generation or catalog integration, ODCS is what the tools expect.

### Decision 2: One contract per CDC table, not per environment

Files: `data-platform/governance/contracts/customers.yaml`, `products.yaml`, `orders.yaml`.

**Rejected:** one giant `pipeline.yaml`. Would obscure per-table ownership and make diffs noisy.

**Rejected:** contract per (table × environment). This is a demo pipeline with one environment; multiplying files by env is overhead without benefit.

Each contract's `id` matches the source-table name (e.g., `customers-cdc`). Namespacing (`ecommerce.customers`) is out of scope for a single-domain pipeline.

### Decision 3: Encoding cross-layer transformations

The contract declares the **source column** as the anchor. Transformations to sink are encoded as ODCS `customProperties` on each column, then the drift test consumes them to relax the equality check.

Example (`customers.yaml`, column `email`):
```yaml
- name: email
  logicalType: string
  required: true
  customProperties:
    - property: pii.classification
      value: sensitive
    - property: sink.transformation
      value: sha256_salted
    - property: sink.expected_type
      value: string  # after hashing, it's a hex string
```

Example (`products.yaml`, column `price`):
```yaml
- name: price
  logicalType: decimal
  required: true
  precision: 10
  scale: 2
  customProperties:
    - property: wire.encoding
      value: debezium_base64_decimal
    - property: wire.decoder
      value: decode_decimal_udf
    - property: spark.parse_type
      value: string  # Spark receives base64 as string, decodes downstream
```

The drift test reads `spark.parse_type` when comparing against `cdc_schemas.py`, and `sink.expected_type` when comparing against ClickHouse DDL. Absent those annotations, direct type mapping applies.

**Alternative rejected:** two contract files per table (`source.yaml` + `sink.yaml`). Doubles the artifact count for no gain — the source→sink transformation is small and stable.

### Decision 4: Type mapping table (contract → each layer)

Drift test uses this canonical mapping. Deviations are drift unless annotated.

| ODCS `logicalType` | Postgres | Spark (Debezium after) | ClickHouse | Notes |
|---|---|---|---|---|
| `integer` | `INTEGER`, `SERIAL` | `IntegerType` | `Int32`, `Int64` | CH widening accepted (Int32 → Int64) |
| `long` | `BIGINT` | `LongType` | `Int64`, `UInt64` | |
| `string` | `TEXT`, `VARCHAR(*)` | `StringType` | `String` | |
| `decimal` | `NUMERIC(p,s)` | `StringType` (base64) | `Decimal(p,s)` | Wire annotation required for `NUMERIC` |
| `timestamp` | `TIMESTAMP` | `LongType` (µs epoch) | `Int64` | Debezium encodes as long; sink stays long |
| `boolean` | `BOOLEAN` | `BooleanType` | `UInt8`, `Bool` | Not used in current 3 tables |

Precision/scale checked only when contract declares it AND all layers can express it (Postgres NUMERIC + ClickHouse Decimal — Spark passes as string, exempt).

### Decision 5: Sink-only metadata columns

`_version` and `_deleted` in ClickHouse have no Postgres/Spark counterpart. Contract declares them under a separate `properties` group with `customProperties.origin: sink_metadata`:

```yaml
- name: _version
  logicalType: long
  required: true
  customProperties:
    - property: origin
      value: sink_metadata
    - property: source
      value: debezium.ts_ms
```

Drift test skips these columns when checking Postgres and Spark layers, but requires them present in ClickHouse.

### Decision 6: GX suite coverage check

The drift test asserts that every column in the contract marked `required: true` appears in the GX suite's `expect_column_values_to_not_be_null` expectation list. This closes the loop: contract says "required", GX enforces "required". A column added to the contract without a matching GX expectation fails the test — nudging the author to update the suite.

**Not enforced:** exhaustive expectation matching. GX suites can (and do) have additional expectations beyond null checks. The drift test only asserts a **lower bound** on quality coverage.

### Decision 7: Test framework and location

`tests/contracts/test_schema_drift.py`, parametrized pytest, one test per (contract × layer) pair. Failure message quotes both sides:

```
FAIL: contract=customers.yaml layer=clickhouse
  Missing in contract: [tax_id]
  Missing in ClickHouse: []
  Type mismatch: [] 
```

Uses `sqlglot` to parse both `init.sql` and `create_tables.sql` (no need to spin up databases). `cdc_schemas.py` is parsed via `ast` — no import required, so the test runs in isolation without Spark on the path.

**Alternative rejected:** connect to running Postgres/ClickHouse in test. Adds container dependency to `make test`, defeats the goal of PR-time gate.

### Decision 8: `make test` wire-up

No new Make target. Pytest auto-collects `tests/contracts/`, and `make test` already runs `uv run pytest`. Drift test failures block the existing gate. The exit-code-5 special case in `make test` (no tests collected) is unaffected — we're adding tests, not removing.

### Decision 9: Bootstrap known-good state

First-run of the drift test against current code may reveal already-existing drift or unannotated intentional differences. The change includes a task to **run the test, fix any surprises, and commit the resulting contract files plus any minor DDL/Spark-schema corrections**. The contract's initial content is derived from current code, not from a wish list.

### Decision 10: OpenMetadata as a fifth layer with soft-fail semantics

**Choice:** Extend the drift test to treat the OM catalog as a fifth layer, cross-checked via `GET /api/v1/tables/name/{fqn}`. Unlike the four DDL/GX layers (hard gates), the OM check **soft-fails** — logs a diagnostic and skips when OM is unreachable, rather than failing `make test`. A CI hook re-runs `make ingest-all` whenever `init.sql` or `create_tables.sql` changes in a PR, so OM's view is fresh before the drift test runs.

**Rationale:**
- **The reconciliation gap requires OM to be a live participant, not a downstream consumer.** If OM is only fed from ingestion and never cross-checked, it silently drifts from the contract — exactly the "three sources of truth = zero" failure mode this change is meant to prevent.
- **Soft-fail on unreachable OM keeps `make test` runnable on dev laptops.** OM requires the governance stack (`make up-governance`), which many contributors won't have running. Making OM a hard gate would force a heavyweight dependency on every test run. The four DDL/GX layers are all parseable from files on disk with no running services, so they stay hard gates.
- **CI ingest hook prevents a race.** Without it, an author could update `init.sql`, run `make test` locally (drift test passes against static files), push, and the CI-side OM check would fail because OM's cached view is stale. Re-running `ingest-all` in CI when schema files change makes the OM layer meaningful rather than a false-positive generator.

**Parser shape:**
- `parse_om_table(fqn: str, client: OMClient) -> list[Column] | None` — returns `None` (with a logged reason) when OM is unreachable. `None` triggers `pytest.skip()` for that parametrization; a non-`None` result triggers the same column-name + type comparison as the other layers.
- Table FQNs: `ecommerce-postgres.public.customers` (source) and `ecommerce-clickhouse.ecommerce_analytics.customers_cdc` (sink) — matches the service names declared in `add-om-ingestion` ingestion YAMLs.
- OM client is a ~30-line wrapper around `httpx` (transitive dep of `datacontract-cli`); no new top-level dependency.

**CI hook (workflow surface):**
- If GHA is the CI: `.github/workflows/ingest-on-schema-change.yml` triggers on `paths: [infrastructure/docker/postgres/init.sql, infrastructure/docker/clickhouse/create_tables.sql]`, spins up the governance stack, and runs `make ingest-all` before `make test`.
- If the repo isn't on GHA yet, the same idea lives in whatever CI is used (documented in `docs/governance.md`).
- Locally, contributors can `make up-governance && make ingest-all` before `make test` to get the OM-layer check to run against a live catalog. Otherwise it silently skips.

**Alternatives considered:**
- **Make OM a hard gate.** Rejected. Kills local dev ergonomics for one added check.
- **Skip OM entirely, keep four layers.** Rejected. This is exactly the Option A "name-the-gap-and-do-nothing" that lets the three-views-drift problem grow.
- **Publish contract INTO OM (`datacontract publish`) instead of reading from it.** Deferred. Publishing makes the contract *authoritative in the catalog*; reading makes OM a *witness* against the contract. For Phase 1+2, witness is what closes the gap. Publish is a Phase 3 concern alongside code generation.

### Decision 11: Defer contract ↔ GX semantic reconciliation

**Choice:** The drift test's GX check remains a *coverage-only* lower bound (see Decision 6). No enforcement that contract PII annotations translate to specific GX expectation shapes. Deferred to a follow-up (`add-contract-pii-vocab` or similar).

**Why now would be premature:**
- **The vocabulary doesn't exist.** ODCS `customProperties` are freeform. "If `pii.classification=sensitive` then GX must have expectation X" requires a project-local mapping — and today we have exactly two PII columns (`customers.name`, `customers.email`) with two `sink.transformation` values (`sha256_salted`, `tokenize_first_initial`). That's not enough distinct cases to design a mapping without over-fitting.
- **DE and DA need to agree on the terms before enforcement.** Locking in a vocabulary now, before the audiences that consume it have written contracts for their own use cases, produces a mapping that's convenient for the change author and inconvenient for everyone else.
- **The schema half is the big win.** Column drift is the failure mode that silently loses data. Semantic PII drift (e.g., forgot to add a hash-shape check) is caught by GX runtime failures or by a manual audit — painful but not silent. Prioritizing schema over semantics matches actual impact.

**What the follow-up would look like:**
- Freeze a PII vocabulary in `docs/governance.md` (e.g., `pii.classification ∈ {sensitive, quasi-identifier, public}`; `sink.transformation ∈ {sha256_salted, tokenize_first_initial, mask_last4, drop}`).
- Add a mapping table in `tests/contracts/parsers.py`: `SEMANTIC_MAP: dict[transformation, GXExpectationKind]`.
- Extend the drift test with a new parametrization that asserts, for each PII-annotated column, that the GX suite has an expectation of the mapped kind.
- Once the mapping is stable across ~10+ tables' worth of contracts, consider moving semantic checks from drift-test to a proper linter.

**Escape valve if this bites sooner than expected:** any DE/DA can open a follow-up change proposal describing the specific pain — a real case beats a hypothetical vocabulary every time.

## Risks / Trade-offs

- **[Risk]** Contract diverges from ODCS spec as the standard evolves (v3.2, v4).
  → **Mitigation:** Pin `datacontract-cli` version in `pyproject.toml`. Bumping the pin is an explicit change with its own PR.

- **[Risk]** Drift test becomes false-positive noise (e.g., type mapping table incomplete for edge cases).
  → **Mitigation:** Keep the type mapping table centralized in `tests/contracts/parsers.py`; adding a mapping is a one-line change. If a false positive blocks urgent work, the escape hatch is `@pytest.mark.xfail(reason="...")` on the specific parametrization until the mapping is patched.

- **[Risk]** `sqlglot` misparses ClickHouse-specific DDL (e.g., `Decimal(10,2)` inside `CREATE TABLE ... ENGINE = ReplacingMergeTree`).
  → **Mitigation:** Test coverage includes all three existing tables from day one. `sqlglot` has a `read="clickhouse"` dialect flag. If parsing fails on any real DDL, fall back to targeted regex (`Decimal\(\d+,\s*\d+\)`) for the specific case.

- **[Trade-off]** Contract is descriptive, not prescriptive. It can be wrong (updated too late) and the drift test would only catch code drifting *away* from the contract, not the contract itself lying.
  → **Accepted.** Phase 3 (generation from contract) would flip this. For Phase 1+2, human review at contract-update time is the safeguard.

- **[Trade-off]** No environment-specific contracts, no versioning.
  → **Accepted.** Adding either now doubles complexity for a demo pipeline. Both are additive later without breaking the ODCS structure.

- **[Risk]** Adding `datacontract-cli` (30MB) + `sqlglot` (~4MB) to `dev` group slows `uv sync`.
  → **Mitigation:** Both are dev-only, don't ship to Docker images. Slowdown is one-time on cold cache.

## Migration Plan

**Prerequisite:** `add-om-ingestion` MUST be archived first. The OM cross-check depends on `make ingest-all` existing and the governance stack being reachable. If `add-om-ingestion` is delayed, this change can still land — the OM layer will soft-fail everywhere until ingestion is available, degrading gracefully to the four-layer check.

**Rollout (single PR):**
1. Add contracts + drift test + Makefile untouched (test picked up automatically).
2. Bring up governance stack: `make up-governance && make ingest-all` (from `add-om-ingestion`). Populates OM with observed schema.
3. Run `make test` locally. Fix any drift surfaced (either update the code to match contract, or update contract to match code — decide per column, favoring the sink DDL as it's the analytical contract). If OM diverges from contract, re-run `make ingest-all` or update the contract.
4. Commit contracts + test + CI ingest-on-schema-change hook + any corrections.

**Rollback:**
- Delete `data-platform/governance/contracts/` and `tests/contracts/`. No runtime dependency; no data migration; no state cleanup.
- Remove `datacontract-cli` and `sqlglot` from `pyproject.toml` `dev` group.
- Remove the CI ingest-on-schema-change hook (self-contained workflow file).

## Open Questions

- **Should the contract declare `_dlq` topics as related outputs?** Deferred. DLQ topology is documented in `docs/governance.md`; adding it to the contract couples two orthogonal concerns.
- **Should we publish contracts to OpenMetadata via `datacontract publish`?** Deferred to Phase 3. This change makes OM a *witness* against the contract (read-only cross-check); publishing would make the contract *authoritative in the catalog* — a bigger change with implications for OM's UI and downstream tooling.
- **Precision/scale strictness for `Decimal`?** Phase 1+2 checks logical type only. If we grow to more `NUMERIC` columns with varying precision, tightening becomes worth the effort.
- **When to freeze the PII vocabulary?** See Decision 11. The trigger will be either (a) DE or DA writing a contract and hitting a case the current freeform annotations can't express, or (b) accumulated table count crossing a threshold where ad-hoc annotations become unmanageable (rough guess: ~8–10 tables).
