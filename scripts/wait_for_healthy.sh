#!/usr/bin/env bash
# scripts/wait_for_healthy.sh
# Polls all required services until they are healthy or times out after 60s.

set -euo pipefail

TIMEOUT=60
INTERVAL=3

wait_for() {
    local name="$1"
    local cmd="$2"
    local elapsed=0

    echo "⏳ Waiting for $name to be healthy..."
    until eval "$cmd" &>/dev/null; do
        if [ $elapsed -ge $TIMEOUT ]; then
            echo "❌ Timed out waiting for $name after ${TIMEOUT}s"
            exit 1
        fi
        sleep $INTERVAL
        elapsed=$((elapsed + INTERVAL))
    done
    echo "✅ $name is healthy"
}

# PostgreSQL
wait_for "PostgreSQL" \
    "docker compose exec -T db pg_isready -U user -d dbname"

# Redis
wait_for "Redis" \
    "docker compose exec -T redis redis-cli ping"

# MinIO
wait_for "MinIO" \
    "curl -sf http://localhost:9002/minio/health/live"

# Vault
wait_for "Vault" \
    "curl -sf http://localhost:8200/v1/sys/health"

echo ""
echo "🚀 All services are healthy. Proceeding with CI pipeline."
