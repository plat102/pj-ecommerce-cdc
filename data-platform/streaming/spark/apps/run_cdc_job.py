#!/usr/bin/env python3
"""
Entry point for running CDC processing jobs
"""
import sys
import argparse
import logging
from pathlib import Path

# Add src to Python path
sys.path.append(str(Path(__file__).parent.parent))

from src.jobs.customers_cdc_job import CDCProcessor
from src.jobs.product_cdc_job import ProductCDCJob
from src.config.app_config import AppConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for CDC jobs"""
    parser = argparse.ArgumentParser(description='Run CDC Processing Jobs')
    parser.add_argument(
        '--job-type', 
        choices=['customers', 'orders', 'products'], 
        default='customers',
        help='Type of CDC job to run'
    )
    parser.add_argument(
        '--debug', 
        action='store_true',
        help='Run in debug mode (console output)'
    )
    parser.add_argument(
        '--config-file',
        help='Path to configuration file'
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = AppConfig()
    if args.debug:
        config.debug_mode = True
        
    logger.info(f"Starting {args.job_type} CDC job...")
    logger.info(f"Debug mode: {config.debug_mode}")
    logger.info(f"Kafka servers: {config.kafka.bootstrap_servers}")
    logger.info(f"ClickHouse URL: {config.clickhouse.jdbc_url}")
    
    # Create processor based on job type
    try:
        if args.job_type == 'customers':
            processor = CDCProcessor(config)
            processor.start_streaming()
            processor.wait_for_termination()
        elif args.job_type == 'products':
            job = ProductCDCJob(config)
            job.start_streaming(process_func=job.process, table_name="products_cdc")
            job.wait_for_termination()
        else:
            raise ValueError(f"Unsupported job type: {args.job_type}")
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Job failed: {e}")
        sys.exit(1)
    finally:
        # Cleanup based on job type
        if args.job_type == 'customers' and 'processor' in locals():
            processor.stop_streaming()
        elif args.job_type == 'products' and 'job' in locals():
            job.stop_streaming()


if __name__ == "__main__":
    main()
