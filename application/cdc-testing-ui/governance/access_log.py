"""
Governance access log emitter for the Streamlit CDC monitor.

Mirrors data-platform/streaming/spark/src/governance/access_log.py — same
event shape, same topic — so downstream auditors see one uniform stream
regardless of which consumer wrote the event.
"""
from __future__ import annotations

import json
import logging
import os
import socket
from datetime import datetime, timezone
from typing import Iterable, List

logger = logging.getLogger(__name__)

ACCESS_LOG_TOPIC = "governance.access_log"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def emit_startup(
    principal: str,
    topics: Iterable[str],
    bootstrap_servers: List[str] | str,
    *,
    extra: dict | None = None,
) -> bool:
    """
    Publish one startup event to ``governance.access_log``.

    Kept best-effort: audit emit must never break the UI.
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
        from kafka import KafkaProducer
    except ImportError:
        logger.warning("kafka-python not installed; skipping access_log emit for %s", principal)
        return False

    try:
        producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda v: v.encode("utf-8") if v is not None else None,
            acks="all",
            retries=1,
            request_timeout_ms=3000,
        )
        producer.send(ACCESS_LOG_TOPIC, key=principal, value=payload).get(timeout=3)
        producer.flush(timeout=3)
        producer.close(timeout=3)
        logger.info("access_log: emitted startup event for principal=%s", principal)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("access_log: failed to emit startup for %s: %s", principal, exc)
        return False
