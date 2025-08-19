# 🚀 Spark CDC Processing Platform

Production-ready Spark Streaming platform for Change Data Capture (CDC) processing from PostgreSQL via Kafka to ClickHouse.

## 📁 **Code Structure**

```
data-platform/streaming/spark/
├── apps/                     # Application entry points
├── src/
│   ├── common/              # Infrastructure clients (Kafka, ClickHouse)
│   ├── transformations/     # Data processing logic
│   ├── utils/               # Pure utility functions
│   ├── schemas/             # Data structure definitions
│   ├── config/              # Configuration management
│   └── jobs/                # Business logic orchestration
├── scripts/                 # Deployment scripts
└── notebooks/               # Development notebooks
```

## 🎯 **Design Principles**

- **Separation of Concerns**: Each layer has distinct responsibilities
- **Reusability**: Infrastructure clients work across multiple jobs
- **Testability**: Each component can be unit tested independently
- **Production Ready**: Comprehensive logging, error handling, and monitoring

## 🏗️ **Components**

### **Common Layer** - Infrastructure Components
- `kafka_client.py`: KafkaReader for streaming/batch operations
- `clickhouse_client.py`: ClickHouseWriter for batch/streaming writes

### **Transformations Layer** - Data Processing
- `kafka_parser.py`: Parse Kafka messages (binary → JSON)
- `cdc_transformer.py`: Transform CDC operations (INSERT/UPDATE/DELETE)

### **Other Layers**
- **Utils**: Stateless utility functions
- **Schemas**: Spark SQL schemas for type safety
- **Config**: Environment-aware configuration
- **Jobs**: Business logic orchestration

## � **Quick Start**

### **Single Command Deployment**
```bash
# Run CDC job
make cdc-run
```

### **Development**
```bash
# Local development
python apps/run_cdc_job.py --job-type customers --debug

# Jupyter notebook
jupyter lab notebooks/ecom_cdc_processing.ipynb
```

### **Production**
```bash
# Spark submit
./scripts/submit_job.sh --job-type customers --master yarn
```

### Sample code flow
```txt
config → I/O → schema → transformations → job orchestration
```
Components:
1. Job entrypoint → lives in apps/.
2. Job orchestration → in jobs/, extends BaseJob.
3. I/O connectors → in io/ (Kafka, ClickHouse, DB, etc).
4. Schemas → in schemas/ (clear contracts, no inferSchema).
5. Transformations → in transformations/, stateless & testable.
6. Utils & logging → in utils/.
7. Config → in config/, always externalized (YAML/env).

This pattern ensures separation of concerns, maintainability, and scalability for Spark jobs in production.

Common coding flow:

```md
Config

    Load environment configs (dev/staging/prod).
    Example: Kafka topic, DB URL, checkpoint path, batch interval…
    👉 Centralize in config/app_config.py.

I/O (Input)

    Read data from source (Kafka, S3, DB, HDFS).
    👉 Put all connectors in io/ (e.g. kafka_client.py).

Schema

    Apply predefined schema (StructType) to raw input.
    Avoid inferSchema in production (not safe).
    👉 Define in schemas/.

Transformations

    Business logic (cleaning, enrichment, aggregations).
    Keep them stateless, testable, reusable.
    👉 Store in transformations/.

I/O (Output)

    Write results to sink (ClickHouse, S3, Parquet, etc).
    👉 Again via io/ layer.

Job orchestration

    Glue all above steps together in jobs/.
    Job = Config + I/O (in) + Schema + Transformations + I/O (out).
    👉 Example: OrdersJob in jobs/orders_job.py.
```
## 📊 **Monitoring**

- **Spark UI**: `http://driver:4040`
- **Key Metrics**: Input rate, processing latency, error rate, checkpoint duration

## 🔮 **Roadmap**

**Current**: ✅ Customers CDC, configuration management, Docker deployment

**Next**: 🔄 Orders/Products CDC, monitoring dashboard, alerting

**Future**: 📋 Schema registry, advanced error recovery, multi-sink support
