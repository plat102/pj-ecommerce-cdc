## Context

The ecommerce CDC platform has a working pipeline (Postgres → Debezium → Kafka → Spark → ClickHouse → Grafana) and a clean OpenSpec contract, but **no data governance layer**. Today:

- Schemas are implicit Spark `StructType`s; Debezium uses plain JSON. No registry, no evolution control. (README's "Future Enhancements" already calls this out.)
- PII columns (`customers.name`, `customers.email`) flow **unmasked** through Kafka topics that are visible in Redpanda Console and land plaintext in ClickHouse.
- No data quality framework. No Great Expectations / Soda / dbt tests. The `data_freshness` view in `data-platform/dashboards/clickhouse/analytics_views.sql` exists but is not wired to alerts.
- No metadata catalog and no lineage tracking. The Postgres → Kafka → Spark → ClickHouse dependency graph lives only in commit history and developer heads.
- No explicit retention. ClickHouse tables have no TTL clauses, Kafka topics use broker defaults, Postgres has no archival pattern, and Spark checkpoints accumulate under `{CHECKPOINT_LOCATION}/{table_name}` indefinitely.

This document is the design for a new `data-governance` OpenSpec capability that closes those gaps. It does **not** create PROPOSAL.md, TASKS.md, or delta files yet — those follow once the design direction is approved.

## Goals / Non-Goals

**Goals:**
- Make every CDC event flow through a contract-checked, schema-registered, lineage-tracked path before it lands in ClickHouse.
- Stop PII from leaking past the Postgres boundary in clear text.
- Give the platform an enforceable lifecycle policy: every table and topic has a documented retention.
- Keep all governance guarantees expressible as OpenSpec requirements so `make spec-validate` can verify them structurally.

**Non-Goals:**
- Encryption at rest (Postgres/Kafka/ClickHouse volume encryption is an infra concern, out of scope).
- GDPR right-to-erasure automation. PII hashing helps but does not implement deletion workflows.
- A data marketplace UX, semantic layer, or self-serve dataset publishing.
- Cross-region replication, multi-tenant policy isolation, or production SLA targets — the demo stack is single-node.
- Replacing existing observability (Grafana infra dashboards stay; governance adds *data* observability alongside).

## Four Pillars

Governance is structured into four pillars, each independently shippable. The recommended build order is the reverse of the natural-reading order: retention first (cheapest, highest risk reduction), catalog last (heaviest infra).

### Pillar 1 — Data Quality & Contracts

**Tool choice:** Confluent **Schema Registry** + **Great Expectations** running inside Spark `foreachBatch`.

**Behavior the spec will encode:**
- The Debezium connector publishes Avro and registers schemas to a Schema Registry running at `schema-registry:8081` (in-cluster) / `localhost:8081` (host).
- Each Spark CDC job runs a Great Expectations suite against the micro-batch DataFrame *before* the ClickHouse write. Failing rows are routed to a `*_dlq` Kafka topic with the original payload + the failing expectation name.
- Each target ClickHouse table has a freshness SLO: `minutes_since_last_update < 10` during pipeline-active hours. Breach fires a Grafana alert.

**Where it plugs in (reuse, don't rebuild):**
- `data-platform/streaming/spark/src/io/clickhouse_client.py` — `create_batch_writer_function` is the natural injection point. Wrap the writer; reject-or-quarantine on validation failure.
- `data-platform/dashboards/clickhouse/analytics_views.sql` — the `data_freshness` view already computes the metric. Wire Grafana alerting on top, no SQL changes needed.
- `data-platform/streaming/spark/scripts/submit_job.sh` — already loads packages; add the `org.apache.spark:spark-avro` and Schema Registry client jars here.

**New files (declared, not built in this turn):**
- `data-platform/governance/expectations/{customers,products,orders}_suite.json`
- `data-platform/streaming/spark/src/governance/gx_runner.py`
- `infrastructure/docker/docker-compose.kafka.yml` gains a `schema-registry` service.

### Pillar 2 — Metadata & Lineage Catalog

**Tool choice:** **OpenMetadata** with OpenLineage Spark listener for runtime lineage.

**Why OpenMetadata over DataHub:**
- Lighter Docker footprint (OM: OpenMetadata server + MySQL + Elasticsearch ≈ 3 containers; DataHub: GMS + frontend + Kafka + MySQL + Elasticsearch + Neo4j ≈ 6 containers).
- Native ingestion connectors for Postgres, Kafka (with Schema Registry), and ClickHouse.
- Built-in data quality module that overlaps with Pillar 1 — leaves the door open to consolidate GX inside OM later.

**Behavior the spec will encode:**
- OpenMetadata ingests metadata from Postgres, Kafka, and ClickHouse on a daily scheduled run.
- Each Spark CDC job emits lineage events to OpenMetadata via the OpenLineage Spark listener, recording the source Kafka topic → target ClickHouse table edge per micro-batch.
- Every column in the three CDC tables (`customers`, `products`, `orders`) carries a description and an owner tag in OpenMetadata.

**Where it plugs in:**
- `data-platform/streaming/spark/scripts/submit_job.sh` — add `--conf spark.extraListeners=io.openlineage.spark.agent.OpenLineageSparkListener` and the OpenLineage HTTP transport config pointing at OpenMetadata.
- Makefile — new `up-governance` / `down-governance` / `logs-governance` targets composing the new file.

**New files:**
- `infrastructure/docker/docker-compose.governance.yml` (OpenMetadata + MySQL + Elasticsearch).
- `data-platform/governance/openmetadata/ingestion-{postgres,kafka,clickhouse}.yaml`.

### Pillar 3 — PII / Access Control / Audit

**Tool choice:** Application-layer masking in Spark transformers + ClickHouse row policies + Kafka-based audit log. No external secret store (a `PII_SALT` env var is enough for this demo; production would use Vault/KMS).

**Behavior the spec will encode:**
- `customers.email` is SHA-256 hashed with salt `PII_SALT` before being written to ClickHouse. The raw email remains in Postgres only.
- `customers.name` is tokenized (first-initial + last-name-hash) in ClickHouse.
- ClickHouse defines a role `analyst_readonly` with a row policy that excludes `_deleted=1` rows on `customers`, `products`, and `orders`. Grafana connects using this role, not `default`.
- Every CDC consumer (Spark jobs, Streamlit Kafka monitor) emits a structured access-log event to the `governance.access_log` Kafka topic on startup, identifying the consumer principal and the topics it subscribed to.

**Where it plugs in:**
- `data-platform/streaming/spark/src/utils/udfs.py` — add `hash_pii_udf` alongside the existing `decode_decimal_udf`. Same pattern.
- `data-platform/streaming/spark/src/transformations/customer_transformer.py` — apply the UDF here. The other transformers don't currently expose PII columns; if they grow PII fields later, the same hook applies.
- `infrastructure/docker/clickhouse/create_tables.sql` — add `CREATE ROLE analyst_readonly` + row policies in the same migration as the TTL changes from Pillar 4.

**Tradeoff:** Hashing breaks joinability for analysts who want to correlate by email across systems. Mitigation: hash is *deterministic with a fixed salt*, so the same email always produces the same hash — joins work as long as both sides hash with the same salt. Salt rotation breaks historical joins (acknowledged risk; see below).

### Pillar 4 — Retention & Lifecycle

**Tool choice:** Native features only — no new service.

**Behavior the spec will encode:**
- ClickHouse CDC tables carry TTLs: tombstones (`_deleted = 1`) expire 90 days after `event_time`; active rows expire 2 years after `event_time`.
- Kafka topics have explicit retention declared in topic-config: `pg.public.*` = 7 days, `governance.access_log` = 30 days, `*_dlq` = 14 days.
- Spark checkpoint directories follow a versioned-path convention: `{CHECKPOINT_LOCATION}/{table_name}/v{schema_version}`. A new Make target `make cdc-rotate-checkpoint TABLE=customers` moves the current checkpoint to `_archived/{date}/` and creates a fresh empty path.
- Postgres `orders` older than 1 year are moved to `orders_archive` by a monthly cron documented in `data-platform/governance/retention/postgres-archive.sql`. The archive table is *not* captured by Debezium.

**Where it plugs in:**
- `infrastructure/docker/clickhouse/create_tables.sql` — single-file diff for TTL clauses.
- The Spark checkpoint convention upgrades `BaseCDCJob` to read `schema_version` from the job class and append it to the checkpoint path.

## Decisions

**One new capability, not requirements scattered across existing ones**
Governance is a distinct concern: contract enforcement, classification, and lifecycle of data flowing through the pipeline. Scattering it across `cdc-pipeline` (quality gates), `analytics` (TTL/masking), and `infrastructure` (services) makes it impossible to audit "what governance does this system guarantee" in one place. The `data-governance` capability owns the requirements; the other three capabilities carry MODIFIED deltas where governance changes their observable behavior.

**Schema Registry as the contract boundary**
Schemas embedded in Spark `StructType`s are reviewed during code review at best, and silently drift at worst. A Schema Registry makes the contract a service-level artifact, gives Debezium a place to validate schema evolution, and is a prerequisite for Avro (which reduces topic size meaningfully on the `customers`/`products`/`orders` shapes).

**Great Expectations inside `foreachBatch`, not as a sidecar**
The alternative — Soda Core or a separate validator service consuming the same Kafka topic — doubles network traffic and creates a "data already in ClickHouse before we knew it was bad" failure mode. Running GX inside `foreachBatch` means validation happens *before* the write commits, and quarantine becomes a write-to-DLQ instead of a delete-from-ClickHouse.

**OpenMetadata over DataHub**
Lighter footprint, native ClickHouse connector (DataHub's is community-maintained), and a built-in DQ module that lets us collapse Pillar 1's GX integration into the catalog later if we want a single pane of glass. Tradeoff: smaller community, fewer Stack Overflow answers when things break.

**Hashing PII, not tokenizing-with-a-vault**
Vault/KMS is the correct production answer. For a demo stack, deterministic SHA-256 with a salt from `PII_SALT` gives the right *shape* of solution — irreversible, joinable, rotatable — without standing up a secret manager. The PROPOSAL.md should explicitly call this out as a demo-grade choice.

**TTL on `event_time`, not `inserted_at`**
ClickHouse rows have both. `event_time` is the Debezium `ts_ms` — i.e., when the change happened in Postgres. Using it for TTL means a row that arrives 6 months late still expires on the same calendar date it would have if it arrived on time. This is the right semantic for compliance retention; `inserted_at` would let backfills extend retention windows accidentally.

## Risks / Trade-offs

**Avro migration breaks existing Spark checkpoints**
Switching Debezium's converter from JSON to Avro changes the Kafka message format. Existing Spark checkpoints encode the JSON-parsing pipeline. Restarting Spark jobs against the new Avro topics will fail at the schema layer. Mitigation: deploy Avro behind a feature flag, drain the existing JSON topics, delete the old checkpoints, switch over. The versioned checkpoint convention from Pillar 4 makes this routine.

**OpenMetadata infra weight on the Azure VM**
Three new containers + ~3GB RAM is fine on a dev laptop. The Azure VM target in `infrastructure/terraform/` is sized for the current stack. Mitigation: keep `up-governance` *optional* — `make up` excludes it; `make up-with-governance` opts in. Re-evaluate VM sizing as part of Pillar 2 rollout.

**PII salt rotation breaks historical joins**
A deterministic hash means `hash(email, salt_v1) ≠ hash(email, salt_v2)`. Rotating the salt — necessary if it leaks — orphans all historical hashed values. Mitigation: document that salt rotation is a backfill event, and provide a procedure to re-hash the ClickHouse `customers` table from the Postgres source of truth.

**OpenLineage Spark listener overhead on small micro-batches**
The listener emits an HTTP event per task on job start/end. The CDC jobs use `TRIGGER_INTERVAL` defaulting to small intervals, so the per-second event rate could pressure the OpenMetadata HTTP endpoint. Mitigation: configure the OpenLineage transport with batching, or fall back to file-based emission with a periodic uploader.

**ClickHouse TTL interaction with `ReplacingMergeTree FINAL` queries**
TTL removes rows during merges. If a tombstone (`_deleted=1`) expires before the next `FINAL` query, the deduplicated state is correct *and* compact. But if a tombstone expires *before* its corresponding active row (e.g., late-arriving updates), `FINAL` could resurrect the deleted row. The 90-day tombstone TTL is intentionally generous to keep this rare. Mitigation: monitor; consider `OPTIMIZE TABLE ... FINAL` on a schedule to force merges before TTL evaluation.

**Spec drift between governance and existing capabilities**
Pillar 1 changes Debezium's converter; Pillar 4 changes ClickHouse schemas. Both touch behavior covered by `cdc-pipeline` and `analytics` specs. If the MODIFIED deltas in those capabilities lag behind the implementation, `make spec-validate` still passes but the specs lie. Mitigation: every PROPOSAL.md for governance work must enumerate the cross-capability deltas explicitly in its `## What Changes` section, not just the `data-governance` additions.

**Governance requirements that constrain operators, not the system**
"You must rotate the PII salt every 90 days" is a procedural rule, not an observable system behavior. Per `openspec/AGENTS.md`, those belong in a runbook or this DESIGN.md's Risks section — not as `### Requirement:` blocks. The spec should encode *only* what's structurally enforceable (e.g., "ClickHouse SHALL define role `analyst_readonly`" — verifiable by inspecting ClickHouse).

## Phased Rollout

Each phase is independently shippable; ship in order, but stop at any phase if the value is sufficient.

**Phase 1 — Retention & Lifecycle (Pillar 4)**
- Pure config; no new services.
- Exit criteria: ClickHouse TTL clauses live, Kafka topic retention declared, checkpoint convention documented and adopted by all three jobs, Postgres archive script written (not necessarily cron-scheduled).
- Highest risk reduction per line of code: bounds storage growth across all four data stores.

**Phase 2 — PII / Access (Pillar 3)**
- One Spark UDF, one ClickHouse migration, one new Kafka topic.
- Exit criteria: `email` and `name` arrive masked in ClickHouse; `analyst_readonly` role exists and Grafana uses it; `governance.access_log` topic exists with at least one consumer principal emitting on startup.
- Touches one transformer plus one ClickHouse migration. No new container.

**Phase 3 — Schema Registry + Data Quality (Pillar 1)**
- Adds Schema Registry container; changes Debezium converter; introduces GX inside Spark jobs.
- Exit criteria: schemas registered for all three topics, GX suites pass on demo data, DLQ topics exist and receive a row when an expectation is forced to fail, freshness alert fires under a forced-stop test.
- Largest dev-time impact. Coordinate with checkpoint rotation from Phase 1.

**Phase 4 — Metadata & Lineage (Pillar 2)**
- Heaviest infra add (OpenMetadata + MySQL + Elasticsearch).
- Exit criteria: ingestion runs successfully for Postgres, Kafka, and ClickHouse; lineage events from at least one Spark job visible in the OpenMetadata UI; all CDC table columns have descriptions.
- Deferred to last so it has interesting metadata (schemas, DQ results, masking annotations) from prior phases to display.

## Requirements That Will Be Declared

These will become `### Requirement:` blocks in `openspec/specs/data-governance/spec.md` once the change is archived. Listed here for review; **not** authoritative until they exist as scenarios with WHEN/THEN.

| Pillar | Requirement (kebab-name) | One-line summary |
|--------|--------------------------|------------------|
| 1 | `schema-registry-publication` | Debezium publishes Avro and registers schemas with Schema Registry |
| 1 | `gx-batch-validation` | Each Spark micro-batch runs the per-table GX suite before writing |
| 1 | `dlq-on-validation-failure` | Failing rows route to `{table}_dlq` with the failing expectation name |
| 1 | `freshness-slo-and-alert` | Each ClickHouse target has `< 10 min` freshness; breach alerts in Grafana |
| 2 | `openmetadata-ingestion` | OpenMetadata ingests Postgres + Kafka + ClickHouse metadata daily |
| 2 | `openlineage-spark-emission` | Spark jobs emit OpenLineage events for source→target lineage |
| 2 | `column-documentation-coverage` | Every column on the three CDC tables has a description + owner |
| 3 | `pii-hashing-customers-email` | `customers.email` is SHA-256(email, PII_SALT) in ClickHouse |
| 3 | `pii-tokenization-customers-name` | `customers.name` is tokenized in ClickHouse |
| 3 | `clickhouse-rbac-roles` | Role `analyst_readonly` exists with row policies; Grafana uses it |
| 3 | `cdc-consumer-access-log` | Consumers emit a startup event to `governance.access_log` |
| 4 | `clickhouse-ttl-policies` | TTL: tombstones 90d, active rows 2y, anchored on `event_time` |
| 4 | `kafka-topic-retention` | Explicit retention per topic family |
| 4 | `postgres-archival-policy` | `orders` older than 1 year move to `orders_archive` |
| 4 | `checkpoint-versioned-paths` | Spark checkpoints live under `{table}/v{schema_version}` |

## Cross-Capability Deltas

Governance changes observable behavior already covered by other specs. The future PROPOSAL.md must declare these MODIFIED requirements:

- **`cdc-pipeline`**: Debezium converter changes from JSON to Avro; Spark jobs gain GX validation + OpenLineage emission steps; checkpoint path convention changes.
- **`analytics`**: ClickHouse tables gain TTL clauses; new `analyst_readonly` role and row policies; Grafana connects via the new role.
- **`infrastructure`**: New `up-governance` / `down-governance` Make targets; new `docker-compose.governance.yml`; Schema Registry added to `docker-compose.kafka.yml`.

The `streamlit-ui` capability is touched only if the Kafka monitor view is updated to emit access-log events; that delta is optional and can ship later.

## Out of Scope

- Encryption at rest (volume-level or database-level encryption).
- GDPR/CCPA right-to-erasure tooling.
- A data marketplace, semantic layer, or self-serve publishing UX.
- Multi-region/multi-tenant policy isolation.
- Production-grade secret management (Vault, KMS, cloud secret managers).
- Automated PII discovery (e.g., scanning new columns and tagging them); column-level PII tagging is manual for now.
