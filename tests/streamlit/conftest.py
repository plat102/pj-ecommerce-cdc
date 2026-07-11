"""Mock fixtures for Streamlit-side unit tests.

Real Postgres and Kafka connections are patched at the client-library
boundary (psycopg2, kafka-python) so managers can be exercised without a
running stack.
"""
import pytest


@pytest.fixture
def mock_psycopg2_connect(mocker):
    """Patch `psycopg2.connect` and return the mock connection object.

    Cursor is a MagicMock; tests assert on `.cursor().execute(...)` calls.
    """
    mock_conn = mocker.MagicMock(name="psycopg2_connection")
    mock_cursor = mocker.MagicMock(name="psycopg2_cursor")
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.cursor.return_value = mock_cursor
    mocker.patch("psycopg2.connect", return_value=mock_conn)
    return mock_conn


@pytest.fixture
def mock_kafka_producer(mocker):
    """Patch `kafka.KafkaProducer` and return the mock producer instance."""
    mock_producer = mocker.MagicMock(name="kafka_producer")
    mocker.patch("kafka.KafkaProducer", return_value=mock_producer)
    return mock_producer


@pytest.fixture
def mock_kafka_consumer(mocker):
    """Patch `kafka.KafkaConsumer` and return the mock consumer instance."""
    mock_consumer = mocker.MagicMock(name="kafka_consumer")
    mocker.patch("kafka.KafkaConsumer", return_value=mock_consumer)
    return mock_consumer
