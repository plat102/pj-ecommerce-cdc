"""
Governance access log — startup emitter for CDC consumers.

Each Spark CDC job calls emit_startup on process start to write a single
identity event to the ``governance.access_log`` Kafka topic. Auditors can
then answer "which consumer subscribed to which topics" without grepping
container logs.

Failure to emit is logged and swallowed — the governance audit trail must
never take a live pipeline down.
"""
from __future__ import annotations

import json
import logging
import os
import socket
from datetime import datetime, timezone
from typing import Iterable

logger = logging.getLogger(__name__)

ACCESS_LOG_TOPIC = "governance.access_log"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def emit_startup(
    principal: str,
    topics: Iterable[str],
    bootstrap_servers: str,
    *,
    extra: dict | None = None,
) -> bool:
    """
    Publish one startup event to ``governance.access_log``.

    Args:
        principal: Logical consumer identity (e.g. "spark-customers-cdc",
            "streamlit-kafka-monitor").
        topics: Kafka topics the consumer will subscribe to.
        bootstrap_servers: Comma-separated Kafka bootstrap servers.
        extra: Optional additional fields merged into the event body.

    Returns:
        True if the event was successfully published, False otherwise.
    """
    payload = {
        "event": "consumer_start",
        "principal": principal,
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "topics": sorted(set(topics)),
        "timestamp": _now_iso(),
    }
    if extra:
        payload.update(extra)

    try:
        from kafka import KafkaProducer  # local import: kafka-python is optional at import time
    except ImportError:
        logger.warning(
            "kafka-python not installed; skipping governance.access_log emit for %s",
            principal,
        )
        return False

    try:
        producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda v: v.encode("utf-8") if v is not None else None,
            acks="all",
            retries=2,
            request_timeout_ms=5000,
        )
        producer.send(ACCESS_LOG_TOPIC, key=principal, value=payload).get(timeout=5)
        producer.flush(timeout=5)
        producer.close(timeout=5)
        logger.info("access_log: emitted startup event for principal=%s", principal)
        return True
    except Exception as exc:  # noqa: BLE001 — audit emit must not crash the pipeline
        logger.warning(
            "access_log: failed to emit startup event for principal=%s: %s",
            principal,
            exc,
        )
        return False
