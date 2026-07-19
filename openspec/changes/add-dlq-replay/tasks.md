## 0. Design (this turn)

- [x] 0.1 Write proposal.md — scope-limited to read-only diagnostic CLI + `dlq_replay_log` topic
- [x] 0.2 Write design.md — 5 decisions covering the read/write split, pure helpers, argparse layout
- [x] 0.3 Write tasks.md (this file)
- [x] 0.4 Write specs delta: `error-handling` ADDED `dlq-diagnostic-cli` + `dlq-replay-pure-helpers`; MODIFIED `dlq-topic-retention` to include `dlq_replay_log` in the managed topic set
- [ ] 0.5 User approves design direction before implementation begins

## 1. Phase 1 — Diagnostic CLI + topic

- [ ] 1.1 Add `dlq_replay_log` to `DLQ_TOPICS` array in `scripts/setup_dlq_topics.sh` so it inherits the shared retention config.
- [ ] 1.2 Create `scripts/dlq_replay.py` with argparse subparser layout `list | inspect | audit-log`. Top-level help SHALL state "read-only diagnostic tool; replay pending in add-dlq-avro-replay".
- [ ] 1.3 Implement pure helpers in the same file: `build_replay_key`, `strip_dlq_envelope`, `pick_dest_topic`, `refuse_if_re_replay`, plus the `RefusedError` type. No CLI subcommand calls them in this change.
- [ ] 1.4 Implement `list --topic <name>` — reads from earliest with a bounded consumer timeout, formats one row per message with offset, key preview, error stage, truncated error message.
- [ ] 1.5 Implement `inspect --topic <name> --offset N` — reads until it finds the requested offset, prints the value as pretty JSON.
- [ ] 1.6 Implement `audit-log [--format json|table]` — reads `dlq_replay_log` from earliest, prints either JSON array or a per-column table.
- [ ] 1.7 Add `dlq-list` and `dlq-inspect` Makefile targets — thin wrappers accepting `TOPIC=` / `OFFSET=` variables.
- [ ] 1.8 `chmod +x scripts/dlq_replay.py`.
- [ ] 1.9 Extend the "DLQ operations" section in `docs/observability.md` with a single paragraph pointing operators at `scripts/dlq_replay.py list --topic <name>` for incident review.

## 2. Phase 2 — Tests

- [ ] 2.1 `tests/scripts/test_dlq_replay.py` — pure helper tests (no Kafka needed):
  - `test_build_replay_key_deterministic` — same inputs → same key.
  - `test_build_replay_key_distinct_by_offset` — different offset → different key.
  - `test_pick_dest_topic_sink_dlq` — `products_cdc_sink_dlq` → `pg.public.products`.
  - `test_pick_dest_topic_gx_dlq` — `products_cdc_dlq` → `pg.public.products`.
  - `test_pick_dest_topic_legacy_short_name` — `products_dlq` → `pg.public.products`.
  - `test_pick_dest_topic_refuses_debezium_connect_dlq` — raises `RefusedError` with the pre-Debezium-bytes message.
  - `test_pick_dest_topic_refuses_unknown_naming` — raises `RefusedError` for an unrecognized suffix.
  - `test_refuse_if_re_replay_raises_when_field_present` — payload with `_replay_source_topic` raises with the reference to the original topic+offset.
  - `test_refuse_if_re_replay_passes_when_absent` — payload without the field returns cleanly.
  - `test_strip_dlq_envelope_drops_error_fields` — result has no `_error_*` keys, preserves everything else including `_version` and `_deleted`.
- [ ] 2.2 CLI argument parsing sanity — verify `dlq_replay.py --help` lists exactly `list`, `inspect`, `audit-log` and no `replay`.

## 3. Phase 3 — Live smoke

- [ ] 3.1 Verify `dlq_replay_log` exists after `make apply-dlq-topics` with 7d/100MB retention.
- [ ] 3.2 `python scripts/dlq_replay.py list --topic products_cdc_sink_dlq` against the topic populated by prior smokes — expect at least 3 rows with correct columns.
- [ ] 3.3 `python scripts/dlq_replay.py inspect --topic products_cdc_sink_dlq --offset 0` — expect full JSON payload including `_error_stage="spark_sink"`.
- [ ] 3.4 `python scripts/dlq_replay.py audit-log --format json` against the empty topic — expect exit 0 and empty JSON array.
- [ ] 3.5 `make dlq-list TOPIC=products_cdc_sink_dlq` and `make dlq-inspect TOPIC=products_cdc_sink_dlq OFFSET=0` — expect identical output to the direct CLI invocations.

## 4. Archive

- [ ] 4.1 Run `openspec validate --changes --specs` — all pass.
- [ ] 4.2 `openspec archive add-dlq-replay --yes`.
- [ ] 4.3 Verify main specs post-archive: `error-handling` gains `dlq-diagnostic-cli` + `dlq-replay-pure-helpers`; `dlq-topic-retention` MODIFIED to include `dlq_replay_log`.
- [ ] 4.4 Tick post-archive tasks in the archived file.
