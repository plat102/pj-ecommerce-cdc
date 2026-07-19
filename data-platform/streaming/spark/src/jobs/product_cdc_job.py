from src.config.app_config import AppConfig
from src.jobs.base_cdc_job import BaseCDCJob
from src.transformations.kafka_parser import KafkaMessageParser
from src.transformations.product_cdc_transformer import ProductCDCTransformer
from src.transformations.cdc_transformer import CDCTransformer
from src.utils.helpers import fetch_avro_schema
from src.common.logging import get_logger

logger = get_logger(__name__)


class ProductCDCJob(BaseCDCJob):
    """CDC Job for Products"""

    def process(self):
        logger.info(f"ProductCDCJob process started. kafka_reader: {self.kafka_reader}")
        topic = self.config.kafka.topics["products"]
        stream_df = self.kafka_reader.read_stream(topic)

        # Fetch Avro schemas from Apicurio (Confluent-compat endpoint) once
        # at query build time; producer schema is stable per topic.
        registry_url = self.config.schema_registry.url
        key_schema_json = fetch_avro_schema(registry_url, f"{topic}-key")
        value_schema_json = fetch_avro_schema(registry_url, f"{topic}-value")

        # Decode Avro (strips 5-byte Confluent header, then from_avro).
        cdc_df = KafkaMessageParser.parse_avro_message(
            kafka_stream=stream_df,
            key_avro_schema=key_schema_json,
            value_avro_schema=value_schema_json,
        )

        # Transform
        if self.config.debug_mode:
            df = ProductCDCTransformer.transform_for_debug(cdc_df)
            df = CDCTransformer.add_processing_metadata(df)
        else:
            df = ProductCDCTransformer.transform_for_clickhouse(cdc_df)

        return CDCTransformer.filter_valid_records(df)


def main():
    config = AppConfig()
    job = ProductCDCJob(config)

    try:
        job.start_streaming(process_func=job.process, table_name="products_cdc")
        job.wait_for_termination()
    except Exception as e:
        logger.error(f"❌ Error occurred: {e}")
        job.stop_streaming()


if __name__ == "__main__":
    main()
