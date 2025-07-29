"""
Example Spark application for CDC data processing
This script demonstrates how to consume Kafka CDC data with Spark Structured Streaming
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import *

# Initialize Spark Session
spark = SparkSession.builder \
    .appName("CDC_Kafka_Consumer") \
    .config("spark.sql.streaming.checkpointLocation", "/opt/spark-data/checkpoints") \
    .getOrCreate()

# Set log level
spark.sparkContext.setLogLevel("WARN")

# Define schema for CDC events
cdc_schema = StructType([
    StructField("before", StructType([
        StructField("id", IntegerType()),
        StructField("name", StringType()),
        StructField("email", StringType()),
        StructField("created_at", StringType())
    ])),
    StructField("after", StructType([
        StructField("id", IntegerType()),
        StructField("name", StringType()),
        StructField("email", StringType()),
        StructField("created_at", StringType())
    ])),
    StructField("source", StructType([
        StructField("table", StringType()),
        StructField("db", StringType())
    ])),
    StructField("op", StringType()),
    StructField("ts_ms", LongType())
])

def process_cdc_stream():
    """Process CDC stream from Kafka"""
    
    # Read from Kafka
    df = spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "kafka1:9092") \
        .option("subscribe", "ecommerce.public.customers") \
        .option("startingOffsets", "latest") \
        .load()
    
    # Parse JSON
    parsed_df = df.select(
        col("key").cast("string"),
        from_json(col("value").cast("string"), cdc_schema).alias("data"),
        col("timestamp")
    )
    
    # Extract CDC fields
    result_df = parsed_df.select(
        col("key"),
        col("data.op").alias("operation"),
        col("data.before").alias("before_data"),
        col("data.after").alias("after_data"),
        col("data.source.table").alias("table_name"),
        col("timestamp")
    )
    
    # Filter only INSERT and UPDATE operations
    filtered_df = result_df.filter(col("operation").isin("c", "u"))
    
    # Write to console (for testing)
    query = filtered_df.writeStream \
        .outputMode("append") \
        .format("console") \
        .option("truncate", False) \
        .trigger(processingTime='10 seconds') \
        .start()
    
    query.awaitTermination()

if __name__ == "__main__":
    print("Starting CDC Kafka Consumer...")
    process_cdc_stream()
