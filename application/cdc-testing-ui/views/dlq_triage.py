"""Streamlit DLQ Triage view.

Read-only page that lists recent contents from every `*_dlq` topic in
the stack (Kafka Connect DLQ + Spark GX DLQ + Spark sink DLQ) in a
single table with error-stage / error-class / truncated error-message
columns and an expander per row for the full JSON payload.

The Kafka consume path reuses `managers.kafka.KafkaManager.consume_messages`
so the underlying wire behavior stays identical to the existing
`Kafka Monitor` view.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping

import streamlit as st

DLQ_TOPICS: List[str] = [
    "debezium_connect_dlq",
    "customers_dlq",
    "products_dlq",
    "orders_dlq",
    "customers_sink_dlq",
    "products_sink_dlq",
    "orders_sink_dlq",
]

_MSG_TRUNC = 80


def _coerce_payload(value: Any) -> Mapping[str, Any]:
    """The kafka manager already JSON-deserializes values; but Kafka
    Connect DLQ writes the raw failing record as bytes, so we handle
    both cases by re-parsing strings and returning a dict-ish view."""
    if isinstance(value, Mapping):
        return value
    if isinstance(value, (bytes, bytearray)):
        try:
            return json.loads(value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"_raw": repr(value)}
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"_raw": value}
    return {"_raw": repr(value)}


def build_triage_rows(messages: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Convert raw KafkaManager messages into flat triage rows.

    Each row has the columns rendered by the view. Kept as a pure
    function so tests can call it directly with synthetic messages.
    """
    rows: List[Dict[str, Any]] = []
    for msg in messages:
        payload = _coerce_payload(msg.get("value"))
        err_msg = payload.get("_error_message") or ""
        rows.append(
            {
                "dlq_topic": msg.get("topic", ""),
                "_error_stage": payload.get("_error_stage") or "unknown",
                "_error_class": payload.get("_error_class") or "",
                "_error_message": (
                    err_msg[:_MSG_TRUNC] + "..."
                    if len(err_msg) > _MSG_TRUNC
                    else err_msg
                ),
                "key": msg.get("key") or "",
                "first_seen": msg.get("timestamp"),
                "_payload": payload,
            }
        )
    return rows


def show_dlq_triage():
    """Render the DLQ Triage page."""
    st.header("🚨 DLQ Triage")
    st.markdown(
        "Recent messages from every dead-letter topic in the pipeline "
        "(Kafka Connect DLQ, Spark GX validation DLQ, Spark sink DLQ)."
    )

    if "kafka_manager" not in st.session_state:
        st.warning(
            "Kafka not initialized. Open any table view first so the "
            "shared session-state Kafka manager is created."
        )
        return

    max_messages = st.number_input(
        "Max messages per topic", min_value=10, max_value=500, value=100, step=10
    )
    recent_only = st.checkbox("Recent only (5 min)", value=True)

    with st.spinner("Reading DLQ topics..."):
        try:
            raw = st.session_state.kafka_manager.consume_messages(
                DLQ_TOPICS,
                max_messages=int(max_messages),
                recent_only=recent_only,
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Kafka read failed: {exc}")
            return

    rows = build_triage_rows(raw)

    if not rows:
        st.info(
            "No DLQ messages in the selected window. This is the "
            "steady-state — DLQ topics only receive traffic when a "
            "record fails Kafka Connect conversion, GX validation, "
            "or the Spark sink write."
        )
        return

    st.success(f"Found {len(rows)} DLQ messages across {len({r['dlq_topic'] for r in rows})} topics")

    table_view = [
        {k: v for k, v in row.items() if k != "_payload"}
        for row in rows
    ]
    st.dataframe(table_view, use_container_width=True, hide_index=True)

    st.subheader("Message details")
    for i, row in enumerate(rows):
        ts = row["first_seen"]
        ts_label = (
            ts.strftime("%H:%M:%S") if isinstance(ts, datetime) else str(ts)
        )
        with st.expander(
            f"[{row['_error_stage']}] {row['dlq_topic']} at {ts_label} — "
            f"{row['_error_class']}: {row['_error_message']}",
            expanded=(i < 3),
        ):
            st.json(row["_payload"], expanded=False)
