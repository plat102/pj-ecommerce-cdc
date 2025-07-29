# Apache Spark Setup Guide

This guide explains how to set up and run Apache Spark with Docker Compose for CDC data processing.

## Architecture

The Spark setup includes:
- **Spark Master**: Cluster coordinator and web UI
- **Spark Workers**: Compute nodes (2 workers by default)
- **Spark History Server**: Job history and monitoring
- **Jupyter Lab**: Interactive notebooks with PySpark

## Services and Ports

| Service | Port | Description |
|---------|------|-------------|
| Spark Master Web UI | 8085 | Cluster monitoring and job tracking |
| Spark Worker 1 UI | 8086 | Worker node 1 status |
| Spark Worker 2 UI | 8087 | Worker node 2 status |
| Spark History Server | 18080 | Historical job information |
| Jupyter Lab | 8888 | Interactive notebooks |

## Quick Start

### 1. Start Spark Cluster
```bash
# Start only Spark services
make up-spark

# Or start full stack including Spark
make up
```

### 2. Verify Installation
```bash
# Check container status
make status-spark

# View logs
make logs-spark
```

### 3. Access Web UIs
- **Spark Master**: http://localhost:8085
- **Spark History**: http://localhost:18080
- **Jupyter Lab**: http://localhost:8888

### 4. Get Jupyter Token
```bash
make jupyter-token
```

## Usage Examples

### Spark Shell
```bash
# Start Spark shell
make spark-shell

# Start PySpark shell
make pyspark-shell
```

### Submit Applications
```bash
# Submit a Spark application
make spark-submit APP=cdc_consumer.py
```

### Interactive Development
1. Access Jupyter Lab at http://localhost:8888
2. Use the provided token
3. Open the demo notebook: `cdc_processing_demo.ipynb`

## Directory Structure

```
spark/
├── conf/                   # Spark configuration
│   └── spark-defaults.conf
├── apps/                   # Spark applications
│   └── cdc_consumer.py
├── notebooks/              # Jupyter notebooks
│   └── cdc_processing_demo.ipynb
├── data/                   # Data files
├── events/                 # Spark event logs
└── jars/                   # Additional JAR files
```

## Configuration

### Spark Configuration
Main configuration in `spark/conf/spark-defaults.conf`:
- Event logging enabled for history server
- Adaptive query execution
- Kafka integration settings

### Resource Allocation
Default worker configuration:
- **Memory**: 2GB per worker
- **Cores**: 2 CPU cores per worker
- **Workers**: 2 workers

### Scaling Workers
To add more workers, modify `docker-compose.spark.yml`:
```yaml
spark-worker-3:
  image: bitnami/spark:3.5.3
  # ... same configuration as other workers
```

## CDC Integration

### Kafka Dependencies
The setup includes Kafka integration for CDC processing:
- Kafka structured streaming
- JSON parsing capabilities
- Checkpoint management

### Example CDC Processing
See `apps/cdc_consumer.py` for a complete example of:
- Reading CDC events from Kafka
- Parsing Debezium JSON format
- Processing INSERT/UPDATE operations
- Writing results to various sinks

## Troubleshooting

### Common Issues

1. **Out of Memory**
   - Increase worker memory in docker-compose
   - Adjust `spark.executor.memory` in spark-defaults.conf

2. **Connection to Kafka Failed**
   - Ensure Kafka is running: `make up-kafka`
   - Check network connectivity between containers

3. **Jupyter Token Issues**
   - Get new token: `make jupyter-token`
   - Check container logs: `make logs-spark`

### Performance Tuning

1. **Memory Settings**
   ```properties
   spark.executor.memory=4g
   spark.driver.memory=2g
   ```

2. **Parallelism**
   ```properties
   spark.sql.adaptive.coalescePartitions.initialPartitionNum=200
   ```

3. **Checkpointing**
   ```properties
   spark.sql.streaming.checkpointLocation=/opt/spark-data/checkpoints
   ```

## Useful Commands

```bash
# Spark cluster management
make up-spark              # Start Spark cluster
make down-spark            # Stop Spark cluster
make restart-spark         # Restart cluster
make status-spark          # Check status

# Interactive shells
make spark-shell           # Scala Spark shell
make pyspark-shell         # Python Spark shell
make sh-spark-master       # Container shell

# Monitoring
make logs-spark            # View logs
make jupyter-token         # Get Jupyter token
```

## Next Steps

1. **Explore Examples**: Try the provided notebooks and applications
2. **Connect to Kafka**: Set up CDC pipeline with Debezium
3. **Add More Workers**: Scale the cluster based on your needs
4. **Monitor Performance**: Use the web UIs to track job performance
5. **Custom Applications**: Develop your own CDC processing logic

For more information, see the main project documentation.
