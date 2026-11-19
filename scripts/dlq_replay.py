#!/usr/bin/env python3
"""Read-only diagnostic CLI for the DLQ topics of the CDC pipeline.

Subcommands:
    list      --topic <name>                 one row per message: partition,
                                             offset, key preview, error stage,
                                             truncated error message
    inspect   --topic <name> --offset N      full JSON value of one message
    audit-log [--format json|table]          contents of `dlq_replay_log`

The tool never writes to Kafka: it only builds a consumer with manual
partition assignment, no consumer group and no offset commits. The
`replay` subcommand is deferred to the `add-dlq-avro-replay` change,
because upstream topics are Avro-encoded via Apicurio and a correct
replay needs a schema-aware encoder.

The pure helpers below (`build_replay_key`, `strip_dlq_envelope`,
`pick_dest_topic`, `refuse_if_re_replay`) fix the envelope contract that
the future replay path builds on. No subcommand calls them yet.

Host-side default bootstrap is `localhost:9093` (the PLAINTEXT_HOST
listener), overridable with `KAFKA_BOOTSTRAP_SERVERS` or `--bootstrap-servers`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

DESCRIPTION = (
    "DLQ diagnostic CLI: read-only diagnostic tool; "
    "replay pending in add-dlq-avro-replay.\n"
    "Never produces a Kafka message; consumes without a group or commits."
)

AUDIT_LOG_TOPIC = "dlq_replay_log"
KNOWN_TABLES = ("customers", "products", "orders")
# Longest suffix first: `products_cdc_sink_dlq` must not match `_dlq` alone.
_DLQ_SUFFIXES = ("_cdc_sink_dlq", "_sink_dlq", "_cdc_dlq", "_dlq")
CONNECT_DLQ_TOPIC = "debezium_connect_dlq"

DEFAULT_BOOTSTRAP = "localhost:9093"
DEFAULT_TIMEOUT_MS = 5000
KEY_PREVIEW_LEN = 24
MESSAGE_TRUNC = 80


class RefusedError(Exception):
    """Raised when a DLQ record must not be replayed."""


# --------------------------------------------------------------------------
# Pure helpers (contract for the future replay path)
# --------------------------------------------------------------------------

def build_replay_key(topic: str, partition: int, offset: int) -> str:
    """Deterministic replay key: sha256("topic|partition|offset")[:32]."""
    raw = f"{topic}|{partition}|{offset}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def strip_dlq_envelope(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a copy of `payload` without the `_error_*` envelope fields.

    Every other field, including `_version` and `_deleted`, is kept.
    """
    return {k: v for k, v in payload.items() if not k.startswith("_error_")}


def pick_dest_topic(source_topic: str) -> str:
    """Map a DLQ topic to the upstream Debezium topic it came from.

    Accepted names: `{table}_cdc_sink_dlq`, `{table}_cdc_dlq` (current) and
    `{table}_sink_dlq`, `{table}_dlq` (legacy), for the known CDC tables.
    """
    if source_topic == CONNECT_DLQ_TOPIC:
        raise RefusedError(
            f"{source_topic} holds raw pre-Debezium bytes that failed Kafka "
            "Connect conversion; they have no Debezium envelope to replay"
        )
    for suffix in _DLQ_SUFFIXES:
        if source_topic.endswith(suffix):
            table = source_topic[: -len(suffix)]
            if table in KNOWN_TABLES:
                return f"pg.public.{table}"
            raise RefusedError(
                f"{source_topic}: unknown table {table!r} "
                f"(known: {', '.join(KNOWN_TABLES)})"
            )
    raise RefusedError(
        f"{source_topic}: unrecognized DLQ topic naming "
        f"(expected one of the suffixes {', '.join(_DLQ_SUFFIXES)})"
    )


def refuse_if_re_replay(payload: Mapping[str, Any]) -> None:
    """Raise `RefusedError` if `payload` already came from a replay."""
    if "_replay_source_topic" in payload:
        topic = payload.get("_replay_source_topic")
        offset = payload.get("_replay_source_offset")
        raise RefusedError(
            f"payload is itself a replay of {topic}@{offset}; "
            "refusing to replay it again"
        )


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------

def decode_value(raw: Optional[bytes]) -> Any:
    """Decode a Kafka value: JSON when possible, else a `_raw` marker."""
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"_raw": repr(raw)}


def decode_key(raw: Optional[bytes]) -> str:
    if raw is None:
        return ""
    return raw.decode("utf-8", errors="replace")


def _truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[:width] + "..."


def list_row(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Flatten one decoded record into the columns of `list`."""
    value = record.get("value")
    payload = value if isinstance(value, Mapping) else {}
    return {
        "partition": record.get("partition", 0),
        "offset": record.get("offset"),
        "key": _truncate(record.get("key") or "", KEY_PREVIEW_LEN),
        "error_stage": payload.get("_error_stage") or "unknown",
        "error_message": _truncate(
            str(payload.get("_error_message") or ""), MESSAGE_TRUNC
        ),
    }


def format_table(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    """Plain fixed-width table with a header and a dash rule."""
    cells = [[_cell(row.get(c)) for c in columns] for row in rows]
    widths = [
        max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(columns)
    ]
    lines = [
        "  ".join(c.ljust(w) for c, w in zip(columns, widths)).rstrip(),
        "  ".join("-" * w for w in widths),
    ]
    for r in cells:
        lines.append("  ".join(v.ljust(w) for v, w in zip(r, widths)).rstrip())
    return "\n".join(lines)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def audit_columns(values: Sequence[Any]) -> List[str]:
    """Union of keys across audit records, in first-seen order."""
    cols: List[str] = []
    for v in values:
        if isinstance(v, Mapping):
            for k in v:
                if k not in cols:
                    cols.append(k)
    return cols


# --------------------------------------------------------------------------
# Kafka read path (consumer only, manual assignment, no commits)
# --------------------------------------------------------------------------

class TopicNotFound(Exception):
    pass


def default_consumer_factory(bootstrap_servers: str, timeout_ms: int):
    from kafka import KafkaConsumer  # lazy: --help and helpers need no broker

    return KafkaConsumer(
        bootstrap_servers=bootstrap_servers.split(","),
        group_id=None,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        consumer_timeout_ms=timeout_ms,
        client_id="dlq-diagnostic-cli",
    )


def _topic_partition(topic: str, partition: int):
    from kafka import TopicPartition

    return TopicPartition(topic, partition)


def _assign(consumer, topic: str, partitions: Optional[Sequence[int]] = None):
    available = consumer.partitions_for_topic(topic)
    if not available:
        raise TopicNotFound(topic)
    chosen = sorted(available) if partitions is None else list(partitions)
    missing = [p for p in chosen if p not in available]
    if missing:
        raise TopicNotFound(f"{topic} partition(s) {missing}")
    tps = [_topic_partition(topic, p) for p in chosen]
    consumer.assign(tps)
    return tps


def _to_record(msg) -> Dict[str, Any]:
    return {
        "topic": msg.topic,
        "partition": msg.partition,
        "offset": msg.offset,
        "timestamp": msg.timestamp,
        "key": decode_key(msg.key),
        "value": decode_value(msg.value),
    }


def read_all(consumer, topic: str, timeout_ms: int) -> List[Dict[str, Any]]:
    """Read every message currently on `topic`, earliest to end offset.

    Bounded twice: stops once each partition reaches the end offset seen at
    start, and gives up after an empty poll of `timeout_ms`.
    """
    tps = _assign(consumer, topic)
    end = consumer.end_offsets(tps)
    begin = consumer.beginning_offsets(tps)
    pending = {tp for tp in tps if end[tp] > begin[tp]}
    consumer.seek_to_beginning(*tps)
    records: List[Dict[str, Any]] = []
    while pending:
        batch = consumer.poll(timeout_ms=timeout_ms)
        if not batch:
            break
        for tp, msgs in batch.items():
            for msg in msgs:
                if msg.offset < end[tp]:
                    records.append(_to_record(msg))
                if msg.offset >= end[tp] - 1:
                    pending.discard(tp)
    records.sort(key=lambda r: (r["partition"], r["offset"]))
    return records


def read_one(
    consumer, topic: str, partition: int, offset: int, timeout_ms: int
) -> Optional[Dict[str, Any]]:
    """Return the message at `topic[partition]@offset`, or None if absent."""
    (tp,) = _assign(consumer, topic, [partition])
    begin = consumer.beginning_offsets([tp])[tp]
    end = consumer.end_offsets([tp])[tp]
    if offset < begin or offset >= end:
        return None
    consumer.seek(tp, offset)
    while True:
        batch = consumer.poll(timeout_ms=timeout_ms)
        if not batch:
            return None
        for msg in batch.get(tp, []):
            if msg.offset == offset:
                return _to_record(msg)
            if msg.offset > offset:  # gap (e.g. aborted txn marker)
                return None


# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------

def cmd_list(args, consumer) -> int:
    records = read_all(consumer, args.topic, args.timeout_ms)
    if not records:
        print(f"(no messages on {args.topic})")
        return 0
    rows = [list_row(r) for r in records]
    print(format_table(
        rows, ["partition", "offset", "key", "error_stage", "error_message"]
    ))
    print(f"\n{len(rows)} message(s) on {args.topic}")
    return 0


def cmd_inspect(args, consumer) -> int:
    record = read_one(
        consumer, args.topic, args.partition, args.offset, args.timeout_ms
    )
    if record is None:
        print(
            f"error: no message at {args.topic}[{args.partition}]@{args.offset}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(record["value"], indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def cmd_audit_log(args, consumer) -> int:
    records = read_all(consumer, AUDIT_LOG_TOPIC, args.timeout_ms)
    values = [r["value"] for r in records]
    if args.format == "json":
        print(json.dumps(values, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    if not values:
        print(f"(no records on {AUDIT_LOG_TOPIC})")
        return 0
    rows = [v if isinstance(v, Mapping) else {"_value": v} for v in values]
    print(format_table(rows, audit_columns(rows)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dlq_replay.py",
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--bootstrap-servers",
        default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", DEFAULT_BOOTSTRAP),
        help="Kafka bootstrap servers (default: $KAFKA_BOOTSTRAP_SERVERS "
             f"or {DEFAULT_BOOTSTRAP})",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=DEFAULT_TIMEOUT_MS,
        help=f"give up after an empty poll of this length (default {DEFAULT_TIMEOUT_MS})",
    )
    sub = parser.add_subparsers(dest="command", metavar="{list,inspect,audit-log}")
    sub.required = True

    p_list = sub.add_parser("list", help="one row per message of a DLQ topic")
    p_list.add_argument("--topic", required=True)
    p_list.set_defaults(func=cmd_list)

    p_inspect = sub.add_parser("inspect", help="full JSON value of one message")
    p_inspect.add_argument("--topic", required=True)
    p_inspect.add_argument("--offset", type=int, required=True)
    p_inspect.add_argument("--partition", type=int, default=0)
    p_inspect.set_defaults(func=cmd_inspect)

    p_audit = sub.add_parser("audit-log", help=f"read the {AUDIT_LOG_TOPIC} topic")
    p_audit.add_argument("--format", choices=("json", "table"), default="table")
    p_audit.set_defaults(func=cmd_audit_log)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    consumer_factory: Optional[Callable[[str, int], Any]] = None,
) -> int:
    args = build_parser().parse_args(argv)
    factory = consumer_factory or default_consumer_factory
    try:
        consumer = factory(args.bootstrap_servers, args.timeout_ms)
    except Exception as exc:  # noqa: BLE001 -- e.g. kafka.errors.NoBrokersAvailable
        print(
            f"error: cannot connect to Kafka at {args.bootstrap_servers}: "
            f"{exc.__class__.__name__}",
            file=sys.stderr,
        )
        return 2
    try:
        return args.func(args, consumer)
    except TopicNotFound as exc:
        print(f"error: topic not found: {exc}", file=sys.stderr)
        return 2
    finally:
        consumer.close()


if __name__ == "__main__":
    sys.exit(main())
