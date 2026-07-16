"""Spark sink DLQ wrapper.

Wraps a `foreachBatch` writer so that any exception raised during the
sink write (e.g., ClickHouse timeout, JDBC connection refused) does
NOT crash the streaming query. Instead, the failing batch's rows are
routed to `{table}_sink_dlq` with the exception class + message
attached, and the batch is treated as successfully consumed.

Opt-in via `ENABLE_SINK_DLQ=1`. When off, exceptions propagate as
before so dev environments still fail loudly on misconfiguration.
"""
from __future__ import annotations

import logging
from typing import Callable

from pyspark.sql import DataFrame

from src.governance import dlq_producer

logger = logging.getLogger(__name__)


def with_sink_dlq(
    inner_writer: Callable[[DataFrame, int], None],
    table: str,
) -> Callable[[DataFrame, int], None]:
    """Return a foreachBatch function that catches exceptions from
    `inner_writer` and routes the failing batch to `{table}_sink_dlq`.
    """
    def wrapped(batch_df: DataFrame, batch_id: int) -> None:
        try:
            inner_writer(batch_df, batch_id)
        except Exception as exc:  # noqa: BLE001 -- intentional: DLQ catches all
            logger.error(
                "Sink write failed for %s (batch_id=%d): %s -- routing to sink DLQ",
                table,
                batch_id,
                exc,
            )
            try:
                dlq_producer.emit(
                    batch_df,
                    topic=f"{table}_sink_dlq",
                    error_stage="spark_sink",
                    extra_fields={
                        "_error_class": exc.__class__.__name__,
                        "_error_message": str(exc),
                    },
                )
            except Exception as dlq_exc:  # noqa: BLE001
                logger.error(
                    "Sink DLQ emit itself failed for %s: %s", table, dlq_exc
                )

    return wrapped
