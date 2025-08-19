from src.config.app_config import AppConfig
from src.jobs.base_cdc_job import BaseCDCJob
from src.schemas.cdc_schemas import CDCSchemas
from src.transformations.kafka_parser import KafkaMessageParser
from src.transformations.product_cdc_transformer import ProductCDCTransformer
from src.transformations.cdc_transformer import CDCTransformer
from src.common.logging import get_logger

logger = get_logger(__name__)


class ProductCDCJob(BaseCDCJob):
    """CDC Job for Products"""

    def process(self):
        logger.info(f"ProductCDCJob process started. kafka_reader: {self.kafka_reader}")
        topic = self.config.kafka.topics["products"]
        stream_df = self.kafka_reader.read_stream(topic)
        schemas = CDCSchemas()

        # Parse binary into JSON
        json_df = KafkaMessageParser.parse_raw_message(stream_df)

        # Apply schema
        cdc_df = KafkaMessageParser.parse_json_structures(
            kafka_json_df=json_df,
            key_schema=schemas.get_key_schema(),
            value_schema=schemas.get_products_value_schema(),
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
