"""
Orders CDC Job for Spark Streaming
Processes CDC events from Kafka and writes to ClickHouse or console
"""
import logging
from typing import Optional
from pyspark.sql import SparkSession
from pyspark.sql.streaming import StreamingQuery

from src.config.app_config import AppConfig
from src.common.kafka_client import KafkaReader
from src.common.clickhouse_client import ClickHouseWriter
from src.transformations.kafka_parser import KafkaMessageParser
from src.transformations.cdc_transformer import CDCTransformer
from src.schemas.cdc_schemas import CDCSchemas

logger = logging.getLogger(__name__)


class OrdersCDCJob:
    """Orders CDC streaming job"""
    
    def __init__(self, config: AppConfig):
        """
        Initialize CDC job
        
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
        # validate_config(config)  # Remove validation for now
        
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
    
    def create_processed_stream(self):
        """Create processed stream with transformations"""
        # Read from Kafka
        kafka_df = self.kafka_reader.read_stream("pg.public.orders")
        
        # Parse JSON messages
        kafka_json_df = KafkaMessageParser.parse_raw_message(kafka_df)
        
        # Parse JSON using schemas
        schemas = CDCSchemas()
        cdc_df = KafkaMessageParser.parse_json_structures(
            kafka_json_df, 
            schemas.get_key_schema(), 
            schemas.get_orders_value_schema()
        )
        
        # Transform to target format based on mode
        if self.config.debug_mode:
            # Debug mode: include operation column for debugging
            transformed_df = CDCTransformer.transform_orders_cdc_for_debug(cdc_df)
            # Add processing metadata for debugging
            final_df = CDCTransformer.add_processing_metadata(transformed_df)
        else:
            # Production mode: exclude operation column for ClickHouse
            transformed_df = CDCTransformer.transform_orders_cdc_for_clickhouse(cdc_df)
            # No metadata in production mode - ClickHouse schema doesn't include processed_at
            final_df = transformed_df
        
        # Filter valid records
        final_df = CDCTransformer.filter_valid_records(final_df)
        
        return final_df
    
    def write_to_clickhouse(self, df, table_name: str):
        """
        Write DataFrame to ClickHouse
        
        Args:
            df: DataFrame to write
            table_name: Target table name
        """
        logger.info(f"Writing to ClickHouse table: {table_name}")
        self.clickhouse_writer.write_batch(df, table_name)
    
    def write_to_console(self, df):
        """
        Write DataFrame to console for debugging
        
        Args:
            df: DataFrame to write
        """
        logger.info("Writing to console for debugging...")
        return (df.writeStream
                .outputMode("append")
                .format("console")
                .option("truncate", "false")
                .option("numRows", 50))
    
    def start_streaming(self):
        """Start the streaming job"""
        logger.info("Starting CDC streaming job...")
        
        # Create processed stream
        processed_df = self.create_processed_stream()
        
        if self.config.debug_mode:
            # Debug mode: write to console
            self.streaming_query = (self.write_to_console(processed_df)
                                   .trigger(processingTime="10 seconds")
                                   .option("checkpointLocation", "/tmp/spark-checkpoints/orders-debug")
                                   .start())
        else:
            # Production mode: write to ClickHouse using foreachBatch
            batch_writer = self.clickhouse_writer.create_batch_writer_function("orders_cdc")
            self.streaming_query = (processed_df.writeStream
                                   .outputMode("append")
                                   .foreachBatch(batch_writer)
                                   .trigger(processingTime="10 seconds")
                                   .option("checkpointLocation", "/tmp/spark-checkpoints/orders")
                                   .start())
        
        logger.info("✅ Streaming job started successfully!")
        return self.streaming_query
    
    def stop_streaming(self):
        """Stop the streaming job"""
        if self.streaming_query and self.streaming_query.isActive:
            logger.info("Stopping streaming job...")
            self.streaming_query.stop()
            logger.info("✅ Streaming job stopped")
    
    def run(self):
        """Main entry point for running the CDC job"""
        try:
            logger.info("Starting orders CDC job...")
            logger.info(f"Debug mode: {self.config.debug_mode}")
            logger.info(f"Kafka servers: {self.config.kafka.bootstrap_servers}")
            logger.info(f"ClickHouse URL: {self.config.clickhouse.jdbc_url}")
            
            # Create Spark session
            self.create_spark_session()
            
            # Start streaming
            query = self.start_streaming()
            
            # Wait for termination
            query.awaitTermination()
            
        except Exception as e:
            logger.error(f"Job failed: {e}")
            raise
        finally:
            self.stop_streaming()
            if self.spark:
                self.spark.stop()


def main():
    """Main function"""
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Load configuration
    config = AppConfig()
    
    # Override app name for orders
    config.spark.app_name = "Ecommerce Orders CDC Processing"
    
    # Create and run job
    job = OrdersCDCJob(config)
    job.run()


if __name__ == "__main__":
    main()
