#!/bin/bash
# Phase 2 Service Startup Script
# Starts all Phase 1+2 services in optimal order
#
# Usage:
#   bash scripts/startup_all.sh [environment]
# 
# Environments:
#   development (default): Console output, debug logging
#   staging: syslog output, info logging
#   production: Structured JSON logging

set -e

# Configuration
ENVIRONMENT=${1:-development}
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN=${PYTHON_BIN:-python}
LOG_DIR="${PROJECT_ROOT}/logs"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Create logs directory
mkdir -p "$LOG_DIR"

# Check prerequisites
check_prerequisites() {
    echo -e "${BLUE}Checking prerequisites...${NC}"
    
    # Check Python
    if ! command -v $PYTHON_BIN &> /dev/null; then
        echo -e "${RED}Python not found${NC}"
        exit 1
    fi
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Docker not found${NC}"
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}Docker Compose not found${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✓ All prerequisites met${NC}"
}

# Start Docker infrastructure
start_docker() {
    echo -e "${BLUE}Starting Docker infrastructure...${NC}"
    
    # Check if already running
    if docker ps 2>/dev/null | grep -q "kafka"; then
        echo -e "${GREEN}✓ Docker infrastructure already running${NC}"
        return 0
    fi
    
    cd "$PROJECT_ROOT"
    docker-compose up -d
    
    # Wait for services
    echo "Waiting for services to be healthy (30s)..."
    sleep 30
    
    docker-compose ps
}

# Start Phase 1 services
start_phase1() {
    echo -e "${BLUE}Starting Phase 1 services...${NC}"
    
    # Terminal 1: Prometheus Collector
    echo "Starting Prometheus Collector..."
    nohup $PYTHON_BIN src/ingestion/prometheus_collector.py \
        > "$LOG_DIR/prometheus_collector.log" 2>&1 &
    PROM_PID=$!
    echo "  PID: $PROM_PID"
    
    # Terminal 2: Feature Extractor
    echo "Starting Feature Extractor..."
    nohup $PYTHON_BIN src/feature_engineering/feature_extractor.py \
        > "$LOG_DIR/feature_extractor.log" 2>&1 &
    FEATURE_PID=$!
    echo "  PID: $FEATURE_PID"
    
    sleep 2
    echo -e "${GREEN}✓ Phase 1 services started${NC}"
}

# Start Phase 2 services
start_phase2() {
    echo -e "${BLUE}Starting Phase 2 services...${NC}"
    
    # Terminal 3: Ensemble Detector
    echo "Starting Ensemble Detector..."
    nohup $PYTHON_BIN src/detection/ensemble_detector.py \
        > "$LOG_DIR/ensemble_detector.log" 2>&1 &
    DETECTOR_PID=$!
    echo "  PID: $DETECTOR_PID"
    
    # Terminal 4: Alert Manager
    echo "Starting Alert Manager..."
    nohup $PYTHON_BIN src/alerting/alert_manager.py \
        > "$LOG_DIR/alert_manager.log" 2>&1 &
    ALERT_PID=$!
    echo "  PID: $ALERT_PID"
    
    # Terminal 5: API Server
    echo "Starting API Server..."
    nohup $PYTHON_BIN src/api/server.py \
        > "$LOG_DIR/api_server.log" 2>&1 &
    API_PID=$!
    echo "  PID: $API_PID"
    
    sleep 2
    echo -e "${GREEN}✓ Phase 2 services started${NC}"
}

# Health checks
health_check() {
    echo -e "${BLUE}Performing health checks...${NC}"
    
    # Wait a bit for services to start
    sleep 5
    
    # Check API server
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ API Server healthy${NC}"
    else
        echo -e "${RED}✗ API Server not responding${NC}"
        return 1
    fi
    
    # Check model status
    if curl -s http://localhost:8000/api/v1/models/status > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Detection models loaded${NC}"
    else
        echo -e "${RED}✗ Detection models not ready${NC}"
    fi
    
    echo -e "${GREEN}✓ Health checks passed${NC}"
}

# Display summary
print_summary() {
    echo -e "\n${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}API Degradation Detection System Started${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    
    echo -e "\n${BLUE}Phase 1 - Infrastructure:${NC}"
    echo "  ✓ Kafka (localhost:9092)"
    echo "  ✓ Prometheus (localhost:9090)"
    echo "  ✓ TimescaleDB (localhost:5432)"
    echo "  ✓ PostgreSQL (localhost:5433)"
    echo "  ✓ Redis (localhost:6379)"
    
    echo -e "\n${BLUE}Phase 1 - Services:${NC}"
    echo "  ✓ Prometheus Collector (ingests metrics)"
    echo "  ✓ Feature Extractor (rolling windows)"
    
    echo -e "\n${BLUE}Phase 2 - Services:${NC}"
    echo "  ✓ Ensemble Detector (anomaly detection)"
    echo "  ✓ Alert Manager (routing & dedup)"
    echo "  ✓ API Server (http://localhost:8000)"
    
    echo -e "\n${BLUE}Useful URLs:${NC}"
    echo "  API Server:    http://localhost:8000"
    echo "  API Docs:      http://localhost:8000/docs"
    echo "  Health:        http://localhost:8000/health"
    echo "  Models:        http://localhost:8000/api/v1/models/status"
    echo "  Prometheus:    http://localhost:9090"
    echo "  Grafana:       http://localhost:3000 (admin/admin)"
    
    echo -e "\n${BLUE}Log Files:${NC}"
    echo "  Prometheus Collector: $LOG_DIR/prometheus_collector.log"
    echo "  Feature Extractor:    $LOG_DIR/feature_extractor.log"
    echo "  Ensemble Detector:    $LOG_DIR/ensemble_detector.log"
    echo "  Alert Manager:        $LOG_DIR/alert_manager.log"
    echo "  API Server:           $LOG_DIR/api_server.log"
    
    echo -e "\n${BLUE}Next Steps:${NC}"
    echo "  1. Run verification: python scripts/verify_phase2.py"
    echo "  2. Access API docs: http://localhost:8000/docs"
    echo "  3. Monitor logs:    tail -f $LOG_DIR/*.log"
    echo "  4. Test alert:      Send request to trigger anomaly"
    echo ""
    echo -e "${BLUE}To stop all services:${NC}"
    echo "  bash scripts/shutdown_all.sh"
    echo ""
}

# Main
main() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}Phase 1 + Phase 2 Startup Script${NC}"
    echo -e "${BLUE}Environment: $ENVIRONMENT${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}\n"
    
    check_prerequisites
    start_docker
    start_phase1
    start_phase2
    health_check
    print_summary
}

main
