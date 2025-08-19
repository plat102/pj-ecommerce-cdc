from decimal import Decimal
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType, DecimalType

def decode_bytes(bytes_array):
    """
    Decode byte array to UTF-8 string
    
    Args:
        bytes_array: Byte array from Kafka message
        
    Returns:
        str: Decoded string or None if decoding fails
    """
    if bytes_array is not None:
        try:
            return bytes(bytes_array).decode('utf-8')
        except Exception:
            return None
    return None


# Create UDF for decoding
decode_udf = udf(decode_bytes, StringType())

def decode_decimal(binary_value, scale=2):
    """
    Decode Debezium decimal (bytes) into Decimal with given scale.
    """
    if binary_value is None:
        return None
    int_val = int.from_bytes(binary_value, byteorder="big", signed=True)
    return Decimal(int_val).scaleb(-scale)


# Register glabal UDF for decoding decimal
decode_decimal_udf = udf(lambda b: decode_decimal(b, 2), DecimalType(10, 2))
