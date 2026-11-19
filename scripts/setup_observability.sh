#!/usr/bin/env bash
# One-time setup: fetch the jmx_prometheus_javaagent jar used by the
# Debezium container as a sidecar for exposing Kafka Connect + Debezium
# JMX metrics on port 5556.
#
# The jar (~700KB) is NOT committed to the repo — it's a build-time
# dependency fetched from Maven Central. Rerun this script when bumping
# JMX_EXPORTER_VERSION below.

set -euo pipefail

JMX_EXPORTER_VERSION="${JMX_EXPORTER_VERSION:-0.20.0}"
TARGET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/infrastructure/docker/jmx-exporter"
JAR_NAME="jmx_prometheus_javaagent-${JMX_EXPORTER_VERSION}.jar"
JAR_PATH="${TARGET_DIR}/${JAR_NAME}"
MAVEN_URL="https://repo1.maven.org/maven2/io/prometheus/jmx/jmx_prometheus_javaagent/${JMX_EXPORTER_VERSION}/${JAR_NAME}"

mkdir -p "${TARGET_DIR}"

if [[ -f "${JAR_PATH}" ]]; then
    echo "PASS jmx-exporter jar already present at ${JAR_PATH}"
    exit 0
fi

echo "Fetching ${JAR_NAME} from Maven Central..."
if command -v curl >/dev/null 2>&1; then
    curl -fsSL -o "${JAR_PATH}" "${MAVEN_URL}"
elif command -v wget >/dev/null 2>&1; then
    wget -q -O "${JAR_PATH}" "${MAVEN_URL}"
else
    echo "FAILED neither curl nor wget available" >&2
    exit 1
fi

if [[ ! -s "${JAR_PATH}" ]]; then
    echo "FAILED download produced an empty file" >&2
    rm -f "${JAR_PATH}"
    exit 1
fi

echo "PASS downloaded ${JAR_PATH} ($(du -h "${JAR_PATH}" | cut -f1))"
