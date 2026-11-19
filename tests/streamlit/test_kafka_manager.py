"""Happy-path tests for KafkaManager.

KafkaManager creates a KafkaConsumer with topic + bootstrap_servers wired
from its config. Real Kafka is not required; the KafkaConsumer class is
patched at the boundary.
"""
from managers.kafka import KafkaManager


def test_create_consumer_uses_config_bootstrap_servers(mocker):
    mock_consumer_cls = mocker.patch("managers.kafka.KafkaConsumer")
    mocker.patch("managers.kafka.st")  # silence st.error

    km = KafkaManager({"bootstrap_servers": "kafka1:9092"})
    km.create_consumer(topics=["pg.public.customers"])

    mock_consumer_cls.assert_called_once()
    args, kwargs = mock_consumer_cls.call_args
    assert args == ("pg.public.customers",)
    assert kwargs["bootstrap_servers"] == "kafka1:9092"
    assert kwargs["auto_offset_reset"] == "latest"
    assert kwargs["group_id"] == "streamlit-consumer"


def test_create_consumer_from_beginning_uses_earliest(mocker):
    mock_consumer_cls = mocker.patch("managers.kafka.KafkaConsumer")
    mocker.patch("managers.kafka.st")

    km = KafkaManager({"bootstrap_servers": "kafka1:9092"})
    km.create_consumer(topics=["pg.public.orders"], from_beginning=True)

    _, kwargs = mock_consumer_cls.call_args
    assert kwargs["auto_offset_reset"] == "earliest"
    assert kwargs["group_id"].startswith("streamlit-consumer-recent-")
