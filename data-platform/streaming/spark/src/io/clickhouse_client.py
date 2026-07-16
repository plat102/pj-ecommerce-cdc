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

        Optional wrappers, controlled by env vars:
          - ENABLE_SINK_DLQ=1 -- wraps the ClickHouse write with a try/except
            that routes failing batches to `{table_name}_sink_dlq`.
          - ENABLE_GX_GATE=1  -- wraps the (already-possibly-DLQ'd) writer with
            a Great Expectations gate that routes invalid rows to
            `{table_name}_dlq` before the sink stage.

        Composition when both are on:
            with_gx_gate(with_sink_dlq(inner, table), table)
        so invalid rows are filtered out before the sink layer ever sees them.
        """
        def write_batch_function(batch_df: DataFrame, batch_id: int):
            self.write_stream_batch(batch_df, batch_id, table_name)

        import os
        writer = write_batch_function
        if os.getenv("ENABLE_SINK_DLQ") == "1":
            from src.governance.error_handling import with_sink_dlq
            writer = with_sink_dlq(writer, table_name)
        if os.getenv("ENABLE_GX_GATE") == "1":
            from src.governance.quality import with_gx_gate
            writer = with_gx_gate(writer, table_name)
        return writer
