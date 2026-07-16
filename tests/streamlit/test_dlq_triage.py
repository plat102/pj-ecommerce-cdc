"""Unit tests for `views.dlq_triage.build_triage_rows`.

The pure function is what carries all the shape/truncation logic; the
Streamlit render layer is thin and exercised via live smoke in Phase 4.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Make application/cdc-testing-ui importable exactly as it is at runtime.
_APP_ROOT = (
    Path(__file__).resolve().parents[2] / "application" / "cdc-testing-ui"
)
sys.path.insert(0, str(_APP_ROOT))


def test_build_triage_rows_shape():
    from views.dlq_triage import build_triage_rows

    msgs = [
        {
            "topic": "products_sink_dlq",
            "partition": 0,
            "offset": 42,
            "timestamp": datetime(2026, 7, 16, 10, 30, 0),
            "key": "products",
            "value": {
                "id": 1,
                "name": "widget",
                "_error_stage": "spark_sink",
                "_error_class": "RuntimeError",
                "_error_message": "clickhouse timeout",
            },
        }
    ]

    rows = build_triage_rows(msgs)

    assert len(rows) == 1
    row = rows[0]
    assert row["dlq_topic"] == "products_sink_dlq"
    assert row["_error_stage"] == "spark_sink"
    assert row["_error_class"] == "RuntimeError"
    assert row["_error_message"] == "clickhouse timeout"
    assert row["key"] == "products"
    assert row["first_seen"] == datetime(2026, 7, 16, 10, 30, 0)
    assert row["_payload"]["id"] == 1
    assert row["_payload"]["name"] == "widget"


def test_build_triage_rows_truncates_long_error_messages():
    from views.dlq_triage import build_triage_rows

    long_msg = "x" * 500
    msgs = [
        {
            "topic": "customers_dlq",
            "timestamp": datetime.utcnow(),
            "key": "customers",
            "value": {
                "id": 1,
                "_error_stage": "gx_validation",
                "_error_class": "ExpectationFailure",
                "_error_message": long_msg,
            },
        }
    ]

    row = build_triage_rows(msgs)[0]
    assert len(row["_error_message"]) == 83  # 80 chars + "..."
    assert row["_error_message"].endswith("...")


def test_build_triage_rows_handles_kafka_connect_raw_bytes():
    """Kafka Connect DLQ writes the raw record value that failed the
    converter — that's usually not our envelope. The function must not
    raise and should surface a `_raw` fallback."""
    from views.dlq_triage import build_triage_rows

    msgs = [
        {
            "topic": "debezium_connect_dlq",
            "timestamp": datetime.utcnow(),
            "key": None,
            "value": b"\x00\x01\x02not-json",
        }
    ]

    row = build_triage_rows(msgs)[0]
    assert row["dlq_topic"] == "debezium_connect_dlq"
    assert row["_error_stage"] == "unknown"
    assert row["_error_class"] == ""
    assert "_raw" in row["_payload"]


def test_build_triage_rows_handles_missing_error_fields():
    from views.dlq_triage import build_triage_rows

    msgs = [
        {
            "topic": "orders_dlq",
            "timestamp": datetime.utcnow(),
            "key": "orders",
            "value": {"id": 99},
        }
    ]

    row = build_triage_rows(msgs)[0]
    assert row["_error_stage"] == "unknown"
    assert row["_error_class"] == ""
    assert row["_error_message"] == ""
