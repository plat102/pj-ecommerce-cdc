TOPIC=${1:-test-topic}
GROUP=${2:-test-group}

docker exec -it kafka1 \
  kafka-console-consumer \
  --bootstrap-server kafka1:9092 \
  --topic "$TOPIC" \
  --group "$GROUP" \
  --from-beginning

docker exec -it kafka1 \
  kafka-console-consumer \
  --bootstrap-server kafka1:9092 \
  --topic pg.public.orders \
  --group test-consumer-group \
  --from-beginning

