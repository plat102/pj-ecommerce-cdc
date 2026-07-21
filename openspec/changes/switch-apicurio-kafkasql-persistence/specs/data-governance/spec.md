## ADDED Requirements

### Requirement: schema-registry-persistence

The Apicurio Registry service SHALL persist all registered artifacts across container restart, `make stop && make start`, and host reboot. Persistence SHALL be implemented via the `apicurio/apicurio-registry-kafkasql:${APICURIO_IMAGE_TAG}` image, which writes every registry mutation to a compacted Kafka topic (`kafkasql-journal`, auto-created with `cleanup.policy=compact` on first boot) and replays that topic on startup. The registry SHALL point at the existing broker via the `KAFKA_BOOTSTRAP_SERVERS` environment variable set to `kafka1:9092`. Persistence is NOT required across `make down`, because `make down` is documented-destructive and removes the underlying Kafka volume along with the journal topic.

#### Scenario: registry uses the kafkasql image variant

- **WHEN** `infrastructure/docker/docker-compose.kafka.yml` is inspected
- **THEN** the `schema-registry` service SHALL use image `apicurio/apicurio-registry-kafkasql:${APICURIO_IMAGE_TAG:-2.5.11.Final}`
- **AND** the service SHALL define environment variable `KAFKA_BOOTSTRAP_SERVERS: kafka1:9092`
- **AND** the healthcheck `start_period` SHALL be at least 30s to accommodate journal replay on cold start

#### Scenario: kafkasql journal topic exists after first boot

- **WHEN** the stack has been brought up via `make up` and Debezium has registered at least one Avro artifact
- **THEN** the Kafka cluster SHALL contain a topic named `kafkasql-journal` with `cleanup.policy=compact`
- **AND** the topic SHALL contain at least one record per registered artifact version

#### Scenario: artifacts survive registry container restart

- **GIVEN** the stack is up and Apicurio contains the six auto-registered CDC artifacts (`pg.public.customers-{key,value}`, `pg.public.products-{key,value}`, `pg.public.orders-{key,value}`)
- **WHEN** the `schema-registry` container is restarted via `docker restart schema-registry` and its healthcheck returns to `healthy`
- **THEN** `curl http://localhost:8081/apis/registry/v2/search/artifacts` SHALL return all six artifact IDs
- **AND** each artifact SHALL retain its pre-restart content ID so already-published Kafka messages remain decodable by downstream consumers

#### Scenario: artifacts survive make stop / make start

- **GIVEN** the stack is up and Apicurio contains the six auto-registered CDC artifacts
- **WHEN** `make stop` is executed followed by `make start`
- **THEN** the `schema-registry` container SHALL come back healthy and `curl http://localhost:8081/apis/registry/v2/search/artifacts` SHALL return all six artifact IDs

#### Scenario: artifacts are wiped by make down (documented-destructive)

- **GIVEN** the stack is up and Apicurio contains registered artifacts
- **WHEN** `make down` is executed followed by `make up`
- **THEN** the `schema-registry` container SHALL come up empty (no registered artifacts)
- **AND** Debezium SHALL re-register artifacts on the next CDC event as it does today
- **AND** this behavior SHALL NOT be treated as a persistence regression — it is consistent with the `destructive-teardown` requirement in the `infrastructure` capability
