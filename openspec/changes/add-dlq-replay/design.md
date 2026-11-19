## Context

Post-`add-dlq-retention` the DLQ story is: bad record → quarantine → observe (Grafana + Streamlit) → 7 days → gone. During design of the original "closing action" (replay), we discovered upstream topics carry Debezium's Confluent-shape Avro wire format `[0x00][contentId:int32][avro body]`. A tool that produces JSON directly to those topics will silently break the Spark consumer at Avro decode; a tool that produces Avro correctly needs:

- Apicurio Registry HTTP client with fingerprint check
- fastavro (new Python dep) with schema loading + encoding
- ContentId header assembly for every produced message
- Schema-evolution reasoning when the DLQ was captured under a different schema version than the current destination topic
- Idempotency semantics coordinated with ClickHouse `ReplacingMergeTree(_version)`
- Re-replay refusal, rate limiting, audit log, Streamlit subprocess wiring

Combined, that's ~30-40 tasks with several unknowns (schema drift handling was flagged as "refuse and force operator hand-migration" but we haven't seen a real incident to know if that's the right ergonomics). Rather than absorb the full risk in one change, we split:

- **This change (`add-dlq-replay`)** — the *read* half. A CLI that surfaces DLQ contents with structured output so operators can enumerate + inspect during incident review, and a shared `dlq_replay_log` topic that a future writer will populate. Every subcommand is read-only; no Kafka producer is instantiated anywhere.
- **Future change (`add-dlq-avro-replay`)** — the *write* half. Adds the `replay` subcommand plus everything above (Avro encoder, schema drift refusal, deterministic keys, re-replay guard runtime call, audit-log producer, Streamlit action). It builds on this change's pure helpers so we don't relitigate the envelope shape.

## Goals / Non-Goals

**Goals:**
- `python scripts/dlq_replay.py list --topic <name>` prints one row per DLQ message with offset, key preview, error stage, truncated error message.
- `python scripts/dlq_replay.py inspect --topic <name> --offset N` prints the full JSON payload of the target message.
- `python scripts/dlq_replay.py audit-log --format json` reads all messages currently on `dlq_replay_log` and prints them. `--format table` prints a summary view.
- `dlq_replay_log` topic is created with the same retention semantics as the other DLQ topics.
- Pure helpers (`build_replay_key`, `strip_dlq_envelope`, `pick_dest_topic`, `refuse_if_re_replay`) exist and are unit-tested even though no runtime code calls them yet — the future change plugs into them without re-designing.

**Non-Goals:**
- Any Kafka production. This change instantiates zero producers.
- The `replay` subcommand. Argparse doesn't even declare it.
- Streamlit UI action. `dlq-triage-view` is untouched.
- Schema drift handling, Avro encoding, contentId management. All deferred.
- Postgres re-INSERT. Not the direction for the eventual replay either — see the follow-up change.

## Decisions

### D1. Ship the pure helpers now, wire them later

`build_replay_key(topic, partition, offset)`, `strip_dlq_envelope(payload)`, `pick_dest_topic(source_topic)`, `refuse_if_re_replay(payload)`, and the `RefusedError` type are all implemented and unit-tested in this change. None are called by any CLI subcommand shipped here.

Why: designing them alongside the CLI where the semantics are clear costs almost nothing extra, and it locks the envelope shape (`_replay_source_*` fields, key derivation) in a place that's easy to reference from the future change's spec. Yagni concern noted; the counter-argument is that these helpers *are* the CLI's public interface for testing purposes, and shipping them without callers is a small price for keeping the follow-up change's scope tight.

Alternative rejected: strip the pure helpers, ship only `list`/`inspect`. Would work, but the follow-up change would need to re-argue the envelope shape from scratch and risk drift with tests we can write today.

### D2. `dlq_replay_log` topic is created now with no producer

The topic ships in this change's `setup_dlq_topics.sh` update. The `audit-log` subcommand reads it (empty in steady-state). The **writer** ships in `add-dlq-avro-replay`.

Why: creating the topic once with correct retention avoids a race where the first replay run in the future change produces a message before the topic exists, which would auto-create it with broker defaults and silently defeat the retention semantics. Ship the topic where the retention model lives.

Alternative rejected: defer the topic creation to the follow-up change. Requires that change to also modify `setup_dlq_topics.sh`, mixing infra + CLI concerns in one change. Cleaner boundary if the retention story lives here.

### D3. Argparse layout accommodates future `replay` without churn

Subparser structure is `dlq_replay {list | inspect | audit-log}`. Adding `replay` in the future change is one new `add_parser` call. The name `dlq_replay.py` looks like it should have a `replay` subcommand today; we accept the naming lead so the follow-up change doesn't require renaming.

### D4. No test for helpers whose runtime consumer doesn't exist

Wait — this contradicts D1. Resolution: we DO test the pure helpers (their contracts are stable), but we do NOT write integration tests for the "call site" because there is no call site. The tests exercise the function inputs → outputs directly; when the follow-up change wires them into the replay flow, it adds integration tests then.

### D5. Makefile targets

Two new targets: `dlq-list TOPIC=...` and `dlq-inspect TOPIC=... OFFSET=...`. Both are thin wrappers around the CLI. No `dlq-replay` target — that ships with the write half. Rationale: operators typing `make dlq-<tab>` should only see actions that exist and are safe.

## Risks / Trade-offs

- **[Risk] Shipping helpers without callers is dead code** → Mitigation: the tests are the callers. Coverage will be 100% of the helper surface. When the follow-up change wires them in, no helper needs to be added or refactored.
- **[Risk] Operators expect a `replay` subcommand because the file is called `dlq_replay.py`** → Mitigation: CLI top-level help explicitly says "read-only diagnostic tool; replay pending in add-dlq-avro-replay". Documentation in `docs/observability.md` says the same.
- **[Trade-off] Two changes instead of one** → Accepted: the write half's design is not fully baked (schema drift ergonomics unknown until we see a real incident). Splitting lets us ship the read half's value now and iterate the write half based on real usage.
- **[Trade-off] `dlq_replay_log` topic sits empty for a while** → Accepted: it's 100 MB of unused broker headroom max. The `audit-log` subcommand works today (returns "no records"), so operators discover the shape and are ready when writes begin.
