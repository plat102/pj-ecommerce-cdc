#!/usr/bin/env bash
# ClickHouse init hook: create the analyst_readonly user and grant the
# matching role that create_tables.sql defines.
#
# Runs once, on first container start, from
#   /docker-entrypoint-initdb.d/create_governance_users.sh
# The password is read from $CLICKHOUSE_ANALYST_PASSWORD (set in
# infrastructure/docker/.env and forwarded via docker-compose.analytics.yml)
# so no secrets land in the SQL init file.

set -euo pipefail

: "${CLICKHOUSE_ANALYST_PASSWORD:?CLICKHOUSE_ANALYST_PASSWORD must be set for the analyst_readonly user}"

clickhouse-client --multiquery <<SQL
CREATE USER IF NOT EXISTS analyst_readonly
    IDENTIFIED WITH sha256_password BY '${CLICKHOUSE_ANALYST_PASSWORD}'
    DEFAULT ROLE analyst_readonly;

GRANT analyst_readonly TO analyst_readonly;
SQL
