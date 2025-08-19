"""
Main CDC Processing Job
"""
import logging
from pyspark.sql import SparkSession
from pyspark.sql.streaming import StreamingQuery
from typing import Optional

from src.config.app_config import AppConfig
from src.schemas.cdc_schemas import CDCSchemas
from src.io.kafka_client import KafkaReader
from src.io.clickhouse_client import ClickHouseWriter
from src.transformations.kafka_parser import KafkaMessageParser
from src.transformations.cdc_transformer import CDCTransformer
from src.transformations.customers_cdc_transformer import CustomersCDCTransformer
from src.utils.helpers import validate_config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CDCProcessor:
    """Main CDC Processing Job"""
    
    def __init__(self, config: AppConfig):
        """
        Initialize CDC Processor
        
        Args:
            config: Application configuration
        """
        self.config = config
        self.spark: Optional[SparkSession] = None
        self.streaming_query: Optional[StreamingQuery] = None
        
        # Initialize clients
        self.kafka_reader: Optional[KafkaReader] = None
        self.clickhouse_writer: Optional[ClickHouseWriter] = None
        
        # Validate configuration
        validate_config(config)
        
    def create_spark_session(self) -> SparkSession:
        """Create and configure Spark session"""
        builder = SparkSession.builder.appName(self.config.spark.app_name)
        
        # Apply configurations
        for key, value in self.config.spark.get_spark_configs().items():
            builder = builder.config(key, value)
            
        if self.config.spark.master:
            builder = builder.master(self.config.spark.master)
            
        self.spark = builder.getOrCreate()
        
        # Initialize clients after Spark session is created
        self.kafka_reader = KafkaReader(self.spark, self.config.kafka.bootstrap_servers)
        self.clickhouse_writer = ClickHouseWriter(
            self.config.clickhouse.jdbc_url,
            self.config.clickhouse.connection_properties
        )
        
        logger.info(f"Created Spark session: {self.spark.sparkContext.applicationId}")
        return self.spark
    
    def read_kafka_stream(self, topic: str):
        """
        Read streaming data from Kafka
        
        Args:
            topic: Kafka topic name
            
        Returns:
            DataFrame: Kafka stream DataFrame
        """
        logger.info(f"Connecting to Kafka topic: {topic}")
        
        kafka_stream = (
            self.spark.readStream
            .format("kafka")
            .option("kafka.bootstrap.servers", self.config.kafka.bootstrap_servers)
            .option("subscribe", topic)
            .option("startingOffsets", "latest")
            .load()
        )
        
        logger.info("✅ Kafka stream connected successfully")
        return kafka_stream
    
    def process_customers_cdc(self):
        """Process customers CDC stream"""
        topic = self.config.kafka.topics["customers"]
        
        # Read Kafka stream
        kafka_stream = self.kafka_reader.read_stream(topic)
        
        # Parse Kafka messages
        kafka_json_df = KafkaMessageParser.parse_raw_message(kafka_stream)
        
        # Parse JSON using schemas
        schemas = CDCSchemas()
        cdc_df = KafkaMessageParser.parse_json_structures(
            kafka_json_df, 
            schemas.get_key_schema(), 
            schemas.get_customers_value_schema()
        )
        
        # Transform to target format based on mode
        if self.config.debug_mode:
            # Debug mode: include operation column for debugging
            transformed_df = CustomersCDCTransformer.transform_customers_cdc_for_debug(cdc_df)
            # Add processing metadata for debugging
            final_df = CustomersCDCTransformer.add_processing_metadata(transformed_df)
        else:
            # Production mode: exclude operation column for ClickHouse
            transformed_df = CustomersCDCTransformer.transform_customers_cdc_for_clickhouse(cdc_df)
            # No metadata in production mode - ClickHouse schema doesn't include processed_at
            final_df = transformed_df
        
        # Filter valid records
        final_df = CustomersCDCTransformer.filter_valid_records(final_df)
        
        return final_df
    
    def write_to_clickhouse(self, df, table_name: str):
        """
        Write DataFrame to ClickHouse
        
        Args:
            df: DataFrame to write
            table_name: Target table name
        """
        logger.info(f"Writing to ClickHouse table: {table_name}")
        
        try:
            (df.write
             .format("jdbc")
             .option("url", self.config.clickhouse.jdbc_url)
             .option("dbtable", table_name)
             .options(**self.config.clickhouse.connection_properties)
             .mode("append")
             .save())
             
            logger.info("✅ Data written to ClickHouse successfully!")
            
        except Exception as e:
            logger.error(f"❌ Error writing to ClickHouse: {e}")
            raise
    
    def start_streaming(self):
        """Start the streaming job"""
        if not self.spark:
            self.create_spark_session()
            
        logger.info("Starting CDC streaming job...")
        
        # Process customers CDC
        customers_df = self.process_customers_cdc()
        
        if self.config.debug_mode:
            # Debug mode: write to console
            logger.info("Debug mode: Writing to console")
            query = (customers_df.writeStream
                    .outputMode("append")
                    .format("console")
                    .option("truncate", False)
                    .trigger(processingTime=self.config.trigger_interval)
                    .start())
        else:
            # Production mode: write to ClickHouse
            write_batch_func = self.clickhouse_writer.create_batch_writer_function("customers_cdc")
            
            query = (customers_df.writeStream
                    .outputMode("append")
                    .foreachBatch(write_batch_func)
                    .option("checkpointLocation", f"{self.config.checkpoint_location}/customers")
                    .trigger(processingTime=self.config.trigger_interval)
                    .start())
        
        self.streaming_query = query
        logger.info("✅ Streaming job started successfully!")
        return query
    
    def stop_streaming(self):
        """Stop the streaming job gracefully"""
        if self.streaming_query:
            logger.info("Stopping streaming job...")
            self.streaming_query.stop()
            logger.info("✅ Streaming job stopped")
            
    def wait_for_termination(self):
        """Wait for streaming job to terminate"""
        if self.streaming_query:
            self.streaming_query.awaitTermination()


def main():
    """Main entry point"""
    config = AppConfig()
    processor = CDCProcessor(config)
    
    try:
        # Start streaming
        processor.start_streaming()
        
        # Wait for termination
        processor.wait_for_termination()
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Job failed with error: {e}")
        raise
    finally:
        processor.stop_streaming()
        if processor.spark:
            processor.spark.stop()


if __name__ == "__main__":
    main()
