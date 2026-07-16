"""Unit tests for `src.governance.error_handling.with_sink_dlq`.

Verify that a raising inner writer:
  1. does NOT propagate the exception (streaming query stays alive),
  2. results in `dlq_producer.emit` being called with the failing batch,
     the `{table}_sink_dlq` topic, and `_error_stage="spark_sink"` plus
     `_error_class` / `_error_message` in extra_fields.

Uses the shared `spark_session` fixture from conftest.py.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


def test_with_sink_dlq_catches_and_routes(spark_session):
    from src.governance.error_handling import with_sink_dlq

    df = spark_session.createDataFrame([(1, "a"), (2, "b")], ["id", "name"])

    def failing_writer(batch_df, batch_id):
        raise RuntimeError("clickhouse timeout")

    wrapped = with_sink_dlq(failing_writer, table="products")

    with patch("src.governance.error_handling.dlq_producer.emit") as emit_mock:
        wrapped(df, batch_id=0)

    assert emit_mock.call_count == 1
    call = emit_mock.call_args
    passed_df = call.args[0] if call.args else call.kwargs["rows_df"]
    assert passed_df is df
    assert call.kwargs["topic"] == "products_sink_dlq"
    assert call.kwargs["error_stage"] == "spark_sink"
    extras = call.kwargs["extra_fields"]
    assert extras["_error_class"] == "RuntimeError"
    assert extras["_error_message"] == "clickhouse timeout"


def test_with_sink_dlq_passthrough_on_success(spark_session):
    from src.governance.error_handling import with_sink_dlq

    df = spark_session.createDataFrame([(1,)], ["id"])
    called_with = {}

    def ok_writer(batch_df, batch_id):
        called_with["batch_id"] = batch_id
        called_with["count"] = batch_df.count()

    wrapped = with_sink_dlq(ok_writer, table="products")

    with patch("src.governance.error_handling.dlq_producer.emit") as emit_mock:
        wrapped(df, batch_id=42)

    assert called_with == {"batch_id": 42, "count": 1}
    emit_mock.assert_not_called()


def test_with_sink_dlq_swallows_dlq_emit_failure(spark_session):
    """If even the DLQ producer fails, `wrapped` must not raise —
    the streaming query survival guarantee is the whole point."""
    from src.governance.error_handling import with_sink_dlq

    df = spark_session.createDataFrame([(1,)], ["id"])

    def failing_writer(batch_df, batch_id):
        raise RuntimeError("primary sink dead")

    wrapped = with_sink_dlq(failing_writer, table="orders")

    with patch(
        "src.governance.error_handling.dlq_producer.emit",
        side_effect=RuntimeError("kafka also dead"),
    ):
        # Must not raise
        wrapped(df, batch_id=0)
