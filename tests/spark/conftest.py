"""Session-scoped SparkSession fixture and sample Kafka payload helpers.

The SparkSession takes ~3-7s to start; scope="session" reuses it across
every test in the run. Filter with `pytest -k <name>` if a subset is needed.

PySpark 3.3.0 requires Java 8/11/17. On JDK 21+ (e.g. host with Java 23),
Spark fails at JVM init because java.nio.DirectByteBuffer.<init>(long,int)
was removed. Whole spark/ dir is skipped in that case so CI/dev on Java 17
still runs it while a modern host box stays green.
"""
import os
import re
import subprocess

import pytest


def _java_major_version() -> int | None:
    java_home = os.environ.get("JAVA_HOME")
    java_bin = f"{java_home}/bin/java" if java_home else "java"
    try:
        out = subprocess.run(
            [java_bin, "-version"], capture_output=True, text=True, check=True
        ).stderr
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    match = re.search(r'version "(\d+)', out)
    return int(match.group(1)) if match else None


_JAVA_VERSION = _java_major_version()
_JAVA_OK = _JAVA_VERSION is not None and _JAVA_VERSION <= 17


def pytest_collection_modifyitems(config, items):
    """Skip only tests that consume the `spark_session` fixture. Pure-Python
    UDF tests in test_udfs.py have no Spark dependency and stay collected."""
    if _JAVA_OK:
        return
    reason = f"Spark 3.3.0 needs JDK <=17; detected {_JAVA_VERSION}"
    skip_marker = pytest.mark.skip(reason=reason)
    for item in items:
        if "spark_session" in getattr(item, "fixturenames", ()):
            item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def spark_session():
    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.master("local[*]")
        .appName("ecommerce-cdc-unit-tests")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.showConsoleProgress", "false")
        .getOrCreate()
    )
    yield spark
    spark.stop()


@pytest.fixture
def debezium_create_payload():
    """Minimal Debezium `op=c` envelope payload for a customers row."""
    return {
        "op": "c",
        "ts_ms": 1_700_000_000_000,
        "before": None,
        "after": {"id": 1, "email": "a@b.c", "name": "Alice"},
    }


@pytest.fixture
def debezium_delete_payload():
    """Minimal Debezium `op=d` envelope payload for a customers row."""
    return {
        "op": "d",
        "ts_ms": 1_700_000_000_500,
        "before": {"id": 1, "email": "a@b.c", "name": "Alice"},
        "after": None,
    }
