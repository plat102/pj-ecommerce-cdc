#!/bin/bash
# Spark Submit Script for CDC Processing

set -e

# Default values
JOB_TYPE="customers"
DEBUG_MODE="false"
SPARK_MASTER="local[*]"
PACKAGES="org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,com.clickhouse:clickhouse-jdbc:0.6.0,org.apache.spark:spark-avro_2.12:3.5.0,io.confluent:kafka-schema-registry-client:7.8.2,io.confluent:kafka-avro-serializer:7.8.2,io.openlineage:openlineage-spark_2.12:1.24.2"
REPOSITORIES="https://packages.confluent.io/maven/"

# OpenLineage listener config. Opt-in via ENABLE_OPENLINEAGE=1 so dev
# environments without a lineage collector are unaffected. When enabled,
# emits START/COMPLETE/FAIL events to OpenMetadata's OpenLineage endpoint
# (namespace `ecommerce-cdc-spark`, one job per --job-type).
OPENLINEAGE_CONFS=()
if [[ "${ENABLE_OPENLINEAGE:-0}" == "1" ]]; then
    OPENLINEAGE_URL="${OPENLINEAGE_URL:-http://openmetadata-server:8585/api/v1/openlineage}"
    OPENLINEAGE_NAMESPACE="${OPENLINEAGE_NAMESPACE:-ecommerce-cdc-spark}"
    OPENLINEAGE_CONFS=(
        --conf spark.extraListeners=io.openlineage.spark.agent.OpenLineageSparkListener
        --conf spark.openlineage.transport.type=http
        --conf spark.openlineage.transport.url=$OPENLINEAGE_URL
        --conf spark.openlineage.namespace=$OPENLINEAGE_NAMESPACE
    )
    echo "🧬 OpenLineage: $OPENLINEAGE_URL (namespace=$OPENLINEAGE_NAMESPACE)"
fi

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

# Path to metrics.properties inside the pyspark-jupyter container.
# The `data-platform/streaming` tree is bind-mounted at /home/jupyter/src-streaming.
METRICS_PROPS="${SPARK_METRICS_CONF:-/home/jupyter/src-streaming/spark/conf/metrics.properties}"

# Submit Spark job
spark-submit \
    --master $SPARK_MASTER \
    --packages $PACKAGES \
    --repositories $REPOSITORIES \
    "${OPENLINEAGE_CONFS[@]}" \
    --conf spark.streaming.stopGracefullyOnShutdown=true \
    --conf spark.sql.shuffle.partitions=8 \
    --conf spark.ui.prometheus.enabled=true \
    --conf spark.metrics.conf=$METRICS_PROPS \
    --py-files src/schemas/cdc_schemas.py,src/utils/helpers.py,src/config/app_config.py,src/jobs/customers_cdc_job.py,src/jobs/product_cdc_job.py,src/jobs/order_cdc_job.py \
    apps/run_cdc_job.py \
    --job-type $JOB_TYPE \
    $([ "$DEBUG_MODE" = "true" ] && echo "--debug")

echo "✅ Spark job completed!"
