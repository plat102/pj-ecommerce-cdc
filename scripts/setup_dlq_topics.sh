#!/usr/bin/env bash
# Pre-create every DLQ topic in the stack with explicit retention config.
#
# Kafka broker defaults to `log.retention.hours=168` and `log.retention.bytes=-1`
# (no size cap). Letting DLQ topics auto-create inherits that "grows forever
# on-disk" behavior, which the DLQ Triage view then has to cold-scan on every
# reload. This script pre-creates each DLQ topic with:
#
#   retention.ms     = 604800000  (7 days, matches Loki retention)
#   retention.bytes  = 104857600  (100 MB per topic, bounds worst-case disk)
#   cleanup.policy   = delete     (time-series, not compacted state)
#
# Both size/time bounds are overrideable via DLQ_RETENTION_MS / DLQ_RETENTION_BYTES.
# Overrides are transient: next `make up` drift-corrects back to the defaults
# above unless the operator persists them in .env.
#
# Idempotent. Safe to re-run: uses `--create --if-not-exists` for missing
# topics, then a second-pass `kafka-configs --alter` to drift-correct existing
# topic configs. Exits non-zero on any failure so `make up` breaks visibly.

set -euo pipefail

BOOTSTRAP="${DLQ_BOOTSTRAP:-localhost:9092}"
KAFKA_CONTAINER="${DLQ_KAFKA_CONTAINER:-kafka1}"
RETENTION_MS="${DLQ_RETENTION_MS:-604800000}"
RETENTION_BYTES="${DLQ_RETENTION_BYTES:-104857600}"

# The topic list is the source of truth for retention coverage. Adding a new
# DLQ topic elsewhere in the codebase (Debezium connector config, Spark sink
# wrapper, GX gate) MUST come with a matching entry here — the `dlq-topic-retention`
# spec asserts every broker topic ending in `_dlq` carries the config below.
DLQ_TOPICS=(
    debezium_connect_dlq
    customers_cdc_dlq
    products_cdc_dlq
    orders_cdc_dlq
    customers_cdc_sink_dlq
    products_cdc_sink_dlq
    orders_cdc_sink_dlq
)

echo "Configuring ${#DLQ_TOPICS[@]} DLQ topics on ${BOOTSTRAP} via ${KAFKA_CONTAINER}"
echo "  retention.ms    = ${RETENTION_MS}"
echo "  retention.bytes = ${RETENTION_BYTES}"
echo "  cleanup.policy  = delete"

for topic in "${DLQ_TOPICS[@]}"; do
    echo ""
    echo ">> ${topic}"

    # Pass 1: create if absent. --if-not-exists makes this a no-op when the
    # topic already exists (either from a prior boot or from auto-create).
    docker exec "${KAFKA_CONTAINER}" kafka-topics \
        --bootstrap-server "${BOOTSTRAP}" \
        --create \
        --if-not-exists \
        --topic "${topic}" \
        --partitions 1 \
        --replication-factor 1 \
        --config "retention.ms=${RETENTION_MS}" \
        --config "retention.bytes=${RETENTION_BYTES}" \
        --config "cleanup.policy=delete"

    # Pass 2: alter existing config to drift-correct. `--create --if-not-exists`
    # from pass 1 does NOT re-apply --config to an existing topic; only --alter
    # will. Running this even after a fresh create is a cheap no-op.
    docker exec "${KAFKA_CONTAINER}" kafka-configs \
        --bootstrap-server "${BOOTSTRAP}" \
        --entity-type topics \
        --entity-name "${topic}" \
        --alter \
        --add-config "retention.ms=${RETENTION_MS},retention.bytes=${RETENTION_BYTES},cleanup.policy=delete" \
        >/dev/null

    echo "   PASS retention config applied"
done

echo ""
echo "PASS ${#DLQ_TOPICS[@]} DLQ topics configured"
