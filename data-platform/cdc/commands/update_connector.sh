curl -X PUT -H "Content-Type: application/json" \
     --data @data-platform/cdc/connectors/register-pg.json \
     http://localhost:8083/connectors/pg-connector-ecommerce/config\


curl -s http://localhost:8083/connectors/pg-connector-ecommerce/status
