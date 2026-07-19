## ADDED Requirements

### Requirement: dlq-diagnostic-cli
The stack SHALL provide a Python CLI at `scripts/dlq_replay.py` with three read-only subcommands: `list`, `inspect`, and `audit-log`. The CLI SHALL NOT instantiate a Kafka producer under any code path in this change; it is strictly a diagnostic reader. `list --topic <name>` SHALL enumerate messages in the topic showing offset, key preview, `_error_stage`, and truncated `_error_message`. `inspect --topic <name> --offset N` SHALL print the full JSON envelope of the target message. `audit-log` SHALL read all messages currently on `dlq_replay_log` and print them, with `--format json` and `--format table` output modes. The CLI top-level help SHALL declare it as read-only and explicitly note that replay is deferred to a follow-up change.

#### Scenario: list surfaces error metadata
- **WHEN** `python scripts/dlq_replay.py list --topic products_cdc_sink_dlq` runs against a topic with 3 messages
- **THEN** stdout SHALL contain one row per message with offset, key preview, error stage, and a truncated error message

#### Scenario: inspect prints one payload
- **WHEN** `python scripts/dlq_replay.py inspect --topic products_cdc_sink_dlq --offset 0` runs
- **THEN** stdout SHALL contain a pretty-printed JSON object matching the full message value at that offset

#### Scenario: audit-log reads empty topic gracefully
- **WHEN** `python scripts/dlq_replay.py audit-log --format json` runs against a fresh `dlq_replay_log` topic with no messages
- **THEN** the CLI SHALL exit 0 and print an empty JSON array (or equivalent empty-state indicator)

#### Scenario: no replay subcommand exists
- **WHEN** `python scripts/dlq_replay.py --help` is invoked
- **THEN** the subcommand list SHALL contain exactly `list`, `inspect`, `audit-log`
- **AND** SHALL NOT contain `replay`

### Requirement: dlq-replay-pure-helpers
The module `scripts/dlq_replay.py` SHALL export pure functions that will underpin the future replay path: `build_replay_key(topic, partition, offset)` returning `sha256("topic|partition|offset").hexdigest()[:32]`; `strip_dlq_envelope(payload)` returning the payload without `_error_*` fields; `pick_dest_topic(source_topic)` mapping DLQ topic → upstream topic and raising `RefusedError` for `debezium_connect_dlq`; `refuse_if_re_replay(payload)` raising `RefusedError` when the payload already carries `_replay_source_topic`. These functions SHALL have unit-test coverage in `tests/scripts/test_dlq_replay.py`. No CLI subcommand in this change invokes them at runtime.

#### Scenario: build_replay_key is deterministic
- **WHEN** `build_replay_key("products_cdc_sink_dlq", 0, 42)` is called twice
- **THEN** both calls SHALL return the identical 32-character hex string

#### Scenario: pick_dest_topic maps sink DLQ correctly
- **WHEN** `pick_dest_topic("products_cdc_sink_dlq")` is called
- **THEN** it SHALL return `"pg.public.products"`

#### Scenario: pick_dest_topic refuses Kafka Connect DLQ
- **WHEN** `pick_dest_topic("debezium_connect_dlq")` is called
- **THEN** it SHALL raise `RefusedError` with a message about raw pre-Debezium bytes

#### Scenario: refuse_if_re_replay flags a prior replay
- **WHEN** `refuse_if_re_replay({"_replay_source_topic": "x", "_replay_source_offset": 5, ...})` is called
- **THEN** it SHALL raise `RefusedError` referencing `x@5`

## MODIFIED Requirements

### Requirement: dlq-topic-retention
Every DLQ topic in the stack SHALL be created with an explicit `retention.ms` and `retention.bytes` config rather than inheriting broker defaults. The default values SHALL be `retention.ms=604800000` (7 days, aligned with Loki retention) and `retention.bytes=104857600` (100 MB per topic), and `cleanup.policy=delete`. The set of topics governed by this requirement SHALL be: `debezium_connect_dlq`, `{customers,products,orders}_cdc_dlq`, `{customers,products,orders}_cdc_sink_dlq`, AND the audit-log companion topic `dlq_replay_log`. Operators SHALL be able to override the two size/time bounds via the environment variables `DLQ_RETENTION_MS` and `DLQ_RETENTION_BYTES` on any invocation of the setup script; overrides are transient and drift-correct back to the defaults on the next `make up`.

#### Scenario: DLQ topics carry explicit retention config
- **WHEN** `kafka-configs --bootstrap-server localhost:9092 --entity-type topics --entity-name <topic> --describe` is executed for each managed topic
- **THEN** the output SHALL include `retention.ms=604800000`, `retention.bytes=104857600`, and `cleanup.policy=delete` (or the currently-effective operator overrides for the first two)

#### Scenario: retention is applied on fresh stack
- **WHEN** the stack is brought up cold via `make up` and no DLQ traffic has yet occurred
- **THEN** every managed topic SHALL already exist on the broker with the retention config above, including the empty `dlq_replay_log` topic

#### Scenario: audit-log topic is included in the managed set
- **WHEN** `kafka-topics --list --bootstrap-server localhost:9092 | grep _dlq` runs after `make up`
- **THEN** `dlq_replay_log` SHALL be present with the same retention semantics as the DLQ topics (even though its name lacks the `_dlq` suffix, its purpose ties it to the DLQ operational surface)
