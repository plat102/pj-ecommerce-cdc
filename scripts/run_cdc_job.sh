#!/bin/bash

# CDC Job Runner Script
# Supports running different CDC jobs (customers, products, orders)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
JOB_TYPE="customers"
DEBUG_MODE=""
HELP=false

# Function to show help
show_help() {
    echo "🚀 CDC Job Runner"
    echo ""
    echo "Usage: $0 [OPTIONS] <job_type>"
    echo ""
    echo "Job Types:"
    echo "  customers     Run customers CDC job"
    echo "  products      Run products CDC job"
    echo "  orders        Run orders CDC job"
    echo ""
    echo "Options:"
    echo "  --debug       Run in debug mode (console output)"
    echo "  --help, -h    Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 customers --debug     # Run customers job in debug mode"
    echo "  $0 products             # Run products job in production mode"
    echo "  $0 orders --debug       # Run orders job in debug mode"
    echo ""
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --debug)
            DEBUG_MODE="--debug"
            shift
            ;;
        --help|-h)
            HELP=true
            shift
            ;;
        customers|products|orders)
            JOB_TYPE="$1"
            shift
            ;;
        *)
            echo -e "${RED}❌ Unknown argument: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

if [[ "$HELP" == true ]]; then
    show_help
    exit 0
fi

# Validate job type
case $JOB_TYPE in
    customers|products|orders)
        ;;
    *)
        echo -e "${RED}❌ Invalid job type: $JOB_TYPE${NC}"
        echo -e "${YELLOW}💡 Valid job types: customers, products, orders${NC}"
        exit 1
        ;;
esac

# Determine mode for display
if [[ -n "$DEBUG_MODE" ]]; then
    MODE_MSG="Debug Mode - Console"
    MODE_COLOR=$YELLOW
else
    MODE_MSG="Production Mode - ClickHouse"
    MODE_COLOR=$GREEN
fi

# Display configuration
echo -e "${BLUE}🚀 Starting CDC ${JOB_TYPE^} Job (${MODE_COLOR}${MODE_MSG}${BLUE})...${NC}"

# Check if Spark container is running
echo -e "${BLUE}✅ Spark container is ready${NC}"

# Change to the project root directory
cd "$(dirname "$0")/.."

# Run the CDC job
echo -e "${BLUE}🔄 Running CDC job...${NC}"

# Set environment variables for debug mode
if [[ -n "$DEBUG_MODE" ]]; then
    export DEBUG_MODE=true
else
    export DEBUG_MODE=false
fi

# Execute the appropriate job based on job type
JOB_FILE=""
case $JOB_TYPE in
    customers)
        JOB_FILE="src/jobs/customers_cdc_job.py"
        ;;
    products)
        JOB_FILE="src/jobs/products_cdc_job.py"
        ;;
    orders)
        JOB_FILE="src/jobs/orders_cdc_job.py"
        ;;
esac

# Docker execution
docker exec -it ed-pyspark-jupyter \
    bash -c "cd /home/jupyter/src-streaming/spark && \
    PYTHONPATH=/home/jupyter/src-streaming/spark \
    DEBUG_MODE=${DEBUG_MODE:-false} \
    /spark/bin/spark-submit \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,com.clickhouse:clickhouse-jdbc:0.6.0 \
    --files src/schemas/cdc_schemas.py,src/utils/helpers.py,src/config/app_config.py \
    ${JOB_FILE}"
