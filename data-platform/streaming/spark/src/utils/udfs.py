import hashlib
import os
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


# PII_SALT resolved at import time so executors pick it up from the driver
# env. Rotation is a redeploy event — see openspec/changes/add-data-governance
# design.md § Risks: "PII salt rotation breaks historical joins".
_PII_SALT = os.getenv("PII_SALT", "")


def hash_pii(value: str) -> str:
    """
    Deterministic SHA-256 hash of a PII string with PII_SALT.

    Same input + same salt -> same hash, so hashed values remain joinable
    across systems. Salt rotation invalidates historical hashes.
    """
    if value is None:
        return None
    digest = hashlib.sha256()
    digest.update(_PII_SALT.encode("utf-8"))
    digest.update(value.encode("utf-8"))
    return digest.hexdigest()


hash_pii_udf = udf(hash_pii, StringType())


def tokenize_name(value: str) -> str:
    """
    Tokenize a human name as first-initial + `.` + short hash of remainder.

    Example: "Jane Doe" -> "J.a3f9b2". Preserves an initial for readability
    while making the rest irreversible without the salt.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    initial = stripped[0].upper()
    remainder = stripped[1:]
    digest = hashlib.sha256()
    digest.update(_PII_SALT.encode("utf-8"))
    digest.update(remainder.encode("utf-8"))
    return f"{initial}.{digest.hexdigest()[:6]}"


tokenize_name_udf = udf(tokenize_name, StringType())
