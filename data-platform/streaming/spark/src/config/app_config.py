"""
Configuration settings for CDC processing jobs
"""
import os
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class KafkaConfig:
    """Kafka connection configuration"""
    bootstrap_servers: str = "kafka1:9092"
    topics: Dict[str, str] = None
    
    def __post_init__(self):
        if self.topics is None:
            self.topics = {
                "customers": "pg.public.customers",
                "orders": "pg.public.orders",
                "products": "pg.public.products"
            }


@dataclass
class ClickHouseConfig:
    """ClickHouse connection configuration"""
    host: str = "clickhouse"
    port: int = 8123
    database: str = "ecommerce_analytics"
    user: str = "default"
    password: str = "clickhouse123"
    
    @property
    def jdbc_url(self) -> str:
        return f"jdbc:clickhouse://{self.host}:{self.port}/{self.database}"
    
    @property
    def connection_properties(self) -> Dict[str, str]:
        return {
            "user": self.user,
            "password": self.password,
            "driver": "com.clickhouse.jdbc.ClickHouseDriver"
        }


@dataclass
class SparkConfig:
    """Spark application configuration"""
    app_name: str = "Ecommerce CDC Processing"
    master: str = "local[*]"
    shuffle_partitions: int = 8
    packages: str = "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,com.clickhouse:clickhouse-jdbc:0.6.0"
    
    def get_spark_configs(self) -> Dict[str, Any]:
        return {
            "spark.streaming.stopGracefullyOnShutdown": True,
            "spark.jars.packages": self.packages,
            "spark.sql.shuffle.partitions": self.shuffle_partitions
        }


class AppConfig:
    """Main application configuration"""
    
    def __init__(self):
        self.kafka = KafkaConfig(
            bootstrap_servers=os.getenv("KAFKA_SERVERS", "kafka1:9092")
        )
        
        self.clickhouse = ClickHouseConfig(
            host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            database=os.getenv("CLICKHOUSE_DB", "ecommerce_analytics"),
            user=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", "clickhouse123")
        )
        
        self.spark = SparkConfig(
            app_name=os.getenv("SPARK_APP_NAME", "Ecommerce CDC Processing"),
            master=os.getenv("SPARK_MASTER", "local[*]"),
            shuffle_partitions=int(os.getenv("SPARK_SHUFFLE_PARTITIONS", "8"))
        )
        
        # Processing settings
        self.checkpoint_location = os.getenv("CHECKPOINT_LOCATION", "/tmp/spark-checkpoints")
        self.trigger_interval = os.getenv("TRIGGER_INTERVAL", "10 seconds")
        self.debug_mode = os.getenv("DEBUG_MODE", "false").lower() == "true"
