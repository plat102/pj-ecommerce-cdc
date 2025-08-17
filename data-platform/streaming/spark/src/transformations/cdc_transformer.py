"""
CDC data transformation functions
"""
from pyspark.sql import DataFrame
from pyspark.sql.functions import when, col, lit, regexp_extract
import logging

logger = logging.getLogger(__name__)


class CDCTransformer:
    """Transformer for CDC data to target format"""
    
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
            
            # Fields: From after for insert/update, null for delete
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.name"))
            .otherwise(lit(None)).alias("name"),
            
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.email"))
            .otherwise(lit(None)).alias("email"),
            
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
            
            # Fields: From after for insert/update, null for delete
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.name"))
            .otherwise(lit(None)).alias("name"),
            
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.email"))
            .otherwise(lit(None)).alias("email"),
            
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
    def transform_products_cdc_for_clickhouse(cdc_df: DataFrame) -> DataFrame:
        """
        Transform products CDC data for ClickHouse (production mode)
        
        Args:
            cdc_df: DataFrame with parsed CDC JSON
            
        Returns:
            DataFrame: Transformed DataFrame ready for ClickHouse
        """
        logger.info("🔄 Transforming products CDC data for ClickHouse...")
        
        return cdc_df.select(
            # ID: From after/before/key based on operation
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.id"))
            .when(col("value_json.op") == "d", col("value_json.before.id"))
            .otherwise(col("key_json.id")).alias("id"),
            
            # Fields: From after for insert/update, null for delete
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.name"))
            .otherwise(lit(None)).alias("name"),
            
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.price"))
            .otherwise(lit(None)).alias("price"),
            
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.created_at"))
            .otherwise(lit(None)).alias("created_at"),
            
            # _version: From ts_ms for ReplacingMergeTree
            col("value_json.ts_ms").alias("_version"),
            
            # _deleted: 0 for insert/update, 1 for delete
            when(col("value_json.op") == "d", lit(1))
            .otherwise(lit(0)).alias("_deleted")
        )
    
    @staticmethod
    def transform_products_cdc_for_debug(cdc_df: DataFrame) -> DataFrame:
        """
        Transform products CDC data for debug mode (includes operation column)
        
        Args:
            cdc_df: DataFrame with parsed CDC JSON
            
        Returns:
            DataFrame: Transformed DataFrame with operation column for debugging
        """
        logger.info("🔄 Transforming products CDC data for debug...")
        
        return cdc_df.select(
            # ID: From after/before/key based on operation
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.id"))
            .when(col("value_json.op") == "d", col("value_json.before.id"))
            .otherwise(col("key_json.id")).alias("id"),
            
            # Fields: From after for insert/update, null for delete
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.name"))
            .otherwise(lit(None)).alias("name"),
            
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.price"))
            .otherwise(lit(None)).alias("price"),
            
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
    def transform_orders_cdc_for_clickhouse(cdc_df: DataFrame) -> DataFrame:
        """
        Transform orders CDC data for ClickHouse (production mode)
        
        Args:
            cdc_df: DataFrame with parsed CDC JSON
            
        Returns:
            DataFrame: Transformed DataFrame ready for ClickHouse
        """
        logger.info("🔄 Transforming orders CDC data for ClickHouse...")
        
        return cdc_df.select(
            # ID: From after/before/key based on operation
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.id"))
            .when(col("value_json.op") == "d", col("value_json.before.id"))
            .otherwise(col("key_json.id")).alias("id"),
            
            # Fields: From after for insert/update, null for delete
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.customer_id"))
            .otherwise(lit(None)).alias("customer_id"),
            
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.product_id"))
            .otherwise(lit(None)).alias("product_id"),
            
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.quantity"))
            .otherwise(lit(None)).alias("quantity"),
            
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.order_time"))
            .otherwise(lit(None)).alias("order_time"),
            
            # _version: From ts_ms for ReplacingMergeTree
            col("value_json.ts_ms").alias("_version"),
            
            # _deleted: 0 for insert/update, 1 for delete
            when(col("value_json.op") == "d", lit(1))
            .otherwise(lit(0)).alias("_deleted")
        )
    
    @staticmethod
    def transform_orders_cdc_for_debug(cdc_df: DataFrame) -> DataFrame:
        """
        Transform orders CDC data for debug mode (includes operation column)
        
        Args:
            cdc_df: DataFrame with parsed CDC JSON
            
        Returns:
            DataFrame: Transformed DataFrame with operation column for debugging
        """
        logger.info("🔄 Transforming orders CDC data for debug...")
        
        return cdc_df.select(
            # ID: From after/before/key based on operation
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.id"))
            .when(col("value_json.op") == "d", col("value_json.before.id"))
            .otherwise(col("key_json.id")).alias("id"),
            
            # Fields: From after for insert/update, null for delete
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.customer_id"))
            .otherwise(lit(None)).alias("customer_id"),
            
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.product_id"))
            .otherwise(lit(None)).alias("product_id"),
            
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.quantity"))
            .otherwise(lit(None)).alias("quantity"),
            
            when(col("value_json.op").isin("c", "u", "r"), col("value_json.after.order_time"))
            .otherwise(lit(None)).alias("order_time"),
            
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
        
        return CDCTransformer.transform_customers_cdc_for_clickhouse(cdc_df)

    @staticmethod
    def transform_orders_cdc(cdc_df: DataFrame) -> DataFrame:
        """
        Transform orders CDC data to target format
        (Legacy method - use transform_orders_cdc_for_clickhouse or transform_orders_cdc_for_debug)
        
        Args:
            cdc_df: DataFrame with parsed CDC JSON
            
        Returns:
            DataFrame: Transformed DataFrame ready for target
        """
        logger.info("🔄 Transforming orders CDC data...")
        
        return CDCTransformer.transform_orders_cdc_for_clickhouse(cdc_df)
    
    @staticmethod
    def add_processing_metadata(df: DataFrame) -> DataFrame:
        """
        Add processing metadata to DataFrame
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame: DataFrame with processing metadata
        """
        from pyspark.sql.functions import current_timestamp, lit
        
        return (df
                .withColumn("processed_at", current_timestamp())
                .withColumn("processing_version", lit("1.0")))
    
    @staticmethod
    def filter_valid_records(df: DataFrame) -> DataFrame:
        """
        Filter out invalid or corrupt records
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame: Filtered DataFrame with valid records only
        """
        logger.info("🔍 Filtering valid records...")
        
        # Check if operation column exists (debug mode)
        has_operation_col = "operation" in df.columns
        
        if has_operation_col:
            return (df
                    .filter(col("id").isNotNull())
                    .filter(col("_version").isNotNull())
                    .filter(col("operation").isNotNull()))
        else:
            return (df
                    .filter(col("id").isNotNull())
                    .filter(col("_version").isNotNull()))
