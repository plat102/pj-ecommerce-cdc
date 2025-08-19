from pyspark.sql import DataFrame
from pyspark.sql.functions import col, when, lit, unbase64
from src.common.logging import get_logger
from src.transformations.cdc_transformer import CDCTransformer
from src.utils.udfs import decode_decimal_udf

logger = get_logger(__name__)


class ProductCDCTransformer(CDCTransformer):
    @staticmethod
    def transform_for_clickhouse(cdc_df: DataFrame) -> DataFrame:
        """
        Transform products CDC data for ClickHouse (production mode).
        """
        logger.info("🔄 Transforming products CDC data for ClickHouse...")

        cdc_df = (
            cdc_df
            .withColumn("price_binary", unbase64(col("value_json.after.price")))
            .withColumn("price_decimal", decode_decimal_udf(col("price_binary")))
        )

        return cdc_df.select(
            # ID: after/before/key
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.id"))
              .when(col("value_json.op") == "d", col("value_json.before.id"))
              .otherwise(col("key_json.id")).alias("id"),

            # Fields
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.name"))
              .otherwise(lit(None)).alias("name"),

            when(col("value_json.op").isin("c", "u", "r"), col("price_decimal"))
              .otherwise(lit(None)).alias("price"),

            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.created_at"))
              .otherwise(lit(None)).alias("created_at"),

            # Version & delete flag
            col("value_json.ts_ms").alias("_version"),
            when(col("value_json.op") == "d", lit(1)).otherwise(lit(0)).alias("_deleted")
        )

    @staticmethod
    def transform_for_debug(cdc_df: DataFrame) -> DataFrame:
        """
        Transform products CDC data for debugging (keeps op column).
        """
        logger.info("🔄 Transforming products CDC data for debug...")

        cdc_df = (
            cdc_df
            .withColumn("price_binary", unbase64(col("value_json.after.price")))
            .withColumn("price_decimal", decode_decimal_udf(col("price_binary")))
        )

        return cdc_df.select(
            # ID: after/before/key
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.id"))
              .when(col("value_json.op") == "d", col("value_json.before.id"))
              .otherwise(col("key_json.id")).alias("id"),

            # Fields
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.name"))
              .otherwise(lit(None)).alias("name"),

            when(col("value_json.op").isin("c", "u", "r"), col("price_decimal"))
              .otherwise(lit(None)).alias("price"),

            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.created_at"))
              .otherwise(lit(None)).alias("created_at"),

            # Version & delete flag
            col("value_json.ts_ms").alias("_version"),
            when(col("value_json.op") == "d", lit(1)).otherwise(lit(0)).alias("_deleted"),

            # Operation type for debug
            col("value_json.op").alias("operation")
        )

    @staticmethod
    def transform_cdc(cdc_df: DataFrame) -> DataFrame:
        """
        Alias for default transform (ClickHouse mode).
        """
        return ProductCDCTransformer.transform_for_clickhouse(cdc_df)
