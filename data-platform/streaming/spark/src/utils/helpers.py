"""
Pure utility functions for data processing
"""
import json
import logging

import requests
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType

logger = logging.getLogger(__name__)


def _fetch_raw_schema(registry_url: str, subject: str) -> dict:
    url = f"{registry_url.rstrip('/')}/subjects/{subject}/versions/latest"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    schema_str = resp.json().get("schema")
    if not schema_str:
        raise RuntimeError(f"Schema Registry returned no 'schema' field for {subject}")
    return json.loads(schema_str)


def _inline_refs(schema_node, registry_url: str, seen: set) -> object:
    """Walk an Avro schema tree and replace string-named type references with
    their fully-resolved subschemas fetched from the registry.

    Debezium registers auxiliary types (like `io.debezium.connector.postgresql.Source`)
    as separate subjects and references them by fully-qualified name inside the
    envelope schema. Spark's `from_avro` needs a self-contained schema, so we
    inline every reference the first time we see it.
    """
    if isinstance(schema_node, dict):
        return {k: _inline_refs(v, registry_url, seen) for k, v in schema_node.items()}
    if isinstance(schema_node, list):
        return [_inline_refs(item, registry_url, seen) for item in schema_node]
    if isinstance(schema_node, str) and "." in schema_node and schema_node not in seen:
        # Primitives and already-inlined types won't match this branch.
        try:
            ref_schema = _fetch_raw_schema(registry_url, schema_node)
        except requests.HTTPError:
            return schema_node  # not a subject we own; leave as-is
        seen.add(schema_node)
        return _inline_refs(ref_schema, registry_url, seen)
    return schema_node


def fetch_avro_schema(registry_url: str, subject: str) -> str:
    """Fetch a registered Avro schema and return a self-contained JSON string.

    Any string-named type references (Debezium's `Source`, envelope refs, etc.)
    are resolved against the same registry so `from_avro` receives a schema it
    can parse without further lookups. The registry URL should point at
    Apicurio's Confluent-compatible endpoint
    (e.g. `http://schema-registry:8080/apis/ccompat/v7`).
    """
    root = _fetch_raw_schema(registry_url, subject)
    resolved = _inline_refs(root, registry_url, seen=set())
    schema_str = json.dumps(resolved)
    logger.info("Fetched + resolved Avro schema for subject %s", subject)
    return schema_str


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


def validate_config(config):
    """
    Validate application configuration
    
    Args:
        config: Application configuration object
        
    Raises:
        ValueError: If configuration is invalid
    """
    if not config.kafka.bootstrap_servers:
        raise ValueError("Kafka bootstrap servers must be specified")
    
    if not config.clickhouse.jdbc_url:
        raise ValueError("ClickHouse JDBC URL must be specified")
    
    if not config.spark.app_name:
        raise ValueError("Spark application name must be specified")


def safe_cast(value, target_type, default=None):
    """
    Safely cast value to target type
    
    Args:
        value: Value to cast
        target_type: Target type (int, float, str, etc.)
        default: Default value if casting fails
        
    Returns:
        Casted value or default
    """
    try:
        return target_type(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def format_kafka_topic_name(database: str, schema: str, table: str) -> str:
    """
    Format Kafka topic name for CDC
    
    Args:
        database: Database name
        schema: Schema name
        table: Table name
        
    Returns:
        str: Formatted topic name
    """
    return f"{database}.{schema}.{table}"


def extract_table_name_from_topic(topic: str) -> str:
    """
    Extract table name from Kafka topic
    
    Args:
        topic: Kafka topic name (e.g., "pg.public.customers")
        
    Returns:
        str: Table name
    """
    parts = topic.split('.')
    return parts[-1] if parts else topic
