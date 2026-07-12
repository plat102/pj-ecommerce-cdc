"""
Common ClickHouse operations for CDC processing
"""
from pyspark.sql import DataFrame
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class ClickHouseWriter:
    """ClickHouse writer with common operations"""
    
    def __init__(self, jdbc_url: str, connection_properties: Dict[str, str]):
        """
        Initialize ClickHouse writer
        
        Args:
            jdbc_url: ClickHouse JDBC URL
            connection_properties: Connection properties (user, password, driver)
        """
        self.jdbc_url = jdbc_url
        self.connection_properties = connection_properties
        
    def write_batch(self, df: DataFrame, table_name: str, mode: str = "append"):
        """
        Write DataFrame to ClickHouse table (batch mode)
        
        Args:
            df: DataFrame to write
            table_name: Target table name
            mode: Write mode (append, overwrite, etc.)
        """
        logger.info(f"💾 Writing batch to ClickHouse table: {table_name}")
        
        try:
            (df.write
             .format("jdbc")
             .option("url", self.jdbc_url)
             .option("dbtable", table_name)
             .options(**self.connection_properties)
             .mode(mode)
             .save())
             
            logger.info(f"✅ Batch written to {table_name} successfully!")
            
        except Exception as e:
            logger.error(f"❌ Error writing batch to ClickHouse: {e}")
            raise
    
    def write_stream_batch(self, batch_df: DataFrame, batch_id: int, table_name: str):
        """
        Write streaming batch to ClickHouse (for foreachBatch)
        
        Args:
            batch_df: Batch DataFrame
            batch_id: Batch ID
            table_name: Target table name
        """
        if not batch_df.isEmpty():
            count = batch_df.count()
            logger.info(f"📦 Processing batch {batch_id} with {count} records")
            self.write_batch(batch_df, table_name)
        else:
            logger.info(f"📦 Batch {batch_id} is empty, skipping...")
    
    def create_batch_writer_function(self, table_name: str):
        """
        Create a batch writer function for streaming.

        When ENABLE_GX_GATE=1, wraps the writer with a Great Expectations
        gate: invalid rows route to `{table_name}_dlq` before the
        ClickHouse write. Default off so dev environments without GX
        continue to work unchanged.
        """
        def write_batch_function(batch_df: DataFrame, batch_id: int):
            self.write_stream_batch(batch_df, batch_id, table_name)

        import os
        if os.getenv("ENABLE_GX_GATE") == "1":
            from src.governance.quality import with_gx_gate
            return with_gx_gate(write_batch_function, table_name)
        return write_batch_function
