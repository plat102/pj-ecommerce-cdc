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

## 📊 **Monitoring**

- **Spark UI**: `http://driver:4040`
- **Key Metrics**: Input rate, processing latency, error rate, checkpoint duration

## 🔮 **Roadmap**

**Current**: ✅ Customers CDC, configuration management, Docker deployment

**Next**: 🔄 Orders/Products CDC, monitoring dashboard, alerting

**Future**: 📋 Schema registry, advanced error recovery, multi-sink support
