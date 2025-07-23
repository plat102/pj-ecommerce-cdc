#!/bin/bash
TOPIC=${1:-test-topic}

docker exec -it kafka1 \
  kafka-console-producer \
  --broker-list kafka1:9092 \
  --topic "$TOPIC"


docker exec -it kafka1 \
  kafka-topics --create \
  --topic test-topic \
  --bootstrap-server kafka1:9092 \
  --partitions 1 \
  --replication-factor 1

docker exec -it kafka1 \
  kafka-topics --list \
  --bootstrap-server kafka1:9092

docker exec -it kafka1 \
  kafka-console-producer \
  --broker-list kafka1:9092 \
  --topic test-topic
