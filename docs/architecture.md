

```txt
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   PostgreSQL    │───▶│    Debezium     │───▶│      Kafka      │
│   (Source DB)   │    │  (CDC Capture)  │    │   (Streaming)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                       ┌─────────────────┐              │
                       │ Spark Streaming │◀─────────────┘
                       │ (Processing)    │
                       └─────────────────┘
                                │
                       ┌─────────────────┐
                       │   ClickHouse    │ 
                       │  (Analytics DB) │
                       │   + Views       │◀──── Analytics Views
                       └─────────────────┘
                                │
                       ┌─────────────────┐
                       │     Grafana     │
                       │  (Dashboards)   │◀──── JSON Dashboards  
                       └─────────────────┘
```