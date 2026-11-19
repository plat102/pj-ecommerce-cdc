"""
Kafka message parsing and transformation functions.

Two parse paths are supported:

1. Legacy JSON — pre-Phase-3 producer wrote JSON envelopes; kept for tests
   and for any local run pinned to the old converter.
2. Avro — post-Phase-3 producer uses Apicurio's Confluent-compatible wire
   format (`[0x00][4-byte contentId][Avro body]`). We strip the 5-byte
   header, then Spark's `from_avro` decodes the body against the schema
   fetched from the registry at job startup.
"""
import logging

from pyspark.sql import DataFrame
from pyspark.sql.avro.functions import from_avro
from pyspark.sql.functions import col, expr, from_json

from src.utils.helpers import decode_udf

logger = logging.getLogger(__name__)


class KafkaMessageParser:
    """Parser for Kafka CDC messages."""

    @staticmethod
    def parse_raw_message(kafka_stream: DataFrame) -> DataFrame:
        """Decode raw Kafka bytes into string columns (legacy JSON path)."""
        logger.info("Parsing raw Kafka messages (JSON path)")
        return (
            kafka_stream.withColumn("key_str", decode_udf(col("key")))
            .withColumn("value_str", expr("cast(value as string)"))
        )

    @staticmethod
    def parse_json_structures(kafka_json_df: DataFrame, key_schema, value_schema) -> DataFrame:
        """Parse JSON strings into structured columns using Spark StructTypes (legacy)."""
        logger.info("Parsing JSON structures")
        return (
            kafka_json_df.withColumn("key_json", from_json(col("key_str"), key_schema))
            .withColumn("value_json", from_json(col("value_str"), value_schema))
            .drop("value", "key", "key_str", "value_str")
        )

    @staticmethod
    def parse_avro_message(
        kafka_stream: DataFrame,
        key_avro_schema: str,
        value_avro_schema: str,
    ) -> DataFrame:
        """Decode Apicurio/Confluent-shape Avro key + value into structured columns.

        The 5-byte magic prefix (`[0x00][contentId:int32]`) is stripped with
        `substring(col, 6, ...)` before `from_avro` is applied. The output
        DataFrame carries `key_json` and `value_json` columns so callers
        downstream do not need to know whether the source was JSON or Avro.
        """
        logger.info("Parsing Avro messages (Apicurio/Confluent wire format)")
        return (
            kafka_stream
            # Strip the 5-byte Confluent-shape header, then Avro-decode.
            .withColumn("_key_body", expr("substring(key, 6, length(key) - 5)"))
            .withColumn("_value_body", expr("substring(value, 6, length(value) - 5)"))
            .withColumn("key_json", from_avro(col("_key_body"), key_avro_schema))
            .withColumn("value_json", from_avro(col("_value_body"), value_avro_schema))
            .drop("value", "key", "_key_body", "_value_body")
        )
