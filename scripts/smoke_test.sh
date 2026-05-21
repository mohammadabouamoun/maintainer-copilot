#!/usr/bin/env bash
# scripts/smoke_test.sh
# Quick end-to-end smoke tests against the running FastAPI backend.
# Exits non-zero on any failure.

set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"

pass=0
fail=0

check() {
    local description="$1"
    local expected_status="$2"
    local actual_status="$3"

    if [ "$actual_status" -eq "$expected_status" ]; then
        echo "  ✅ PASS: $description (HTTP $actual_status)"
        pass=$((pass + 1))
    else
        echo "  ❌ FAIL: $description (expected HTTP $expected_status, got $actual_status)"
        fail=$((fail + 1))
    fi
}

echo ""
echo "=== Smoke Tests against $API_URL ==="
echo ""

# 1. Health check
status=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health")
check "GET /health returns 200" 200 "$status"

# 2. OpenAPI schema accessible
status=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/docs")
check "GET /docs (OpenAPI UI) returns 200" 200 "$status"

# 3. Widget.js loader served
status=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/widget.js")
check "GET /widget.js returns 200" 200 "$status"

# 4. Auth registration endpoint reachable
status=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$API_URL/auth/register" \
    -H "Content-Type: application/json" \
    -d '{"email":"smoke_'"$(date +%s)"'@test.com","password":"SmokeTest123!","role":"user"}')
check "POST /auth/register returns 201" 201 "$status"

# 5. Unauthenticated POST to /chat/message returns 422 (no body) not 500
status=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$API_URL/chat/message" \
    -H "Content-Type: application/json" \
    -d '{}')
check "POST /chat/message with empty body returns 4xx (not 5xx)" 422 "$status"

echo ""
echo "=== Results: $pass passed, $fail failed ==="
echo ""

if [ "$fail" -gt 0 ]; then
    echo "❌ Smoke tests FAILED."
    exit 1
fi

echo "✅ All smoke tests passed."
