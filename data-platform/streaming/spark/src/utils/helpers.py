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


def format_kafka_topic_name(database: str, schema: str, table: str) -> str:
    """
    Format Kafka topic name for CDC
    
    Args:
        database: Database name
        schema: Schema name
        table: Table name
        
    Returns:
        str: Formatted topic name
    """
    return f"{database}.{schema}.{table}"


def extract_table_name_from_topic(topic: str) -> str:
    """
    Extract table name from Kafka topic
    
    Args:
        topic: Kafka topic name (e.g., "pg.public.customers")
        
    Returns:
        str: Table name
    """
    parts = topic.split('.')
    return parts[-1] if parts else topic
