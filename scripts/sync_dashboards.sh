#!/bin/bash

# Sync Grafana dashboards from source to provisioning
echo "🔄 Syncing Grafana dashboards..."

SOURCE_DIR="data-platform/dashboards/grafana"
TARGET_DIR="infrastructure/docker/grafana/provisioning/dashboards/files"

# Create target directory if it doesn't exist
mkdir -p "$TARGET_DIR"

# Copy all dashboard files
cp "$SOURCE_DIR"/*.json "$TARGET_DIR/"

echo "✅ Dashboards synced successfully!"
echo "📁 Source: $SOURCE_DIR"
echo "📁 Target: $TARGET_DIR"

# List copied files
echo "📊 Synced dashboards:"
ls -la "$TARGET_DIR"/*.json
