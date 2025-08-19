#!/bin/bash
# Simple CDC Run Script

set -e

# Parse arguments
DEBUG_MODE="false"
JOB_TYPE="customers"
while [[ $# -gt 0 ]]; do
    case $1 in
        --debug)
            DEBUG_MODE="true"
            shift
            ;;
        --job-type)
            JOB_TYPE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option $1"
            echo "Usage: $0 [--debug] [--job-type customers|products]"
            exit 1
            ;;
    esac
done

if [ "$DEBUG_MODE" = "true" ]; then
    echo "🐛 Starting CDC $JOB_TYPE Job (Debug Mode - Console Output)..."
else
    echo "🚀 Starting CDC $JOB_TYPE Job (Production Mode - ClickHouse)..."
fi

# Check if Spark container is running
if ! docker ps | grep -q "ed-pyspark-jupyter"; then
    echo "🐳 Starting Spark container..."
    cd infrastructure/docker
    docker-compose -f docker-compose.spark.yml up -d
    echo "⏳ Waiting for container to be ready..."
    sleep 10
    cd ../..
fi

echo "✅ Spark container is ready"
echo "🔄 Running CDC job..."

# Run the CDC job with appropriate mode
if [ "$DEBUG_MODE" = "true" ]; then
    docker exec ed-pyspark-jupyter bash -c "cd /home/jupyter/src-streaming/spark && ./scripts/submit_job.sh --job-type $JOB_TYPE --debug"
else
    docker exec ed-pyspark-jupyter bash -c "cd /home/jupyter/src-streaming/spark && ./scripts/submit_job.sh --job-type $JOB_TYPE"
fi

echo "✅ CDC job completed!"
