from pyspark.sql import DataFrame
from pyspark.sql.functions import col, when, lit
from src.common.logging import get_logger
from src.transformations.cdc_transformer import CDCTransformer

logger = get_logger(__name__)


class OrderCDCTransformer(CDCTransformer):
    @staticmethod
    def transform_for_clickhouse(transformed_df: DataFrame) -> DataFrame:
        """
        Transform orders CDC data for ClickHouse (production mode).
        """
        logger.info("🔄 Transforming orders CDC data for ClickHouse...")

        # On delete (op=d) source from `before` so non-nullable ClickHouse
        # columns still receive a value; otherwise `after`.
        return transformed_df.select(
            when(col("value_json.op") == "d", col("value_json.before.id"))
              .otherwise(col("value_json.after.id"))
              .alias("id"),
            when(col("value_json.op") == "d", col("value_json.before.customer_id"))
              .otherwise(col("value_json.after.customer_id"))
              .alias("customer_id"),
            when(col("value_json.op") == "d", col("value_json.before.product_id"))
              .otherwise(col("value_json.after.product_id"))
              .alias("product_id"),
            when(col("value_json.op") == "d", col("value_json.before.quantity"))
              .otherwise(col("value_json.after.quantity"))
              .alias("quantity"),
            when(col("value_json.op") == "d", col("value_json.before.order_time"))
              .otherwise(col("value_json.after.order_time"))
              .alias("order_time"),
            col("value_json.ts_ms").alias("_version"),
            when(col("value_json.op") == "d", lit(1)).otherwise(lit(0)).alias("_deleted"),
        )

    @staticmethod
    def transform_for_debug(transformed_df: DataFrame) -> DataFrame:
        """
        Transform orders CDC data for debugging (keeps op column).
        """
        logger.info("🔄 Transforming orders CDC data for debug...")

        return transformed_df.select(
            when(col("value_json.op") == "d", col("value_json.before.id"))
              .otherwise(col("value_json.after.id"))
              .alias("id"),
            when(col("value_json.op") == "d", col("value_json.before.customer_id"))
              .otherwise(col("value_json.after.customer_id"))
              .alias("customer_id"),
            when(col("value_json.op") == "d", col("value_json.before.product_id"))
              .otherwise(col("value_json.after.product_id"))
              .alias("product_id"),
            when(col("value_json.op") == "d", col("value_json.before.quantity"))
              .otherwise(col("value_json.after.quantity"))
              .alias("quantity"),
            when(col("value_json.op") == "d", col("value_json.before.order_time"))
              .otherwise(col("value_json.after.order_time"))
              .alias("order_time"),
            col("value_json.ts_ms").alias("_version"),
            when(col("value_json.op") == "d", lit(1)).otherwise(lit(0)).alias("_deleted"),
            col("value_json.op").alias("operation"),
        )

    @staticmethod
    def transform_cdc(transformed_df: DataFrame) -> DataFrame:
        """
        Alias for default transform (ClickHouse mode).
        """
        return OrderCDCTransformer.transform_for_clickhouse(transformed_df)
    