"""Happy-path tests for CustomersCDCTransformer (ClickHouse mode).

The transformer expects a DataFrame with `key_json` and `value_json` struct
columns as produced by KafkaMessageParser.parse_json_structures. Rows are
built here from Python dicts against explicit schemas to keep the test
self-contained.
"""
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    IntegerType,
    LongType,
)

from src.transformations.customers_cdc_transformer import CustomersCDCTransformer


_AFTER = StructType([
    StructField("id", IntegerType()),
    StructField("name", StringType()),
    StructField("email", StringType()),
    StructField("created_at", StringType()),
])

_BEFORE = StructType([
    StructField("id", IntegerType()),
])

VALUE_SCHEMA = StructType([
    StructField("op", StringType()),
    StructField("ts_ms", LongType()),
    StructField("before", _BEFORE),
    StructField("after", _AFTER),
])

KEY_SCHEMA = StructType([StructField("id", IntegerType())])

FULL_SCHEMA = StructType([
    StructField("key_json", KEY_SCHEMA),
    StructField("value_json", VALUE_SCHEMA),
])


def test_customers_transform_create_populates_id_and_version(spark_session):
    row = (
        {"id": 1},
        ("c", 1_700_000_000_000, None, (1, "Alice", "alice@example.com", "2026-01-01")),
    )
    df = spark_session.createDataFrame([row], schema=FULL_SCHEMA)

    out = CustomersCDCTransformer.transform_customers_cdc_for_clickhouse(df).collect()[0]

    assert out["id"] == 1
    assert out["_version"] == 1_700_000_000_000
    assert out["_deleted"] == 0
    # Email + name are PII-transformed; assert non-null and not equal to raw
    assert out["email"] is not None and out["email"] != "alice@example.com"
    assert out["name"] is not None and out["name"] != "Alice"


def test_customers_transform_delete_sets_deleted_flag(spark_session):
    row = (
        {"id": 42},
        ("d", 1_700_000_000_500, (42,), None),
    )
    df = spark_session.createDataFrame([row], schema=FULL_SCHEMA)

    out = CustomersCDCTransformer.transform_customers_cdc_for_clickhouse(df).collect()[0]

    assert out["id"] == 42
    assert out["_deleted"] == 1
    assert out["_version"] == 1_700_000_000_500
    # Delete events NULL out PII fields
    assert out["name"] is None
    assert out["email"] is None
