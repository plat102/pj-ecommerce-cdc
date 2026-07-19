from pyspark.sql import DataFrame
from pyspark.sql.functions import col, when, lit
from src.common.logging import get_logger
from src.transformations.cdc_transformer import CDCTransformer

logger = get_logger(__name__)


class ProductCDCTransformer(CDCTransformer):
    @staticmethod
    def transform_for_clickhouse(cdc_df: DataFrame) -> DataFrame:
        """
        Transform products CDC data for ClickHouse (production mode).

        With the Apicurio Avro converter, `from_avro` already decodes the
        `price` field's Debezium `Decimal` logical type into Spark DecimalType,
        so the legacy `unbase64 + decode_decimal_udf` pass is no longer needed.
        """
        logger.info("Transforming products CDC data for ClickHouse (Avro path)")

        # On delete events (op=d), `after` is null; source the row from
        # `before` so non-nullable ClickHouse columns still receive a value.
        # Non-delete events use `after`. Key is a last-resort fallback.
        return cdc_df.select(
            when(col("value_json.op") == "d", col("value_json.before.id"))
              .otherwise(col("value_json.after.id"))
              .alias("id"),
            when(col("value_json.op") == "d", col("value_json.before.name"))
              .otherwise(col("value_json.after.name"))
              .alias("name"),
            when(col("value_json.op") == "d", col("value_json.before.price"))
              .otherwise(col("value_json.after.price"))
              .alias("price"),
            when(col("value_json.op") == "d", col("value_json.before.created_at"))
              .otherwise(col("value_json.after.created_at"))
              .alias("created_at"),
            col("value_json.ts_ms").alias("_version"),
            when(col("value_json.op") == "d", lit(1)).otherwise(lit(0)).alias("_deleted"),
        )

    @staticmethod
    def transform_for_debug(cdc_df: DataFrame) -> DataFrame:
        """Debug output: keeps the `operation` column visible on the console sink."""
        logger.info("Transforming products CDC data for debug (Avro path)")

        return cdc_df.select(
            when(col("value_json.op") == "d", col("value_json.before.id"))
              .otherwise(col("value_json.after.id"))
              .alias("id"),
            when(col("value_json.op") == "d", col("value_json.before.name"))
              .otherwise(col("value_json.after.name"))
              .alias("name"),
            when(col("value_json.op") == "d", col("value_json.before.price"))
              .otherwise(col("value_json.after.price"))
              .alias("price"),
            when(col("value_json.op") == "d", col("value_json.before.created_at"))
              .otherwise(col("value_json.after.created_at"))
              .alias("created_at"),
            col("value_json.ts_ms").alias("_version"),
            when(col("value_json.op") == "d", lit(1)).otherwise(lit(0)).alias("_deleted"),
            col("value_json.op").alias("operation"),
        )

    @staticmethod
    def transform_cdc(cdc_df: DataFrame) -> DataFrame:
        """
        Alias for default transform (ClickHouse mode).
        """
        return ProductCDCTransformer.transform_for_clickhouse(cdc_df)
