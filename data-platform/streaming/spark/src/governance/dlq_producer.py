"""Shared DLQ producer for CDC pipeline.

A single Kafka producer helper used by every DLQ path in the pipeline
(GX validation gate, Spark sink wrapper, future stages). Every DLQ
message carries the same envelope so a single Streamlit view or Grafana
Loki query can render all `*_dlq` topics without stage-specific parsing.
"""
from __future__ import annotations

import logging
import os
from typing import Mapping, Optional

from pyspark.sql import DataFrame
from pyspark.sql.functions import lit, struct, to_json

logger = logging.getLogger(__name__)


def emit(
    rows_df: DataFrame,
    topic: str,
    error_stage: str,
    extra_fields: Optional[Mapping[str, str]] = None,
) -> None:
    """Publish every row in `rows_df` to `topic` with a shared DLQ envelope.

    Envelope columns added alongside the JSON of the original row:
        _error_stage    -- e.g., "gx_validation", "spark_sink"
        _error_class    -- optional exception class name (from extra_fields)
        _error_message  -- optional exception message (from extra_fields)
        <any extra>     -- caller-supplied fields (e.g., _error_expectation)

    The full original row is preserved as a JSON string in the Kafka
    message value so downstream triage tools can render it verbatim.
    """
    if rows_df.rdd.isEmpty():
        return

    kafka_servers = os.getenv("KAFKA_SERVERS", "kafka1:9092")
    count = rows_df.count()
    logger.warning(
        "DLQ emit: routing %d rows to %s (stage=%s)", count, topic, error_stage
    )

    enriched = rows_df.withColumn("_error_stage", lit(error_stage))
    if extra_fields:
        for k, v in extra_fields.items():
            enriched = enriched.withColumn(k, lit(v))

    (
        enriched.select(
            to_json(struct("*")).alias("value"),
            lit(topic).alias("key"),
        )
        .write.format("kafka")
        .option("kafka.bootstrap.servers", kafka_servers)
        .option("topic", topic)
        .save()
    )
