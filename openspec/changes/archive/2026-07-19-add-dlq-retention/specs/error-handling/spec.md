## ADDED Requirements

### Requirement: dlq-topic-retention
Every DLQ topic in the stack SHALL be created with an explicit `retention.ms` and `retention.bytes` config rather than inheriting broker defaults. The default values SHALL be `retention.ms=604800000` (7 days, aligned with Loki retention) and `retention.bytes=104857600` (100 MB per topic), and `cleanup.policy=delete`. The set of DLQ topics governed by this requirement SHALL be: `debezium_connect_dlq`, `{customers,products,orders}_cdc_dlq`, and `{customers,products,orders}_cdc_sink_dlq`. Operators SHALL be able to override the two size/time bounds via the environment variables `DLQ_RETENTION_MS` and `DLQ_RETENTION_BYTES` on any invocation of the setup script; overrides are transient and drift-correct back to the defaults on the next `make up`.

#### Scenario: DLQ topics carry explicit retention config
- **WHEN** `kafka-configs --bootstrap-server localhost:9092 --entity-type topics --entity-name <dlq_topic> --describe` is executed for each DLQ topic listed above
- **THEN** the output SHALL include `retention.ms=604800000`, `retention.bytes=104857600`, and `cleanup.policy=delete` (or the currently-effective operator overrides for the first two)

#### Scenario: retention is applied on fresh stack
- **WHEN** the stack is brought up cold via `make up` and no DLQ traffic has yet occurred
- **THEN** every DLQ topic SHALL already exist on the broker with the retention config above, before any bad record needs to route there

#### Scenario: retention drift-corrects on re-run
- **WHEN** an operator manually alters a DLQ topic (e.g. `kafka-configs --alter --add-config retention.ms=99999`) and then re-runs `make up` or `make apply-dlq-topics`
- **THEN** the topic's retention config SHALL be restored to the defaults (or to the current `DLQ_RETENTION_MS` / `DLQ_RETENTION_BYTES` values if set)

#### Scenario: operator raises retention temporarily
- **WHEN** an operator runs `DLQ_RETENTION_MS=2592000000 make apply-dlq-topics` (30 days)
- **THEN** every DLQ topic SHALL be reconfigured with `retention.ms=2592000000`
- **AND** the next `make up` without the override set SHALL restore `retention.ms=604800000`

### Requirement: dlq-topic-partitions-and-replication
Every DLQ topic SHALL be created with `partitions=1` and `replication.factor=1`, matching the single-broker dev cluster and the Debezium `errors.deadletterqueue.topic.replication.factor` value declared in `kafka-connect-dlq-config`.

#### Scenario: DLQ topic layout is uniform
- **WHEN** `kafka-topics --describe --topic <dlq_topic>` runs against any DLQ topic in the stack
- **THEN** the output SHALL show `PartitionCount: 1` and `ReplicationFactor: 1`
