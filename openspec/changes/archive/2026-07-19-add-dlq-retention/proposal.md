## Why

The 8 DLQ topics introduced by `add-error-handling-dlq` (`debezium_connect_dlq`, `{customers,products,orders}_cdc_dlq`, `{customers,products,orders}_cdc_sink_dlq`) currently auto-create on first bad record and inherit the Kafka broker's default retention — effectively "forever" on the dev volume. On a long-running local stack this means:

- Kafka log volume creeps unboundedly. A single stuck upstream (e.g. schema-registry down for a week) can fill the disk while the operator is unaware.
- The Streamlit DLQ Triage view consumes with `from_beginning=True` inside a 5-min timestamp filter, so old accumulated messages don't display but Kafka still reads and skips them — cold-start latency grows with history depth.
- There is no defined way to "drain and forget" a DLQ topic after the underlying issue is fixed, other than deleting the topic entirely (destructive and undoes any partial diagnosis).

## What Changes

- Introduce `scripts/setup_dlq_topics.sh` that pre-creates every DLQ topic explicitly via `kafka-topics --create --if-not-exists`, with `retention.ms=604800000` (7 days, aligned with Loki retention set in observability Phase 1) and `retention.bytes=104857600` (100 MB per topic). Cleanup policy stays `delete` — DLQ is time-series, not key-based.
- Add a Makefile target `apply-dlq-topics` that runs the script, and wire it into `make up` right after Kafka reports healthy (before Debezium connector apply, so the first bad record from Debezium lands in a topic with correct retention rather than auto-created broker defaults).
- Extend `docs/observability.md` with a "DLQ operations" section: when to drain vs escalate, what retention means for triage workflows, how to raise retention temporarily for post-incident forensics.

Non-goals:
- No automatic drain/archive when retention expires (Kafka handles the delete; there's no "cold storage" tier here).
- No per-topic retention tuning knobs — all DLQ topics share the same 7d/100MB defaults, overrideable at script-invocation time via env vars for the temporary-raise workflow.
- No compaction (`cleanup.policy=compact`) — DLQ payloads are events, not state; last-write-wins would silently drop errors.

## Capabilities

### New Capabilities
None. This change extends the existing `error-handling` and `infrastructure` capabilities.

### Modified Capabilities
- `error-handling`: adds a new requirement `dlq-topic-retention` covering the retention/size floor for every `*_dlq` topic in the stack.
- `infrastructure`: extends `per-service-targets` / `full-stack-startup` requirements with the `apply-dlq-topics` target and its position in the `make up` sequence.

## Impact

**Code**:
- New: `scripts/setup_dlq_topics.sh`
- Modified: `Makefile` (new target + wire into `up`)
- Modified: `docs/observability.md` (new "DLQ operations" section)
- Modified: `.env.example` (optional `DLQ_RETENTION_MS`, `DLQ_RETENTION_BYTES` overrides)

**Runtime behavior**:
- On first-ever `make up` after this change: script creates 9 DLQ topics up front. Idempotent (`--if-not-exists`), safe to re-run.
- On subsequent `make up`: script no-ops for existing topics but re-applies retention config via `--alter` so retention can drift-correct if a topic was pre-created by hand.
- Existing DLQ topics that already accumulated messages: retention is applied non-destructively; Kafka enforces the new limit lazily on next log-cleaner pass.

**No breaking changes** for CDC pipeline or governance code — DLQ producers already reference topic names by string constant; broker-side retention is transparent.
