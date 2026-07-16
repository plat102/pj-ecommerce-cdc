"""Great Expectations wrapper for CDC micro-batches.

Runs the per-table suite against the DataFrame *before* the ClickHouse
write. Rows that fail column-level expectations are routed to `{table}_dlq`
with the failing expectation name attached; passing rows continue to the
sink. If GX itself fails to import (skeleton mode), validation is skipped
and a warning is logged — this is intentional so Phase 3 config can land
without forcing every dev to install ~200MB of GX.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Callable, Tuple

from pyspark.sql import DataFrame
from pyspark.sql.functions import lit

logger = logging.getLogger(__name__)

_SUITE_DIR = Path(
    os.getenv(
        "GX_SUITE_DIR",
        "/home/jupyter/governance/expectations",
    )
)


def _load_suite(table: str) -> dict:
    path = _SUITE_DIR / f"{table}_suite.json"
    with path.open() as f:
        return json.load(f)


def _validate_with_gx(batch_df: DataFrame, table: str) -> Tuple[DataFrame, DataFrame]:
    """Split batch into (valid_df, invalid_df) using the table's suite.

    Returns (batch_df, empty_like(batch_df)) if GX is not installed, so the
    pipeline stays functional in dev environments without the dependency.
    """
    try:
        # GX is optional in dev; when absent, pass through
        import great_expectations as gx  # noqa: F401  (import guard only)
    except ImportError:
        logger.warning(
            "great_expectations not installed; skipping DQ validation for %s", table
        )
        empty = batch_df.limit(0).withColumn("_failed_expectation", lit(None))
        return batch_df, empty

    try:
        suite = _load_suite(table)
    except FileNotFoundError:
        logger.warning("No GX suite for %s at %s; skipping", table, _SUITE_DIR)
        empty = batch_df.limit(0).withColumn("_failed_expectation", lit(None))
        return batch_df, empty

    # Minimal in-Spark implementation of the two expectation kinds that catch
    # the most CDC breakage: not_null and value_in_set. Full GX suite runs
    # richer checks and is invoked separately for reporting; the inline check
    # here is the gate.
    from pyspark.sql.functions import col

    invalid_mask = lit(False)
    failing_name = None
    for exp in suite.get("expectations", []):
        etype = exp["expectation_type"]
        col_name = exp["kwargs"].get("column")
        if not col_name or col_name not in batch_df.columns:
            continue
        if etype == "expect_column_values_to_not_be_null":
            row_bad = col(col_name).isNull()
            invalid_mask = invalid_mask | row_bad
            failing_name = failing_name or etype
        elif etype == "expect_column_values_to_be_in_set":
            allowed = exp["kwargs"].get("value_set", [])
            row_bad = ~col(col_name).isin(allowed) & col(col_name).isNotNull()
            invalid_mask = invalid_mask | row_bad
            failing_name = failing_name or etype

    invalid = batch_df.filter(invalid_mask).withColumn(
        "_failed_expectation", lit(failing_name or "unknown")
    )
    valid = batch_df.filter(~invalid_mask)
    return valid, invalid


def with_gx_gate(inner_writer: Callable[[DataFrame, int], None], table: str) -> Callable[[DataFrame, int], None]:
    """Return a foreachBatch function that runs GX before delegating to
    `inner_writer`. Invalid rows go to `{table}_dlq` and are dropped from
    the ClickHouse write.
    """
    from src.governance import dlq_producer

    def wrapped(batch_df: DataFrame, batch_id: int) -> None:
        if batch_df.isEmpty():
            inner_writer(batch_df, batch_id)
            return
        valid, invalid = _validate_with_gx(batch_df, table)
        if invalid.limit(1).count() > 0:
            failing = (
                invalid.select("_failed_expectation")
                .limit(1)
                .collect()[0]["_failed_expectation"]
            )
            failing_name = failing or "unknown"
            dlq_producer.emit(
                invalid.drop("_failed_expectation"),
                topic=f"{table}_dlq",
                error_stage="gx_validation",
                extra_fields={
                    "_error_class": "ExpectationFailure",
                    "_error_message": failing_name,
                    "_error_expectation": failing_name,
                },
            )
        inner_writer(valid, batch_id)

    return wrapped
