"""Session-scoped SparkSession fixture and sample Kafka payload helpers.

The SparkSession takes ~3-7s to start; scope="session" reuses it across
every test in the run. Filter with `pytest -k <name>` if a subset is needed.
"""
import pytest
from pyspark.sql import SparkSession


@pytest.fixture(scope="session")
def spark_session() -> SparkSession:
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
