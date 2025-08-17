"""
Common Kafka operations for CDC processing
"""
from pyspark.sql import DataFrame
from pyspark.sql.functions import expr, col
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class KafkaReader:
    """Kafka stream reader with common operations"""
    
    def __init__(self, spark_session, bootstrap_servers: str):
        """
        Initialize Kafka reader
        
        Args:
            spark_session: Spark session
            bootstrap_servers: Kafka bootstrap servers
        """
        self.spark = spark_session
        self.bootstrap_servers = bootstrap_servers
        
    def read_stream(self, topic: str, starting_offsets: str = "latest") -> DataFrame:
        """
        Read streaming data from Kafka topic
        
        Args:
            topic: Kafka topic name
            starting_offsets: Starting offset position
            
        Returns:
            DataFrame: Raw Kafka stream DataFrame
        """
        logger.info(f"🔗 Connecting to Kafka topic: {topic}")
        
        kafka_stream = (
            self.spark.readStream
            .format("kafka")
            .option("kafka.bootstrap.servers", self.bootstrap_servers)
            .option("subscribe", topic)
            .option("startingOffsets", starting_offsets)
            .load()
        )
        
        logger.info("✅ Kafka stream connected successfully")
        return kafka_stream
    
    def read_batch(self, topic: str, starting_offsets: str = "earliest") -> DataFrame:
        """
        Read batch data from Kafka topic
        
        Args:
            topic: Kafka topic name
            starting_offsets: Starting offset position
            
        Returns:
            DataFrame: Kafka batch DataFrame
        """
        logger.info(f"📊 Reading batch from Kafka topic: {topic}")
        
        kafka_df = (
            self.spark.read
            .format("kafka")
            .option("kafka.bootstrap.servers", self.bootstrap_servers)
            .option("subscribe", topic)
            .option("startingOffsets", starting_offsets)
            .load()
        )
        
        return kafka_df
