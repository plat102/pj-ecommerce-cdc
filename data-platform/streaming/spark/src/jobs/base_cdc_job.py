
from typing import Callable
from pyspark.sql import DataFrame
from pyspark.sql.streaming import StreamingQuery
from src.jobs.base_streaming_job import BaseStreamingJob
from src.io.kafka_client import KafkaReader
from src.io.clickhouse_client import ClickHouseWriter
from src.common.logging import get_logger

logger = get_logger()

class BaseCDCJob(BaseStreamingJob):
    """Base class for CDC streaming jobs"""

    def __init__(self, config):
        super().__init__(config)
        self.kafka_reader: KafkaReader = None
        self.clickhouse_writer: ClickHouseWriter = None
        
    def create_spark_sessions(self):
        """Extend to init Kafka + ClickHouse"""
        spark = super().create_spark_session()
        self.kafka_reader = KafkaReader(spark, self.config.kafka.bootstrap_servers)
        self.clickhouse_writer = ClickHouseWriter(
            self.config.clickhouse.jdbc_url,
            self.config.clickhouse.connection_properties
        )
        return spark

    def read_kafka_stream(self, topic: str) -> DataFrame:
        logger.info(f"Reading Kafka stream from topic: {topic}")

        kafka_stream = (
            self.spark.readStream
            .format("kafka")
            .option("kafka.bootstrap.servers", self.config.kafka.bootstrap_servers)
            .option("subscribe", topic)
            .option('startingOffsets', 'latest')
            .load()
        )
        
        logger.info("✅ Kafka stream connected successfully.")
        return kafka_stream

    def start_streaming(self, process_func: Callable[[], DataFrame], table_name: str) -> StreamingQuery:
        """
        Starts a CDC (Change Data Capture) streaming job using Spark Structured Streaming.
        Args:
            process_func (Callable[[], DataFrame]): A function that returns a Spark DataFrame to be streamed.
            table_name (str): The name of the target table for writing streaming data.
        Returns:
            StreamingQuery: The active Spark StreamingQuery object.
        Behavior:
            - Initializes a Spark session if not already created.
            - If debug mode is enabled, streams data to the console.
            - Otherwise, streams data to ClickHouse using a batch writer function.
            - Sets checkpoint location and trigger interval based on configuration.
            - Stores the StreamingQuery instance for later reference.
        """
        if not self.spark:
            self.create_spark_session()
        logger.info("🚀 Starting CDC streaming job...")

        df = process_func()
        if self.config.debug_mode:
            query = (
                df.writeStream
                .format("console")
                .outputMode("append")
                .option("truncate", "false")
                .trigger(processingTime=self.config.trigger_interval)
                .start()
            )
        else:
            write_batch_func = self.clickhouse_writer.create_batch_writer_function(table_name)
            
            query = (
                df.writeStream
                .foreachBatch(write_batch_func)
                .option('checkpointLocation', f'{self.config.checkpoint_location}/{table_name}')
                .trigger(processingTime=self.config.trigger_interval)
                .start()
            )
        
        self.streaming_query = query
        logger.info("✅ Streaming job started successfully!")
        
        return query
