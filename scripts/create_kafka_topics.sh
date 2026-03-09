#!/bin/bash

# Kafka Topics Creation Script
#
# Creates all required Kafka topics with appropriate configurations.
# This script should be run after Kafka is up and running.
#
# Usage:
#   bash scripts/create_kafka_topics.sh
#
# Or run via Docker:
#   docker exec kafka bash -c 'kafka-topics --create --bootstrap-server localhost:9092 ...'

set -e

KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS:-localhost:9092}"
REPLICATION_FACTOR=1  # Set to 3 for production
NUM_PARTITIONS=3

echo "Creating Kafka topics..."
echo "Bootstrap servers: $KAFKA_BOOTSTRAP_SERVERS"

# Function to create topic
create_topic() {
    local topic_name=$1
    local partitions=$2
    local retention_ms=$3
    
    echo "Creating topic: $topic_name"
    
    kafka-topics \
        --create \
        --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
        --topic "$topic_name" \
        --partitions "$partitions" \
        --replication-factor "$REPLICATION_FACTOR" \
        --config "retention.ms=$retention_ms" \
        --if-not-exists
}

# 7 days = 604800000 ms
RETENTION_7_DAYS=604800000

# 30 days = 2592000000 ms
RETENTION_30_DAYS=2592000000

# 90 days = 7776000000 ms
RETENTION_90_DAYS=7776000000

# Create topics with their respective retention policies

# Raw metrics from Prometheus (high volume, 7 days retention)
create_topic "raw-metrics" "$NUM_PARTITIONS" "$RETENTION_7_DAYS"

# Extracted features for ML (high volume, 7 days retention)
create_topic "feature-store" "$NUM_PARTITIONS" "$RETENTION_7_DAYS"

# Detected anomalies (medium volume, 30 days retention)
create_topic "anomalies" 3 "$RETENTION_30_DAYS"

# Generated alerts (low volume, 90 days retention)
create_topic "alerts" 2 "$RETENTION_90_DAYS"

# Root cause analysis results (low volume, 90 days retention)
create_topic "root-causes" 2 "$RETENTION_90_DAYS"

# System events for monitoring
create_topic "system-events" 2 "$RETENTION_30_DAYS"

# Model predictions and evaluations
create_topic "model-predictions" 2 "$RETENTION_90_DAYS"

echo ""
echo "All Kafka topics created successfully!"
echo ""
echo "Listing all topics:"
kafka-topics \
    --list \
    --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS"

echo ""
echo "Topic details:"
kafka-topics \
    --describe \
    --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS"
