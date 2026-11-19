## Context

The CDC pipeline (`Postgres → Debezium → Kafka → Spark → ClickHouse`) uses Apicurio Registry to store the Avro schemas that Debezium auto-registers from Postgres DDL. The wire format on every CDC topic is `[0x00][contentId:int32][avro-body]` — the `contentId` is a pointer into the registry. If the registry doesn't have the schema for a given contentId, downstream deserialization (Spark, OpenMetadata) fails on that message.

The registry currently runs on `apicurio/apicurio-registry-mem:2.5.11.Final` (see `infrastructure/docker/docker-compose.kafka.yml:73`). The `-mem` variant is an in-JVM H2 database with no persistence layer — every restart wipes every artifact.

Apicurio 2.5.x publishes three storage variants of the same registry:
- `-mem`: in-memory, ephemeral (current).
- `-sql`: persists to an external RDBMS (Postgres, MSSQL).
- `-kafkasql`: persists by producing to a compacted Kafka topic (`kafkasql-journal`) and replaying it on boot.

The introducing commit for the current setup (`4199d02`, 2026-07-12) chose Apicurio itself over Confluent SR because the Debezium image bundles Apicurio's Avro converter (`ENABLE_APICURIO_CONVERTERS=true`) but not Confluent's — that constraint still holds and rules out any non-Apicurio registry from consideration without a custom Debezium image.

## Goals / Non-Goals

**Goals:**
- Registered Avro artifacts survive container restart / `make stop && make start` / host reboot.
- No changes to Debezium, Spark, or OpenMetadata configuration.
- No new infrastructure dependency (no extra database, no extra volumes to manage).
- Same wire format on Kafka topics — the switch is invisible to already-encoded messages **as long as the registry has finished replaying its journal** at consumption time.
- Same major/minor version of Apicurio (2.5.11.Final) — no API surface change.

**Non-Goals:**
- Persisting schemas across `make down`. `make down` intentionally removes the Kafka volume, and the kafkasql topic goes with it. This is consistent with the existing `destructive-teardown` requirement in the `infrastructure` capability (`openspec/specs/infrastructure/spec.md:50`) and is not the pain point we're fixing.
- Migrating away from Apicurio. Constrained by the Debezium plugin bundle noted above.
- Registry high-availability, clustering, or multi-broker fault tolerance. Single-broker demo deployment.
- Kafka authentication for the registry storage topic (SASL/SSL). Local demo runs on plain PLAINTEXT.

## Decisions

### Decision 1: Use `apicurio-registry-kafkasql`, not `apicurio-registry-sql`

**Chosen:** `apicurio/apicurio-registry-kafkasql:2.5.11.Final`.

**Alternative considered — `apicurio-registry-sql`** (Postgres-backed):
- **Pros:** Familiar `pg_dump` backup story; fastest cold start; no journal replay.
- **Cons:** Adds a Postgres dependency (either a new dedicated container or a schema inside the existing `postgres` service that already hosts the source-of-truth CDC data — either option couples two independent concerns), introduces a docker volume to manage, and increases the operational surface (`postgres` becomes a stronger blast-radius target).

**Alternative considered — keep `-mem`, export schemas to disk on shutdown:**
- **Pros:** Zero image change.
- **Cons:** Requires custom shutdown hooks and a re-registration bootstrap script; loses schema *versions* (only latest survives export); no coverage for crash restarts (only graceful shutdowns).

**Rationale for `-kafkasql`:** the compacted Kafka topic co-lives with the CDC data itself — one durability domain to reason about, no new service to run, no volume to back up separately. The tradeoff is one-time journal replay (~20–30s) on cold start; measured against the current restart-wipes-everything behavior, that's a favorable trade.

### Decision 2: Default `kafkasql-journal` topic; do not pre-create it

The Apicurio kafkasql code auto-creates its journal topic on first boot with `cleanup.policy=compact` (source: Apicurio 2.5.11 kafkasql module; behavior confirmed via `overlay.properties` defaults). We do **not** need to pre-declare the topic in any Kafka init script or Makefile target. If we ever need to override name/partitions, we can set `REGISTRY_KAFKASQL_TOPIC` — but for a single-partition local demo, the default is correct.

### Decision 3: Only add `KAFKA_BOOTSTRAP_SERVERS` env var; keep everything else

`overlay.properties` in the Apicurio 2.5.11.Final source (`storage/kafkasql/src/main/resources/overlay.properties`) shows the kafkasql profile expands `${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}`. The container's default of `localhost:9092` won't resolve inside our Docker network, so we set it to `kafka1:9092`. Every other kafkasql property (`registry.kafkasql.topic`, consumer group id, producer client id) has a sensible default.

**Rejected — set `REGISTRY_KAFKASQL_BOOTSTRAP_SERVERS` directly:** cleaner-looking but not what the image actually reads; the `${KAFKA_BOOTSTRAP_SERVERS:...}` interpolation in `overlay.properties` is the documented public contract.

### Decision 4: Bump healthcheck `start_period` from 15s to 30s

The `-mem` variant is essentially instant-ready. The kafkasql variant must connect to Kafka, subscribe to `kafkasql-journal`, and replay it before serving requests. On a cold-boot local setup this is bounded by broker availability + topic size (empty first time, then grows with schema versions). 30s is a safe default that avoids spurious restart loops without slowing down the healthy path (subsequent healthchecks fire on the 15s interval as today).

### Decision 5: Leave `schema-registry-publication` unchanged; add a new sibling requirement

The existing `data-governance/schema-registry-publication` requirement is about *what* Debezium publishes to the registry — that behavior is unchanged. Persistence is orthogonal ("the storage layer of the registry is durable across container restart"). We add `schema-registry-persistence` as a new requirement in the same capability rather than amending the existing one, which keeps the two concerns independently reviewable.

## Risks / Trade-offs

**[Risk] Journal replay is slow enough on a real dataset to trip the healthcheck.**
→ Mitigation: `start_period: 30s` covers a demo-scale journal (< 100 schema versions). If we ever accumulate thousands of versions (unlikely — Debezium only publishes on DDL change), bump `start_period` further. The number of retries (10) times the interval (15s) also gives us a 150s post-`start_period` grace window.

**[Risk] Kafka broker unavailable during registry boot.**
→ Mitigation: `depends_on: kafka1: { condition: service_healthy }` already gates registry startup on a healthy broker. Verified in the current compose block; unchanged by this proposal.

**[Risk] Wire-format mismatch during migration — messages produced with the `-mem` registry carry contentIds that don't exist in the fresh kafkasql journal.**
→ Mitigation: on first `make up` after cutover, the fresh kafkasql registry starts empty; Debezium re-registers all six artifacts on the next CDC event; new content IDs may differ from the old ones. Pre-cutover messages still on Kafka topics will be undecodable until an equivalent schema is re-registered. For a local demo, we accept this — the mitigation is to `make down` before the cutover (destroys existing Kafka messages along with the registry) so there's nothing to mismatch against. Documented in `tasks.md`.

**[Risk] Rollback is easy but partial.**
→ Reverting the compose block restores `-mem`. The `kafkasql-journal` topic remains on Kafka; it's inert but visible. Acceptable — we can delete it manually if it bothers us (`docker exec kafka1 kafka-topics --delete ...`).

**[Trade-off] Cold-start latency.**
→ ~20–30s slower first-time boot. Once running, no ongoing performance impact.

**[Trade-off] We're still on `-mem`'s vulnerability window during `make down`.**
→ True and by design. `make down` is documented-destructive; if we ever want cross-teardown persistence, we'd need a different fix (e.g., named volume for a `-sql` variant with its own Postgres). Out of scope here.

## Migration Plan

1. **Pre-cutover (optional archive):** while the current `-mem` stack is up, `curl` the registry's ccompat subjects endpoint into `data-platform/cdc/schemas/backup/` so we have a reference of what was registered. Not committed to VCS.
2. **Clean cutover:** `make down` (destroys existing Kafka topics and stale content-ID space), edit the compose file per `tasks.md`, then `make up`. Debezium re-registers artifacts on first CDC event.
3. **Verification:** confirm subjects list is correct after `make up`, then `docker restart schema-registry` and re-check — subjects must survive. This is the acceptance test for the whole change.
4. **Rollback:** `git revert` the compose diff, `make down && make up`. Optionally `docker exec kafka1 kafka-topics ... --delete --topic kafkasql-journal` if we don't want the orphan topic.

## Open Questions

- **Should we pin `apicurio-registry-kafkasql` to a specific SHA rather than the `2.5.11.Final` tag?** Consistent with how we already pin `-mem`, so no. Tag-pinning is the project convention.
- **Should the Makefile grow a `make persist-check` target that runs the persistence acceptance test?** Nice-to-have; deferred. The tasks.md verification steps are enough for a manual check.
