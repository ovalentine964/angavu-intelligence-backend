#!/bin/bash
# =============================================================
# Angavu Intelligence — Canary Deploy Script
# =============================================================
# Wraps the DeploymentHarness API for CLI-based canary deployments.
#
# Usage:
#   bash scripts/canary-deploy.sh \
#     --component IntelligenceGenerator \
#     --old v1.2 --new v1.3
#
#   bash scripts/canary-deploy.sh --status <deployment_id>
#   bash scripts/canary-deploy.sh --rollback <deployment_id>
#   bash scripts/canary-deploy.sh --versions
#   bash scripts/canary-deploy.sh --flags
#   bash scripts/canary-deploy.sh --metrics
#
# Canary stages: 1% → 10% → 50% → 100%
# Auto-rollback: error rate >1% or latency >2x baseline
# =============================================================

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log()   { echo -e "${GREEN}[CANARY]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Configuration ───────────────────────────────────────────
API_HOST="${ANGAVU_API_HOST:-http://localhost:8000}"
API_PREFIX="${API_V1_PREFIX:-/api/v1}"
DEPLOY_URL="${API_HOST}${API_PREFIX}/deploy"

# ── Parse arguments ─────────────────────────────────────────
ACTION=""
COMPONENT=""
OLD_VERSION=""
NEW_VERSION=""
DEPLOYMENT_ID=""
METADATA="{}"

while [[ $# -gt 0 ]]; do
    case $1 in
        --component)    COMPONENT="$2"; shift 2 ;;
        --old)          OLD_VERSION="$2"; shift 2 ;;
        --new)          NEW_VERSION="$2"; shift 2 ;;
        --status)       ACTION="status"; DEPLOYMENT_ID="$2"; shift 2 ;;
        --rollback)     ACTION="rollback"; DEPLOYMENT_ID="$2"; shift 2 ;;
        --pause)        ACTION="pause"; DEPLOYMENT_ID="$2"; shift 2 ;;
        --resume)       ACTION="resume"; DEPLOYMENT_ID="$2"; shift 2 ;;
        --active)       ACTION="active"; shift ;;
        --history)      ACTION="history"; shift ;;
        --versions)     ACTION="versions"; shift ;;
        --routes)       ACTION="routes"; shift ;;
        --flags)        ACTION="flags"; shift ;;
        --metrics)      ACTION="metrics"; shift ;;
        --health)       ACTION="health"; shift ;;
        --start)        ACTION="start"; shift ;;
        --metadata)     METADATA="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Deployment Lifecycle:"
            echo "  --start --component <name> --old <ver> --new <ver>  Start canary deploy"
            echo "  --status <deployment_id>                             Check deployment status"
            echo "  --pause <deployment_id>                              Pause deployment"
            echo "  --resume <deployment_id>                             Resume deployment"
            echo "  --rollback <deployment_id>                           Rollback deployment"
            echo ""
            echo "Monitoring:"
            echo "  --active     List active deployments"
            echo "  --history    Deployment history"
            echo "  --versions   Version map (which version serves what %)"
            echo "  --routes     Traffic routes"
            echo "  --metrics    Deployment metrics (error rate, latency, throughput)"
            echo "  --flags      Feature flags"
            echo "  --health     Harness health"
            echo ""
            echo "Options:"
            echo "  --metadata '{\"key\":\"val\"}'  Deployment metadata (JSON)"
            echo ""
            echo "Environment:"
            echo "  ANGAVU_API_HOST   API host (default: http://localhost:8000)"
            echo "  API_V1_PREFIX     API prefix (default: /api/v1)"
            exit 0
            ;;
        *) error "Unknown option: $1. Use --help for usage." ;;
    esac
done

# ── Helper: API call ────────────────────────────────────────
api_get() {
    local path="$1"
    curl -sf "${DEPLOY_URL}${path}" 2>/dev/null || error "API call failed: GET ${path}"
}

api_post() {
    local path="$1"
    local data="${2:-{}}"
    curl -sf -X POST "${DEPLOY_URL}${path}" \
        -H "Content-Type: application/json" \
        -d "$data" 2>/dev/null || error "API call failed: POST ${path}"
}

api_delete() {
    local path="$1"
    curl -sf -X DELETE "${DEPLOY_URL}${path}" 2>/dev/null || error "API call failed: DELETE ${path}"
}

# Pretty print JSON (requires python3 or jq)
pp() {
    if command -v jq &>/dev/null; then
        echo "$1" | jq .
    elif command -v python3 &>/dev/null; then
        echo "$1" | python3 -m json.tool 2>/dev/null || echo "$1"
    else
        echo "$1"
    fi
}

# ── Actions ─────────────────────────────────────────────────

case "$ACTION" in
    start)
        [ -z "$COMPONENT" ] && error "Missing --component"
        [ -z "$OLD_VERSION" ] && error "Missing --old"
        [ -z "$NEW_VERSION" ] && error "Missing --new"

        log "Starting canary deployment..."
        log "  Component:  $COMPONENT"
        log "  Old:        $OLD_VERSION"
        log "  New:        $NEW_VERSION"
        log "  Stages:     1% → 10% → 50% → 100%"
        log "  Thresholds: error rate ≤1%, latency ≤2x baseline"
        echo ""

        RESPONSE=$(api_post "/start" "{
            \"component\": \"$COMPONENT\",
            \"old_version\": \"$OLD_VERSION\",
            \"new_version\": \"$NEW_VERSION\",
            \"metadata\": $METADATA
        }")

        log "Deployment started:"
        pp "$RESPONSE"

        # Extract deployment ID
        DEPLOY_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['deployment']['deployment_id'])" 2>/dev/null || echo "")
        if [ -n "$DEPLOY_ID" ]; then
            echo ""
            log "Track with: $0 --status $DEPLOY_ID"
            log "Rollback:   $0 --rollback $DEPLOY_ID"
        fi
        ;;

    status)
        [ -z "$DEPLOYMENT_ID" ] && error "Missing deployment ID"
        RESPONSE=$(api_get "/status/$DEPLOYMENT_ID")
        pp "$RESPONSE"
        ;;

    pause)
        [ -z "$DEPLOYMENT_ID" ] && error "Missing deployment ID"
        RESPONSE=$(api_post "/pause/$DEPLOYMENT_ID")
        pp "$RESPONSE"
        ;;

    resume)
        [ -z "$DEPLOYMENT_ID" ] && error "Missing deployment ID"
        RESPONSE=$(api_post "/resume/$DEPLOYMENT_ID")
        pp "$RESPONSE"
        ;;

    rollback)
        [ -z "$DEPLOYMENT_ID" ] && error "Missing deployment ID"
        warn "Rolling back deployment $DEPLOYMENT_ID..."
        RESPONSE=$(api_post "/rollback/$DEPLOYMENT_ID" '{"reason":"manual_cli"}')
        pp "$RESPONSE"
        ;;

    active)
        RESPONSE=$(api_get "/active")
        pp "$RESPONSE"
        ;;

    history)
        RESPONSE=$(api_get "/history")
        pp "$RESPONSE"
        ;;

    versions)
        log "Version map (which version serves what % of traffic):"
        RESPONSE=$(api_get "/versions")
        pp "$RESPONSE"
        echo ""
        log "Currently serving versions:"
        RESPONSE=$(api_get "/versions/serving")
        pp "$RESPONSE"
        ;;

    routes)
        RESPONSE=$(api_get "/routes")
        pp "$RESPONSE"
        ;;

    metrics)
        log "Deployment metrics (error rate, latency, throughput per version):"
        RESPONSE=$(api_get "/metrics")
        pp "$RESPONSE"
        ;;

    flags)
        RESPONSE=$(api_get "/flags")
        pp "$RESPONSE"
        ;;

    health)
        log "Deployment Harness health:"
        RESPONSE=$(api_get "/health")
        pp "$RESPONSE"
        ;;

    "")
        # Default: show health
        log "Deployment Harness health:"
        RESPONSE=$(api_get "/health")
        pp "$RESPONSE"
        ;;
esac
