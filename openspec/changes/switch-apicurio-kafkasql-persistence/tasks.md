## 1. Pre-cutover (optional archival)

- [ ] 1.1 If the stack is currently running, capture the currently-registered subjects for reference: `mkdir -p data-platform/cdc/schemas/backup && for s in $(curl -s http://localhost:8081/apis/ccompat/v7/subjects | jq -r '.[]'); do curl -s "http://localhost:8081/apis/ccompat/v7/subjects/$s/versions/latest" > "data-platform/cdc/schemas/backup/${s}.json"; done`. Do not commit; this is a local diagnostic artifact.
- [ ] 1.2 Bring the stack down cleanly to wipe the stale content-ID space before the cutover: `make down`.

## 2. Edit the compose service

- [ ] 2.1 In `infrastructure/docker/docker-compose.kafka.yml`, change the `schema-registry` service image from `apicurio/apicurio-registry-mem:${APICURIO_IMAGE_TAG:-2.5.11.Final}` to `apicurio/apicurio-registry-kafkasql:${APICURIO_IMAGE_TAG:-2.5.11.Final}`.
- [ ] 2.2 In the same service block, add environment variable `KAFKA_BOOTSTRAP_SERVERS: kafka1:9092` alongside the existing `QUARKUS_HTTP_PORT` and `QUARKUS_PROFILE`.
- [ ] 2.3 In the same service block, change the healthcheck `start_period` from `15s` to `30s`.
- [ ] 2.4 Update the header comment above the service (currently references the `-mem` image) to describe kafkasql-backed persistence: storage lives in the compacted Kafka topic `kafkasql-journal`, auto-created on first boot.

## 3. Verify env-example alignment

- [ ] 3.1 If `.env.example` contains a comment naming the `-mem` variant next to `APICURIO_IMAGE_TAG`, update it. If no such comment exists, no action required (the variable name is unchanged).

## 4. Bring the stack up and verify first-boot behavior

- [ ] 4.1 `make up`. Watch `docker logs -f schema-registry` and confirm the container reaches `healthy` within ~30s; expect log lines about Kafka producer/consumer initialization and journal replay.
- [ ] 4.2 Confirm the journal topic was auto-created with the correct cleanup policy: `docker exec kafka1 kafka-topics --bootstrap-server localhost:9092 --describe --topic kafkasql-journal` — output must include `cleanup.policy=compact`.
- [ ] 4.3 Apply the Debezium connector (if `make up` did not do it automatically): `make apply-pg-connector`. Confirm success with `make check-connector`.
- [ ] 4.4 Trigger CDC events by populating demo data: `make demo-data`. Confirm all six Apicurio subjects exist: `curl -s http://localhost:8081/subjects | jq` returns `pg.public.customers-key`, `pg.public.customers-value`, `pg.public.products-key`, `pg.public.products-value`, `pg.public.orders-key`, `pg.public.orders-value` (and may also include `io.debezium.connector.postgresql.Source`).

## 5. Persistence acceptance test

- [ ] 5.1 Snapshot the current subjects list: `curl -s http://localhost:8081/subjects | jq -S '.' > /tmp/subjects-before.json`.
- [ ] 5.2 Restart the registry container: `docker restart schema-registry`.
- [ ] 5.3 Wait for its healthcheck to return `healthy` (up to 30s + interval buffer).
- [ ] 5.4 Confirm subjects survived: `curl -s http://localhost:8081/subjects | jq -S '.' > /tmp/subjects-after.json && diff /tmp/subjects-before.json /tmp/subjects-after.json` — the diff MUST be empty.

## 6. Downstream sanity check

- [ ] 6.1 Start the three Spark CDC jobs in production mode: `make cdc-run-all-prod`.
- [ ] 6.2 Trigger another batch of demo data: `make demo-data`.
- [ ] 6.3 Verify rows landed in ClickHouse: `docker exec clickhouse clickhouse-client -q "SELECT count() FROM customers FINAL"` returns non-zero (same for `products` and `orders`). This confirms Spark's Confluent-compatible schema fetch still works against the kafkasql-backed registry.
- [ ] 6.4 Open Grafana at http://localhost:3000 and confirm CDC dashboards still populate.

## 7. Documented-destructive confirmation

- [ ] 7.1 Optionally verify the non-goal: `make down && make up`. Confirm the registry comes up empty (`curl -s http://localhost:8081/subjects | jq` returns `[]` before Debezium runs), then re-apply the connector and confirm re-registration works. This validates the scenario in the spec that documents `make down` as still-destructive.

## 8. Update memory / documentation cross-references

- [ ] 8.1 If any repo doc (`docs/governance.md`, `CLAUDE.md` service URLs section) explicitly names the `-mem` variant, update it. Grep first: `grep -rn "apicurio-registry-mem" .` — expect only the change proposal itself to remain.

## 9. Archive the change

- [ ] 9.1 Once the change is verified and merged, run `/opsx:archive switch-apicurio-kafkasql-persistence` (or the equivalent OpenSpec archive command) so the `schema-registry-persistence` requirement lands in `openspec/specs/data-governance/spec.md`.
