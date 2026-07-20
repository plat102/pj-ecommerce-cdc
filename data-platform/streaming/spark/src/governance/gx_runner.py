"""Second-pass GX validator that produces Data Docs + Prometheus metrics.

Runs **alongside** the inline gate in `quality.py` when
`ENABLE_GX_DATA_DOCS=1`. The inline gate remains the authoritative
row-drop decision; this runner is purely for reporting. Failures never
propagate — the pipeline continues even if GX itself crashes.

See openspec/changes/add-gx-data-docs/design.md for the two-pass model.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from pyspark.sql import DataFrame

logger = logging.getLogger(__name__)


class GxSuiteRunner:
    """Runs a GX suite over a Spark DataFrame and persists the result.

    Lazy-imports `great_expectations` so environments without the extra
    installed (the default) do not pay the ~200MB import cost.
    """

    def __init__(
        self,
        project_dir: str = "/opt/gx/",
        textfile_dir: str = "/opt/gx/textfile/",
        validations_retention_count: int = 100,
        validations_retention_seconds: int = 24 * 3600,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.textfile_dir = Path(textfile_dir)
        self.retention_count = validations_retention_count
        self.retention_seconds = validations_retention_seconds
        self._context: Any = None

    def _get_context(self) -> Any:
        if self._context is not None:
            return self._context
        import great_expectations as gx

        self._context = gx.get_context(context_root_dir=str(self.project_dir))
        return self._context

    def validate_and_persist(self, batch_df: DataFrame, table: str) -> None:
        """Validate `batch_df` against `{table}_suite`, persist result, and
        emit textfile metrics. Any failure is logged and swallowed."""
        try:
            self._validate_and_persist(batch_df, table)
        except Exception as exc:
            logger.warning(
                "gx-runner table=%s failed (non-fatal): %s", table, exc
            )

    def _validate_and_persist(self, batch_df: DataFrame, table: str) -> None:
        import datetime as _dt

        from great_expectations.core.run_identifier import RunIdentifier
        from great_expectations.data_context.types.resource_identifiers import (
            ExpectationSuiteIdentifier,
            ValidationResultIdentifier,
        )
        from great_expectations.dataset import SparkDFDataset

        suite_name = f"{table}_suite"
        context = self._get_context()
        suite = context.get_expectation_suite(suite_name)

        dataset = SparkDFDataset(batch_df)
        result = dataset.validate(expectation_suite=suite)

        now_ms = int(time.time() * 1000)
        run_id = RunIdentifier(
            run_name=f"{table}-{now_ms}",
            run_time=_dt.datetime.utcnow(),
        )
        key = ValidationResultIdentifier(
            expectation_suite_identifier=ExpectationSuiteIdentifier(suite_name),
            run_id=run_id,
            batch_identifier=str(now_ms),
        )
        context.validations_store.set(key=key, value=result)
        try:
            context.build_data_docs(site_names=["local_site"])
        except Exception as exc:
            logger.debug("data-docs rebuild skipped: %s", exc)

        self._write_textfile(table, suite_name, result)
        self._prune_validations(suite_name)

    def _write_textfile(self, table: str, suite_name: str, result: Any) -> None:
        """Write `gx.prom` for node-exporter to scrape. Atomic via rename."""
        self.textfile_dir.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        lines.append(
            "# HELP gx_suite_success_ratio Fraction of expectations that "
            "passed in the latest ValidationResult per suite."
        )
        lines.append("# TYPE gx_suite_success_ratio gauge")

        stats = getattr(result, "statistics", {}) or {}
        successful = stats.get("successful_expectations", 0)
        evaluated = stats.get("evaluated_expectations", 0) or 1
        suite_ratio = successful / evaluated
        lines.append(
            f'gx_suite_success_ratio{{table="{table}",'
            f'suite="{suite_name}"}} {suite_ratio:.6f}'
        )

        lines.append(
            "# HELP gx_expectation_success_ratio Latest per-expectation "
            "success ratio."
        )
        lines.append("# TYPE gx_expectation_success_ratio gauge")

        for exp_result in getattr(result, "results", []) or []:
            cfg = getattr(exp_result, "expectation_config", None)
            if cfg is None:
                continue
            etype = getattr(cfg, "expectation_type", "unknown")
            kwargs = getattr(cfg, "kwargs", {}) or {}
            column = kwargs.get("column", "")
            r = getattr(exp_result, "result", {}) or {}
            element_count = r.get("element_count") or 0
            unexpected_count = r.get("unexpected_count") or 0
            if element_count > 0:
                ratio = 1.0 - (unexpected_count / element_count)
            else:
                ratio = 1.0 if getattr(exp_result, "success", True) else 0.0
            lines.append(
                f'gx_expectation_success_ratio{{table="{table}",'
                f'expectation_type="{etype}",'
                f'column="{column}"}} {ratio:.6f}'
            )

        payload = "\n".join(lines) + "\n"
        target = self.textfile_dir / "gx.prom"
        tmp = target.with_suffix(".prom.tmp")
        tmp.write_text(payload)
        os.replace(tmp, target)

    def _prune_validations(self, suite_name: str) -> None:
        """Keep at most `retention_count` per suite AND drop entries older
        than `retention_seconds`. Best-effort — swallow errors."""
        try:
            root = self.project_dir / "uncommitted" / "validations" / suite_name
            if not root.exists():
                return
            files = sorted(root.rglob("*.json"), key=lambda p: p.stat().st_mtime)
            cutoff = time.time() - self.retention_seconds

            to_delete: list[Path] = [p for p in files if p.stat().st_mtime < cutoff]
            remaining = [p for p in files if p not in to_delete]
            if len(remaining) > self.retention_count:
                excess = len(remaining) - self.retention_count
                to_delete.extend(remaining[:excess])

            for p in to_delete:
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass
        except Exception as exc:
            logger.debug("prune skipped for %s: %s", suite_name, exc)
