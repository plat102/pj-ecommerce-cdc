"""
Customers CDC transformer
"""
import logging
from pyspark.sql import DataFrame
from pyspark.sql.functions import when, col, lit

from src.transformations.cdc_transformer import CDCTransformer
from src.utils.udfs import hash_pii_udf, tokenize_name_udf

logger = logging.getLogger(__name__)


def _mask_name(raw_name):
    return when(raw_name.isNull(), lit(None)).otherwise(tokenize_name_udf(raw_name))


def _mask_email(raw_email):
    return when(raw_email.isNull(), lit(None)).otherwise(hash_pii_udf(raw_email))


class CustomersCDCTransformer(CDCTransformer): # <domain><context><role>

    @staticmethod
    def transform_customers_cdc_for_clickhouse(cdc_df: DataFrame) -> DataFrame:
        """
        Transform customers CDC data for ClickHouse (production mode)

        Args:
            cdc_df: DataFrame with parsed CDC JSON

        Returns:
            DataFrame: Transformed DataFrame ready for ClickHouse
        """
        logger.info("🔄 Transforming customers CDC data for ClickHouse...")

        # On delete (op=d) sourced from `before`; PII masking still applies so
        # the tombstone row in ClickHouse never carries plaintext identity.
        return cdc_df.select(
            when(col("value_json.op") == "d", col("value_json.before.id"))
              .otherwise(col("value_json.after.id"))
              .alias("id"),

            _mask_name(
                when(col("value_json.op") == "d", col("value_json.before.name"))
                  .otherwise(col("value_json.after.name"))
            ).alias("name"),

            _mask_email(
                when(col("value_json.op") == "d", col("value_json.before.email"))
                  .otherwise(col("value_json.after.email"))
            ).alias("email"),

            when(col("value_json.op") == "d", col("value_json.before.created_at"))
              .otherwise(col("value_json.after.created_at"))
              .alias("created_at"),

            col("value_json.ts_ms").alias("_version"),
            when(col("value_json.op") == "d", lit(1)).otherwise(lit(0)).alias("_deleted"),
        )

    @staticmethod
    def transform_customers_cdc_for_debug(cdc_df: DataFrame) -> DataFrame:
        """
        Transform customers CDC data for debug mode (includes operation column)

        Args:
            cdc_df: DataFrame with parsed CDC JSON

        Returns:
            DataFrame: Transformed DataFrame with operation column for debugging
        """
        logger.info("🔄 Transforming customers CDC data for debug...")

        # Debug output — PII still masked so console never leaks plaintext.
        return cdc_df.select(
            when(col("value_json.op") == "d", col("value_json.before.id"))
              .otherwise(col("value_json.after.id"))
              .alias("id"),

            _mask_name(
                when(col("value_json.op") == "d", col("value_json.before.name"))
                  .otherwise(col("value_json.after.name"))
            ).alias("name"),

            _mask_email(
                when(col("value_json.op") == "d", col("value_json.before.email"))
                  .otherwise(col("value_json.after.email"))
            ).alias("email"),

            when(col("value_json.op") == "d", col("value_json.before.created_at"))
              .otherwise(col("value_json.after.created_at"))
              .alias("created_at"),

            col("value_json.ts_ms").alias("_version"),
            when(col("value_json.op") == "d", lit(1)).otherwise(lit(0)).alias("_deleted"),
            col("value_json.op").alias("operation"),
        )
    
    @staticmethod
    def transform_customers_cdc(cdc_df: DataFrame) -> DataFrame:
        """
        Transform customers CDC data to target format with versioning
        (Legacy method - use transform_customers_cdc_for_clickhouse or transform_customers_cdc_for_debug)
        
        Args:
            cdc_df: DataFrame with parsed CDC JSON
            
        Returns:
            DataFrame: Transformed DataFrame ready for target
        """
        logger.info("🔄 Transforming customers CDC data...")
        
        return CustomersCDCTransformer.transform_customers_cdc_for_clickhouse(cdc_df)
    