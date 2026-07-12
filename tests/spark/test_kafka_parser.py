"""Happy-path tests for KafkaMessageParser.

parse_raw_message decodes key bytes and casts value to string; parse_json_structures
parses key/value JSON with provided schemas and drops raw columns.
"""
import json

from pyspark.sql.functions import lit
from pyspark.sql.types import StructType, StructField, StringType, LongType, IntegerType

from src.transformations.kafka_parser import KafkaMessageParser


KEY_SCHEMA = StructType([StructField("id", IntegerType())])
VALUE_SCHEMA = StructType([
    StructField("op", StringType()),
    StructField("ts_ms", LongType()),
    StructField("after", StructType([
        StructField("id", IntegerType()),
        StructField("name", StringType()),
    ])),
])


def _make_json_df(spark_session, payload_json: str, key_json: str = '{"id":1}'):
    return (
        spark_session.createDataFrame(
            [(key_json, payload_json)],
            schema=["key_str", "value_str"],
        )
        .withColumn("key", lit(None))
        .withColumn("value", lit(None))
    )


def test_parse_raw_message_creates_string_columns(spark_session):
    df = spark_session.createDataFrame(
        [(bytearray(b'{"id":1}'), bytearray(b'{"op":"c"}'))],
        schema=["key", "value"],
    )
    parsed = KafkaMessageParser.parse_raw_message(df).collect()
    assert parsed[0]["key_str"] == '{"id":1}'
    assert parsed[0]["value_str"] == '{"op":"c"}'


def test_parse_json_structures_op_create(spark_session):
    payload = {
        "op": "c",
        "ts_ms": 1_700_000_000_000,
        "after": {"id": 1, "name": "Alice"},
    }
    df = _make_json_df(spark_session, json.dumps(payload))
    parsed = KafkaMessageParser.parse_json_structures(df, KEY_SCHEMA, VALUE_SCHEMA).collect()
    row = parsed[0]
    assert row["value_json"]["op"] == "c"
    assert row["value_json"]["after"]["id"] == 1
    assert row["value_json"]["after"]["name"] == "Alice"
    assert row["key_json"]["id"] == 1


def test_parse_json_structures_op_delete(spark_session):
    payload = {
        "op": "d",
        "ts_ms": 1_700_000_000_500,
        "after": None,
    }
    df = _make_json_df(spark_session, json.dumps(payload))
    parsed = KafkaMessageParser.parse_json_structures(df, KEY_SCHEMA, VALUE_SCHEMA).collect()
    row = parsed[0]
    assert row["value_json"]["op"] == "d"
    assert row["value_json"]["after"] is None
