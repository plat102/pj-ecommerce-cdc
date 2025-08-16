"""
Kafka message parsing and transformation functions
"""
from pyspark.sql import DataFrame
from pyspark.sql.functions import expr, col, from_json
from src.utils.helpers import decode_udf
import logging

logger = logging.getLogger(__name__)


class KafkaMessageParser:
    """Parser for Kafka CDC messages"""
    
    @staticmethod
    def parse_raw_message(kafka_stream: DataFrame) -> DataFrame:
        """
        Parse Kafka stream to extract key and value as strings
        
        Args:
            kafka_stream: Raw Kafka DataFrame stream
            
        Returns:
            DataFrame: Parsed DataFrame with key_str and value_str columns
        """
        logger.info("🔍 Parsing raw Kafka messages...")
        
        return (kafka_stream
                .withColumn('key_str', decode_udf(col("key")))
                .withColumn('value_str', expr('cast(value as string)')))
    
    @staticmethod
    def parse_json_structures(kafka_json_df: DataFrame, key_schema, value_schema) -> DataFrame:
        """
        Parse JSON strings to structured data using schemas
        
        Args:
            kafka_json_df: DataFrame with key_str and value_str columns
            key_schema: Schema for key JSON
            value_schema: Schema for value JSON
            
        Returns:
            DataFrame: DataFrame with parsed JSON structures
        """
        logger.info("🏗️ Parsing JSON structures...")
        
        return (kafka_json_df
                .withColumn("key_json", from_json(col("key_str"), key_schema))
                .withColumn('value_json', from_json(col('value_str'), value_schema))
                .drop('value', 'key', 'key_str', 'value_str'))  # Clean up raw columns
