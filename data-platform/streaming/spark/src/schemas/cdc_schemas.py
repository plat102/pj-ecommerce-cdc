"""
CDC Schema definitions for Debezium format messages
"""
from pyspark.sql.types import StructType, StructField, IntegerType, StringType, LongType


class CDCSchemas:
    """Schema definitions for CDC messages"""
    
    @staticmethod
    def get_key_schema():
        """Get schema for Kafka message key"""
        return StructType([
            StructField("id", IntegerType(), True)
        ])
    
    @staticmethod
    def get_customers_value_schema():
        """Get schema for customers CDC value JSON (Debezium format)"""
        customer_record_schema = StructType([
            StructField("id", IntegerType(), True),
            StructField("name", StringType(), True),
            StructField("email", StringType(), True),
            StructField("created_at", LongType(), True)
        ])
        
        return StructType([
            StructField("before", customer_record_schema, True),
            StructField("after", customer_record_schema, True),
            StructField("source", StructType([
                StructField("ts_ms", LongType(), True),
                StructField("schema", StringType(), True),
                StructField("table", StringType(), True)
            ]), True),
            StructField("op", StringType(), True),
            StructField("ts_ms", LongType(), True)
        ])

    @staticmethod
    def get_products_value_schema():
        """Get products value schema"""
        # TODO
        pass
    
    @staticmethod
    def get_orders_value_schema():
        """Get orders value schema"""
        # TODO
        pass
    
    