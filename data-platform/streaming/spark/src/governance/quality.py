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
    # GX proper is only used for richer reporting outside the hot path. The
    # inline gate below is pure Spark and runs even without GX installed.
    try:
        import great_expectations as gx  # noqa: F401
    except ImportError:
        logger.debug(
            "great_expectations not installed; using inline gate only for %s", table
        )

    try:
        suite = _load_suite(table)
    except FileNotFoundError:
        logger.warning("No GX suite for %s at %s; skipping", table, _SUITE_DIR)
        empty = batch_df.limit(0).withColumn("_failed_expectation", lit(None))
        return batch_df, empty

    # In-Spark implementation of the expectation kinds that catch the most CDC
    # breakage: not_null, value_in_set, value_between, and value_length_between.
    # Full GX suite runs richer checks and is invoked separately for reporting;
    # the inline check here is the gate.
    #
    # Range/length checks skip NULLs so that per-expectation `mostly` semantics
    # (e.g. NULLs on op="d" excluded) don't fire false positives at the row
    # level. Batch-wide `mostly` (the fraction of rows the expectation allows
    # to fail) is applied afterwards: if the fraction of rows that fail a
    # specific expectation stays within its tolerance, those rows are treated
    # as passing.
    from pyspark.sql.functions import coalesce, col, length, when

    row_bad_by_expectation: list[tuple[str, object, float]] = []
    for exp in suite.get("expectations", []):
        etype = exp["expectation_type"]
        col_name = exp["kwargs"].get("column")
        mostly = float(exp["kwargs"].get("mostly", 1.0))
        if not col_name or col_name not in batch_df.columns:
            continue
        row_bad = None
        if etype == "expect_column_values_to_not_be_null":
            row_bad = col(col_name).isNull()
        elif etype == "expect_column_values_to_be_in_set":
            allowed = exp["kwargs"].get("value_set", [])
            row_bad = col(col_name).isNotNull() & ~col(col_name).isin(allowed)
        elif etype == "expect_column_values_to_be_between":
            min_v = exp["kwargs"].get("min_value")
            max_v = exp["kwargs"].get("max_value")
            out_of_range = lit(False)
            if min_v is not None:
                out_of_range = out_of_range | (col(col_name) < lit(min_v))
            if max_v is not None:
                out_of_range = out_of_range | (col(col_name) > lit(max_v))
            row_bad = col(col_name).isNotNull() & out_of_range
        elif etype == "expect_column_value_lengths_to_be_between":
            min_v = exp["kwargs"].get("min_value")
            max_v = exp["kwargs"].get("max_value")
            len_expr = length(col(col_name))
            length_out_of_range = lit(False)
            if min_v is not None:
                length_out_of_range = length_out_of_range | (len_expr < lit(min_v))
            if max_v is not None:
                length_out_of_range = length_out_of_range | (len_expr > lit(max_v))
            row_bad = col(col_name).isNotNull() & length_out_of_range
        if row_bad is not None:
            row_bad_by_expectation.append((etype, row_bad, mostly))

    if not row_bad_by_expectation:
        empty = batch_df.limit(0).withColumn("_failed_expectation", lit(None))
        return batch_df, empty

    # Apply per-expectation `mostly`: if a given expectation's failure rate is
    # within tolerance, ignore its row-level failures for this batch.
    total = batch_df.count()
    active: list[tuple[str, object]] = []
    for etype, row_bad, mostly in row_bad_by_expectation:
        if mostly >= 1.0 or total == 0:
            active.append((etype, row_bad))
            continue
        fail_count = batch_df.filter(row_bad).count()
        # GX semantics: expectation passes when success_ratio >= mostly.
        # Failing rows only escalate to the gate when the expectation itself
        # has already failed batch-wide.
        success_ratio = 1.0 - (fail_count / total) if total else 1.0
        if success_ratio < mostly:
            active.append((etype, row_bad))

    if not active:
        empty = batch_df.limit(0).withColumn("_failed_expectation", lit(None))
        return batch_df, empty

    # Per-row failing expectation: whichever active expectation fires first
    # (in suite declaration order) becomes that row's label.
    failing_col = lit(None).cast("string")
    invalid_mask = lit(False)
    for etype, row_bad in reversed(active):
        failing_col = when(row_bad, lit(etype)).otherwise(failing_col)
    for _, row_bad in active:
        invalid_mask = invalid_mask | row_bad

    invalid = batch_df.filter(invalid_mask).withColumn(
        "_failed_expectation", coalesce(failing_col, lit("unknown"))
    )
    valid = batch_df.filter(~invalid_mask)
    return valid, invalid


def with_gx_gate(inner_writer: Callable[[DataFrame, int], None], table: str) -> Callable[[DataFrame, int], None]:
    """Return a foreachBatch function that runs GX before delegating to
    `inner_writer`. Invalid rows go to `{table}_dlq` and are dropped from
    the ClickHouse write.
    """
    from pyspark.sql.functions import col, lit
    from src.governance import dlq_producer

    def wrapped(batch_df: DataFrame, batch_id: int) -> None:
        if batch_df.isEmpty():
            inner_writer(batch_df, batch_id)
            return
        valid, invalid = _validate_with_gx(batch_df, table)
        invalid_count = invalid.limit(1).count()
        logger.info(
            "gx-gate table=%s batch=%d invalid=%s",
            table, batch_id, "yes" if invalid_count else "no",
        )
        if invalid_count > 0:
            # Preserve per-row failing expectation so DLQ consumers can filter
            # by the specific expectation that fired.
            payload = (
                invalid
                .withColumnRenamed("_failed_expectation", "_error_expectation")
                .withColumn("_error_class", lit("ExpectationFailure"))
                .withColumn("_error_message", col("_error_expectation"))
            )
            dlq_producer.emit(
                payload,
                topic=f"{table}_dlq",
                error_stage="gx_validation",
            )
        inner_writer(valid, batch_id)

    return wrapped
