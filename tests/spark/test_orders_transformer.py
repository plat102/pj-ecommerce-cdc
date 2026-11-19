"""Happy-path tests for OrderCDCTransformer (ClickHouse mode)."""
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    IntegerType,
    LongType,
)

from src.transformations.order_cdc_transformer import OrderCDCTransformer


_AFTER = StructType([
    StructField("id", IntegerType()),
    StructField("customer_id", IntegerType()),
    StructField("product_id", IntegerType()),
    StructField("quantity", IntegerType()),
    StructField("order_time", StringType()),
])

_BEFORE = StructType([StructField("id", IntegerType())])

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


def test_orders_transform_create_populates_fields(spark_session):
    row = (
        {"id": 100},
        ("c", 1_700_000_000_000, None, (100, 1, 7, 3, "2026-01-01T12:00:00Z")),
    )
    df = spark_session.createDataFrame([row], schema=FULL_SCHEMA)

    out = OrderCDCTransformer.transform_for_clickhouse(df).collect()[0]

    assert out["id"] == 100
    assert out["customer_id"] == 1
    assert out["product_id"] == 7
    assert out["quantity"] == 3
    assert out["_version"] == 1_700_000_000_000
    assert out["_deleted"] == 0


def test_orders_transform_delete_sets_deleted_flag(spark_session):
    row = (
        {"id": 101},
        ("d", 1_700_000_000_500, (101,), None),
    )
    df = spark_session.createDataFrame([row], schema=FULL_SCHEMA)

    out = OrderCDCTransformer.transform_for_clickhouse(df).collect()[0]

    assert out["id"] == 101
    assert out["_deleted"] == 1
    assert out["_version"] == 1_700_000_000_500
    assert out["customer_id"] is None
