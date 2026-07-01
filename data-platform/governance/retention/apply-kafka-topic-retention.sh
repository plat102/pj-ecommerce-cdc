#!/usr/bin/env bash
# Apply explicit per-topic retention to Kafka.
# Idempotent: re-running updates the existing config.
#
# Retention policy (from openspec/changes/add-data-governance/design.md, Pillar 4):
#   pg.public.*            7 days   (source CDC events)
#   governance.access_log  30 days  (consumer identity audit)
#   *_dlq                  14 days  (validation-failed rows, replay window)

set -euo pipefail

KAFKA_CONTAINER="${KAFKA_CONTAINER:-kafka1}"
BOOTSTRAP="${BOOTSTRAP:-kafka1:9092}"

DAY_MS=86400000
RETENTION_PG_MS=$((7 * DAY_MS))
RETENTION_ACCESS_LOG_MS=$((30 * DAY_MS))
RETENTION_DLQ_MS=$((14 * DAY_MS))

kafka() {
    docker exec "$KAFKA_CONTAINER" "$@"
}

configure_topic() {
    local topic="$1"
    local retention_ms="$2"
    kafka kafka-configs --bootstrap-server "$BOOTSTRAP" \
        --entity-type topics --entity-name "$topic" \
        --alter --add-config "retention.ms=${retention_ms}"
    echo "configured ${topic}: retention.ms=${retention_ms}"
}

ensure_topic() {
    local topic="$1"
    local retention_ms="$2"
    if ! kafka kafka-topics --bootstrap-server "$BOOTSTRAP" --describe --topic "$topic" >/dev/null 2>&1; then
        kafka kafka-topics --bootstrap-server "$BOOTSTRAP" \
            --create --topic "$topic" \
            --partitions 1 --replication-factor 1 \
            --config "retention.ms=${retention_ms}"
        echo "created ${topic}: retention.ms=${retention_ms}"
    else
        configure_topic "$topic" "$retention_ms"
    fi
}

# CDC source topics — created by Debezium, apply retention post-hoc
for topic in pg.public.customers pg.public.products pg.public.orders; do
    if kafka kafka-topics --bootstrap-server "$BOOTSTRAP" --describe --topic "$topic" >/dev/null 2>&1; then
        configure_topic "$topic" "$RETENTION_PG_MS"
    else
        echo "skipping ${topic}: not present yet (register the Debezium connector first)"
    fi
done

# Governance topics — create if missing so retention is pinned from day one
ensure_topic governance.access_log "$RETENTION_ACCESS_LOG_MS"
ensure_topic customers_dlq "$RETENTION_DLQ_MS"
ensure_topic products_dlq "$RETENTION_DLQ_MS"
ensure_topic orders_dlq "$RETENTION_DLQ_MS"
