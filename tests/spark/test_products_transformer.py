"""Happy-path tests for ProductCDCTransformer (ClickHouse mode).

Products carry a base64-encoded Debezium DECIMAL in `after.price`; the
transformer decodes it with decode_decimal_udf via unbase64.
"""
import base64
from decimal import Decimal

from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    IntegerType,
    LongType,
)

from src.transformations.product_cdc_transformer import ProductCDCTransformer


def _encode_price(dec: Decimal, scale: int = 2) -> str:
    """Mirror Debezium's DECIMAL(x, scale) → base64 encoding."""
    unscaled = int(dec.scaleb(scale))
    n_bytes = max(1, (unscaled.bit_length() + 8) // 8)
    raw = unscaled.to_bytes(n_bytes, byteorder="big", signed=True)
    return base64.b64encode(raw).decode("ascii")


_AFTER = StructType([
    StructField("id", IntegerType()),
    StructField("name", StringType()),
    StructField("price", StringType()),
    StructField("created_at", StringType()),
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


def test_products_transform_create_decodes_price(spark_session):
    price_b64 = _encode_price(Decimal("19.99"))
    row = (
        {"id": 7},
        ("c", 1_700_000_000_000, None, (7, "Widget", price_b64, "2026-01-01")),
    )
    df = spark_session.createDataFrame([row], schema=FULL_SCHEMA)

    out = ProductCDCTransformer.transform_for_clickhouse(df).collect()[0]

    assert out["id"] == 7
    assert out["name"] == "Widget"
    assert out["price"] == Decimal("19.99")
    assert out["_version"] == 1_700_000_000_000
    assert out["_deleted"] == 0


def test_products_transform_delete_nulls_fields(spark_session):
    row = (
        {"id": 8},
        ("d", 1_700_000_000_900, (8,), None),
    )
    df = spark_session.createDataFrame([row], schema=FULL_SCHEMA)

    out = ProductCDCTransformer.transform_for_clickhouse(df).collect()[0]

    assert out["id"] == 8
    assert out["_deleted"] == 1
    assert out["_version"] == 1_700_000_000_900
    assert out["name"] is None
    assert out["price"] is None
