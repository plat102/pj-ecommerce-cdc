"""
Pure utility functions for data processing
"""
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType


def decode_bytes(bytes_array):
    """
    Decode byte array to UTF-8 string
    
    Args:
        bytes_array: Byte array from Kafka message
        
    Returns:
        str: Decoded string or None if decoding fails
    """
    if bytes_array is not None:
        try:
            return bytes(bytes_array).decode('utf-8')
        except Exception:
            return None
    return None


# Create UDF for decoding
decode_udf = udf(decode_bytes, StringType())


def validate_config(config):
    """
    Validate application configuration
    
    Args:
        config: Application configuration object
        
    Raises:
        ValueError: If configuration is invalid
    """
    if not config.kafka.bootstrap_servers:
        raise ValueError("Kafka bootstrap servers must be specified")
    
    if not config.clickhouse.jdbc_url:
        raise ValueError("ClickHouse JDBC URL must be specified")
    
    if not config.spark.app_name:
        raise ValueError("Spark application name must be specified")


def safe_cast(value, target_type, default=None):
    """
    Safely cast value to target type
    
    Args:
        value: Value to cast
        target_type: Target type (int, float, str, etc.)
        default: Default value if casting fails
        
    Returns:
        Casted value or default
    """
    try:
        return target_type(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def parse_kafka_message(kafka_stream):
    """
    Parse Kafka stream to extract key and value as strings
    
    Args:
        kafka_stream: Kafka DataFrame stream
        
    Returns:
        DataFrame: Parsed DataFrame with key_str and value_str columns
    """
    from pyspark.sql.functions import expr
    
    return (kafka_stream
            .withColumn('key_str', decode_udf(col("key")))
            .withColumn('value_str', expr('cast(value as string)')))


def parse_cdc_json(kafka_json_df, key_schema, value_schema):
    """
    Parse JSON strings to structured data using schemas
    
    Args:
        kafka_json_df: DataFrame with key_str and value_str columns
        key_schema: Schema for key JSON
        value_schema: Schema for value JSON
        
    Returns:
        DataFrame: DataFrame with parsed JSON structures
    """
    return (kafka_json_df
            .withColumn("key_json", from_json(col("key_str"), key_schema))
            .withColumn('value_json', from_json(col('value_str'), value_schema))
            .drop('value', 'key'))


def transform_cdc_to_target(cdc_df):
    """
    Transform CDC data to target format with versioning
    
    Args:
        cdc_df: DataFrame with parsed CDC JSON
        
    Returns:
        DataFrame: Transformed DataFrame ready for target
    """
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
