#!/bin/bash
# Simple CDC Run Script

set -e

echo "🚀 Starting CDC Customers Job..."

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

# Run the CDC job
docker exec ed-pyspark-jupyter bash -c "cd /home/jupyter/src-streaming/spark && ./scripts/submit_job.sh --job-type customers --debug"

echo "✅ CDC job completed!"
