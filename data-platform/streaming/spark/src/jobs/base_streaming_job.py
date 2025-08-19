from typing import Optional
from pyspark.sql.streaming import StreamingQuery
from src.jobs.base_job import BaseJob
from src.common.logging import get_logger

logger = get_logger()

class BaseStreamingJob(BaseJob):
    """Base class for Spark streaming jobs"""
    
    def __init__(self, config):
        super().__init__(config)
        self.streaming_query: Optional[StreamingQuery] = None
        
    def stop_streaming(self):
        if self.streaming_query:
            logger.info("Stopping streaming query...")
            self.streaming_query.stop()
            logger.info("Streaming query stopped.")

    def wait_for_termination(self):
        if self.streaming_query:
            self.streaming_query.awaitTermination()
