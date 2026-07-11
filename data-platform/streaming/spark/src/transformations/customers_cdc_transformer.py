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

        return cdc_df.select(
            # ID: From after/before/key based on operation
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.id"))
            .when(col("value_json.op") == "d", col("value_json.before.id"))
            .otherwise(col("key_json.id")).alias("id"),

            # name: tokenized before landing in ClickHouse (see openspec
            # data-governance Pillar 3). Delete events emit null.
            when(
                col("value_json.op").isin("c", "u", "r"),
                _mask_name(col("value_json.after.name")),
            ).otherwise(lit(None)).alias("name"),

            # email: SHA-256(email, PII_SALT). Deterministic so joins by
            # hashed email still work across systems.
            when(
                col("value_json.op").isin("c", "u", "r"),
                _mask_email(col("value_json.after.email")),
            ).otherwise(lit(None)).alias("email"),

            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.created_at"))
            .otherwise(lit(None)).alias("created_at"),

            # _version: From ts_ms for ReplacingMergeTree
            col("value_json.ts_ms").alias("_version"),

            # _deleted: 0 for insert/update, 1 for delete
            when(col("value_json.op") == "d", lit(1))
            .otherwise(lit(0)).alias("_deleted")
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

        return cdc_df.select(
            # ID: From after/before/key based on operation
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.id"))
            .when(col("value_json.op") == "d", col("value_json.before.id"))
            .otherwise(col("key_json.id")).alias("id"),

            # Debug mode also masks PII so console logs never contain
            # plaintext values.
            when(
                col("value_json.op").isin("c", "u", "r"),
                _mask_name(col("value_json.after.name")),
            ).otherwise(lit(None)).alias("name"),

            when(
                col("value_json.op").isin("c", "u", "r"),
                _mask_email(col("value_json.after.email")),
            ).otherwise(lit(None)).alias("email"),

            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.created_at"))
            .otherwise(lit(None)).alias("created_at"),

            # _version: From ts_ms for ReplacingMergeTree
            col("value_json.ts_ms").alias("_version"),

            # _deleted: 0 for insert/update, 1 for delete
            when(col("value_json.op") == "d", lit(1))
            .otherwise(lit(0)).alias("_deleted"),

            # Operation type for debugging
            col("value_json.op").alias("operation")
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
    