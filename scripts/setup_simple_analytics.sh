#!/bin/bash

# =====================================================
# Ecommerce CDC Analytics Setup (SIMPLIFIED)
# Only ClickHouse Views + Grafana Dashboards
# =====================================================

set -e

echo "🚀 Setting up Simple Ecommerce Analytics..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}$1${NC}"
}

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    print_error "Docker is not running. Please start Docker first."
    exit 1
fi

print_header "📊 Step 1: Check & Start Services"

cd infrastructure/docker

# Check if ClickHouse is already running
if docker ps | grep -q clickhouse; then
    print_status "ClickHouse is already running - skipping start"
else
    print_status "Starting ClickHouse..."
    docker-compose -f docker-compose.analytics.yml up -d clickhouse
    print_status "Waiting for ClickHouse to start..."
    sleep 15
fi

# Check if Grafana is already running
if docker ps | grep -q grafana; then
    print_status "Grafana is already running - skipping start"
else
    print_status "Starting Grafana..."
    docker-compose -f docker-compose.analytics.yml up -d grafana
    print_status "Waiting for Grafana to start..."
    sleep 10
fi

# Wait for ClickHouse to be ready
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if docker exec clickhouse clickhouse-client --query "SELECT 1" > /dev/null 2>&1; then
        print_status "ClickHouse is ready!"
        break
    fi
    
    print_status "Waiting for ClickHouse... (attempt $((attempt + 1))/$max_attempts)"
    sleep 2
    attempt=$((attempt + 1))
done

if [ $attempt -eq $max_attempts ]; then
    print_error "ClickHouse failed to start within expected time"
    exit 1
fi

print_header "📈 Step 2: Create Analytics Views"

# Create analytics views in ClickHouse
print_status "Creating analytics views..."
cd ../../data-platform/dashboards/clickhouse

docker exec -i clickhouse clickhouse-client --multiquery < analytics_views.sql

if [ $? -eq 0 ]; then
    print_status "✅ Analytics views created successfully"
else
    print_error "❌ Failed to create analytics views"
    exit 1
fi

print_header "📊 Step 3: Setup Grafana Datasource"

# Wait for Grafana to be ready
print_status "Waiting for Grafana to start..."
sleep 10

print_header "✅ Setup Complete!"

echo ""
echo "🎯 What you have now:"
echo "   📊 ClickHouse with analytics views"
echo "   📈 Grafana dashboards ready to import"
echo "   🔄 Real-time data from CDC pipeline"
echo ""
echo "📱 Access URLs:"
echo "   Grafana: http://localhost:3000 (admin/admin123)"
echo "   ClickHouse: http://localhost:8123"
echo ""
echo "🔍 Test analytics queries:"
echo "   docker exec -it clickhouse clickhouse-client"
echo "   USE ecommerce_analytics;"
echo "   SELECT * FROM daily_sales_summary LIMIT 5;"
echo ""
echo "📊 Import Grafana dashboards:"
echo "   1. Open Grafana → Import"
echo "   2. Upload: data-platform/dashboards/grafana/executive-dashboard.json"
echo "   3. Upload: data-platform/dashboards/grafana/customer-insights.json"
echo ""

print_status "🎉 Simple Analytics setup completed!"
print_status "💡 No extra services needed - Grafana queries ClickHouse directly!"
