"""Tests for the GX second-pass runner.

These are pure-Python tests: `GxSuiteRunner` interacts with GX (mocked)
and the filesystem (real tmp_path). No Spark session is required — the
DataFrame is opaque to the runner and passed straight to `SparkDFDataset`,
which we mock.
"""
from __future__ import annotations

import sys
import time
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _stub_great_expectations(monkeypatch, dataset_validate_result):
    """Install a minimal `great_expectations` stub so lazy imports succeed.

    Returns (context_mock, dataset_class_mock) for assertions.
    """
    gx_pkg = types.ModuleType("great_expectations")
    core_pkg = types.ModuleType("great_expectations.core")
    run_id_mod = types.ModuleType("great_expectations.core.run_identifier")
    dc_pkg = types.ModuleType("great_expectations.data_context")
    dc_types_pkg = types.ModuleType("great_expectations.data_context.types")
    resource_ids_mod = types.ModuleType(
        "great_expectations.data_context.types.resource_identifiers"
    )
    dataset_mod = types.ModuleType("great_expectations.dataset")

    context = MagicMock(name="gx_context")
    context.validations_store = MagicMock()
    context.validations_store.set = MagicMock()
    context.get_expectation_suite = MagicMock(return_value=MagicMock())
    context.build_data_docs = MagicMock()
    gx_pkg.get_context = MagicMock(return_value=context)

    dataset_class = MagicMock(name="SparkDFDataset")
    dataset_instance = MagicMock()
    dataset_instance.validate = MagicMock(return_value=dataset_validate_result)
    dataset_class.return_value = dataset_instance
    dataset_mod.SparkDFDataset = dataset_class

    run_id_mod.RunIdentifier = MagicMock(name="RunIdentifier")
    resource_ids_mod.ValidationResultIdentifier = MagicMock(
        name="ValidationResultIdentifier"
    )
    resource_ids_mod.ExpectationSuiteIdentifier = MagicMock(
        name="ExpectationSuiteIdentifier"
    )

    monkeypatch.setitem(sys.modules, "great_expectations", gx_pkg)
    monkeypatch.setitem(sys.modules, "great_expectations.core", core_pkg)
    monkeypatch.setitem(
        sys.modules, "great_expectations.core.run_identifier", run_id_mod
    )
    monkeypatch.setitem(sys.modules, "great_expectations.data_context", dc_pkg)
    monkeypatch.setitem(
        sys.modules, "great_expectations.data_context.types", dc_types_pkg
    )
    monkeypatch.setitem(
        sys.modules,
        "great_expectations.data_context.types.resource_identifiers",
        resource_ids_mod,
    )
    monkeypatch.setitem(sys.modules, "great_expectations.dataset", dataset_mod)

    return context, dataset_class


def _fake_validation_result(*, evaluated: int, successful: int, per_exp):
    """Build a duck-typed object shaped like GX's ExpectationSuiteValidationResult."""
    result = types.SimpleNamespace()
    result.statistics = {
        "evaluated_expectations": evaluated,
        "successful_expectations": successful,
    }
    result.results = []
    for etype, column, element_count, unexpected_count in per_exp:
        exp = types.SimpleNamespace()
        exp.expectation_config = types.SimpleNamespace(
            expectation_type=etype, kwargs={"column": column}
        )
        exp.result = {
            "element_count": element_count,
            "unexpected_count": unexpected_count,
        }
        exp.success = unexpected_count == 0
        result.results.append(exp)
    return result


def test_textfile_metrics_written_and_labels_correct(tmp_path, monkeypatch):
    from src.governance.gx_runner import GxSuiteRunner

    validation = _fake_validation_result(
        evaluated=3,
        successful=2,
        per_exp=[
            ("expect_column_values_to_not_be_null", "id", 100, 0),
            ("expect_column_values_to_be_between", "price", 100, 18),
            ("expect_column_values_to_be_in_set", "_deleted", 100, 0),
        ],
    )
    _stub_great_expectations(monkeypatch, validation)

    runner = GxSuiteRunner(
        project_dir=str(tmp_path),
        textfile_dir=str(tmp_path / "textfile"),
    )
    runner.validate_and_persist(MagicMock(name="batch_df"), table="products")

    prom = (tmp_path / "textfile" / "gx.prom").read_text()
    assert 'gx_suite_success_ratio{table="products",suite="products_suite"} 0.666667' in prom
    assert (
        'gx_expectation_success_ratio{table="products",'
        'expectation_type="expect_column_values_to_not_be_null",'
        'column="id"} 1.000000'
    ) in prom
    assert (
        'gx_expectation_success_ratio{table="products",'
        'expectation_type="expect_column_values_to_be_between",'
        'column="price"} 0.820000'
    ) in prom


def test_runner_swallows_gx_errors(tmp_path, monkeypatch, caplog):
    """A failure inside the GX code path never re-raises."""
    from src.governance.gx_runner import GxSuiteRunner

    validation = _fake_validation_result(
        evaluated=1, successful=1, per_exp=[("expect_column_to_exist", "id", 0, 0)]
    )
    context, _ = _stub_great_expectations(monkeypatch, validation)
    context.get_expectation_suite.side_effect = RuntimeError("boom")

    runner = GxSuiteRunner(
        project_dir=str(tmp_path), textfile_dir=str(tmp_path / "textfile")
    )
    # Must not raise:
    runner.validate_and_persist(MagicMock(), table="products")


def test_pruning_keeps_at_most_retention_count(tmp_path, monkeypatch):
    from src.governance.gx_runner import GxSuiteRunner

    suite_dir = tmp_path / "uncommitted" / "validations" / "products_suite"
    suite_dir.mkdir(parents=True)

    # Seed 150 fresh validation files.
    for i in range(150):
        p = suite_dir / f"v{i:03d}.json"
        p.write_text("{}")
        # Stagger mtimes so pruning is deterministic (oldest first).
        os.utime(p, (time.time() - (150 - i), time.time() - (150 - i)))

    validation = _fake_validation_result(
        evaluated=1, successful=1, per_exp=[("expect_column_to_exist", "id", 0, 0)]
    )
    _stub_great_expectations(monkeypatch, validation)

    runner = GxSuiteRunner(
        project_dir=str(tmp_path),
        textfile_dir=str(tmp_path / "textfile"),
        validations_retention_count=100,
        validations_retention_seconds=24 * 3600,
    )
    runner.validate_and_persist(MagicMock(), table="products")

    remaining = sorted(suite_dir.glob("*.json"))
    assert len(remaining) == 100
    # Newest 100 kept — v050..v149.
    names = {p.name for p in remaining}
    assert "v149.json" in names
    assert "v050.json" in names
    assert "v049.json" not in names


import os  # noqa: E402  (used only by the pruning test above)
