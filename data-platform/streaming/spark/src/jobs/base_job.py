from typing import Optional
from pyspark.sql import SparkSession
from src.config.app_config import AppConfig
from src.common.logging import get_logger

logger = get_logger()


class BaseJob:
    """Base class for any Spark job"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.spark: Optional[SparkSession] = None

    def create_spark_session(self):
        """Create Spark session with configs"""
        builder = SparkSession.builder.appName(self.config.spark.app_name)

        for key, value in self.config.spark.get_spark_configs().items():
            builder.config(key, value)

        if self.config.spark.master:
            builder = builder.master(self.config.spark.master)

        self.spark = builder.getOrCreate()
        logger.info(
            f"Spark session created with app name: {self.config.spark.app_name}\
                (id: {self.spark.sparkContext.applicationId})"
        )
