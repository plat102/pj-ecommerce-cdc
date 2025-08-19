#!/bin/bash
# Spark Submit Script for CDC Processing

set -e

# Default values
JOB_TYPE="customers"
DEBUG_MODE="false"
SPARK_MASTER="local[*]"
PACKAGES="org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,com.clickhouse:clickhouse-jdbc:0.6.0"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --job-type)
            JOB_TYPE="$2"
            shift 2
            ;;
        --debug)
            DEBUG_MODE="true"
            shift
            ;;
        --master)
            SPARK_MASTER="$2"
            shift 2
            ;;
        --packages)
            PACKAGES="$2"
            shift 2
            ;;
        *)
            echo "Unknown option $1"
            exit 1
            ;;
    esac
done

echo "🚀 Starting Spark CDC Job..."
echo "📋 Job Type: $JOB_TYPE"
echo "🐛 Debug Mode: $DEBUG_MODE"
echo "⚡ Spark Master: $SPARK_MASTER"

# Set environment variables
export DEBUG_MODE=$DEBUG_MODE

# Submit Spark job
spark-submit \
    --master $SPARK_MASTER \
    --packages $PACKAGES \
    --conf spark.streaming.stopGracefullyOnShutdown=true \
    --conf spark.sql.shuffle.partitions=8 \
    --py-files src/schemas/cdc_schemas.py,src/utils/helpers.py,src/config/app_config.py,src/jobs/customers_cdc_job.py,src/jobs/product_cdc_job.py \
    apps/run_cdc_job.py \
    --job-type $JOB_TYPE \
    $([ "$DEBUG_MODE" = "true" ] && echo "--debug")

echo "✅ Spark job completed!"
