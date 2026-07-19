## Why

`add-error-handling-dlq` gave us DLQ topics + a read-only Streamlit Triage view; `add-dlq-retention` gave us 7-day retention. What's missing is a repeatable operator workflow after diagnosing a bad record: today the only options are wait for retention expiry, delete + recreate the topic, or hand-craft a `kafka-console-consumer` invocation and eyeball the JSON. There is no auditable, scriptable way to enumerate a specific DLQ topic's contents or produce a diagnostic report during an incident review.

We originally scoped this change to include an *automated replay* path — re-produce DLQ messages back into `pg.public.{table}` so the Spark pipeline picks them up. During design implementation we hit a fundamental blocker: upstream topics are Avro-encoded via Apicurio (Confluent wire format `[0x00][contentId:int32][avro body]`), so an automated replay requires the CLI to fetch schemas from Apicurio, encode payloads with fastavro, prepend contentId headers, and handle schema evolution. That's an entire second complexity budget — see design.md §Context for the full walk-through. Rather than absorb it in one change, we ship the **tooling half now** (list / inspect / audit-log) and leave the **encoding half** to a future `add-dlq-avro-replay` change once we have real incidents to inform the design.

## What Changes

- Introduce `scripts/dlq_replay.py` — a Python CLI with three read-only subcommands:
  - `list --topic <name>` — enumerate messages with offset, key preview, `_error_stage`, truncated `_error_message`.
  - `inspect --topic <name> --offset N` — pretty-print the full JSON payload of one message.
  - `audit-log --format json|table` — read the batch-level audit records written by future replay actions (topic exists now; producers land later).
- Add the `dlq_replay_log` topic to `scripts/setup_dlq_topics.sh` so it inherits the shared 7d/100MB retention config. The audit-log **reader** ships in this change; the **writer** waits for `add-dlq-avro-replay`.
- Unit tests for the pure helpers in `tests/scripts/test_dlq_replay.py`.
- `docs/observability.md` "DLQ operations" section is extended with a one-paragraph pointer to the CLI so operators discover it during incident review.

**Explicit non-goal for this change:** no `replay` subcommand. No production of any Kafka message. The CLI is strictly a diagnostic reader.

## Capabilities

### New Capabilities
None. All modifications land on existing capabilities.

### Modified Capabilities
- `error-handling`: adds requirement `dlq-diagnostic-cli` (subcommand contract for `list`, `inspect`, `audit-log`). Extends `dlq-topic-retention` to include `dlq_replay_log` in the retention-managed topic set.
- `streamlit-ui`: no change. The proposed per-row Replay button is deferred to `add-dlq-avro-replay` because it is meaningless without an actual replay path.

## Impact

**New code**:
- `scripts/dlq_replay.py` (CLI, no external writes)
- `tests/scripts/test_dlq_replay.py` (unit tests)

**Modified code**:
- `scripts/setup_dlq_topics.sh` — add `dlq_replay_log` to the topic array
- `Makefile` — add `dlq-list` and `dlq-inspect` convenience targets
- `docs/observability.md` — one-paragraph pointer to the CLI

**Runtime behavior**:
- CLI is read-only. Running it against any topic never produces a message anywhere.
- `dlq_replay_log` is created empty on `make up`; readers see zero rows until a future change starts writing.

**No breaking changes**. The tool adds observability without touching hot paths.

**Deferred to `add-dlq-avro-replay`**: everything that requires actually producing messages — the `replay` subcommand, deterministic key derivation, re-replay refusal at runtime (the pure helper stays testable here so the future change can reuse it), audit-log writer, Streamlit Replay button, schema drift guard.
