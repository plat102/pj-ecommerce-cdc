## Why

The schema registry currently runs on `apicurio/apicurio-registry-mem:2.5.11.Final`, an in-memory image variant. Every container restart — including `docker restart schema-registry`, host reboots, and `make down` — wipes every registered Avro artifact. Debezium re-registers schemas from Postgres DDL on the next CDC event, but any Kafka messages already on the topic that carry old content IDs become undecodable until a matching ID happens to be re-issued. This is a real operational hazard for a pipeline whose whole wire format depends on the registry.

The `-mem` choice was accepted in `add-data-governance` Phase 3 as expedient; the introducing commit (`4199d02`) documented Apicurio as the load-bearing choice (Debezium bundles Apicurio's Avro converter; Confluent's is not on the plugin path), but did not lock in a storage variant. Switching from `-mem` to the `-kafkasql` variant persists all schemas to a compacted Kafka topic (`kafkasql-journal`) without changing the Apicurio API, the wire format, or any converter.

## What Changes

- **Replace** the `schema-registry` image in `infrastructure/docker/docker-compose.kafka.yml` from `apicurio/apicurio-registry-mem:2.5.11.Final` to `apicurio/apicurio-registry-kafkasql:2.5.11.Final`.
- **Add** one environment variable to the same service: `KAFKA_BOOTSTRAP_SERVERS: kafka1:9092` (points registry storage at the existing broker).
- **Extend** the healthcheck `start_period` from 15s to 30s to accommodate the one-time journal replay on cold boot.
- **Add a new requirement** in the `data-governance` capability documenting that the registry survives container restart. (No existing requirement is being weakened; this closes a durability gap.)
- **NOT changing**: `data-platform/cdc/connectors/register-pg.json`, Spark `app_config.py`, OpenMetadata `kafka.yaml`, `docs/governance.md`, or any spec other than `data-governance`. Same API endpoint (`http://schema-registry:8080/apis/registry/v2`), same ccompat endpoint, same `Legacy4ByteIdHandler` wire format.

Behavior on `make down` is unchanged and intentional: because `make down` removes the Kafka volume, the `kafkasql-journal` topic goes with it — schemas do not survive `make down`. Persistence applies to container restart / `make stop && make start` / host reboot, which is where the current pain lives.

## Capabilities

### New Capabilities
<!-- None. This change reuses an existing capability. -->

### Modified Capabilities
- `data-governance`: adds `schema-registry-persistence` requirement covering registry-storage durability across container restart; leaves the existing `schema-registry-publication` requirement intact.

## Impact

- **Files touched**: `infrastructure/docker/docker-compose.kafka.yml` (one service block: image + env + healthcheck). Optionally `.env.example` if a stale comment names the `-mem` variant.
- **Kafka**: a new compacted topic `kafkasql-journal` gets auto-created on first boot with `cleanup.policy=compact`. No manual topic setup required.
- **Downstream systems**: none affected. Debezium's Apicurio converter, Spark's `fetch_avro_schema()` against `/apis/ccompat/v7`, and OpenMetadata's Kafka ingestion all continue to work unchanged.
- **Rollback**: revert the compose block. The `kafkasql-journal` topic can remain in Kafka; it is inert when the `-mem` image is restored.
- **Risk**: low. Same Apicurio codebase, same major version (2.5.11.Final), documented storage-variant image published by Apicurio itself. First-boot cold-start is ~20–30s slower (journal replay); ongoing restarts are similarly bounded.
