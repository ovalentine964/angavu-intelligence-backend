#!/bin/bash
# =============================================================================
# Angavu Intelligence Backend — Azure Deployment Script
# Deploys the full stack to Azure Free Tier:
#   - PostgreSQL Flexible Server
#   - Azure Cache for Redis (C0 Basic)
#   - Azure Container Registry
#   - Azure Container Apps
# =============================================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
RESOURCE_GROUP="${RESOURCE_GROUP:-angavu-rg}"
LOCATION="${LOCATION:-eastus}"
ACR_NAME="${ACR_NAME:-angavuacr}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
CONTAINER_APP_NAME="angavu-api"
ENVIRONMENT_NAME="angavu-env"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log()   { echo -e "${BLUE}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }

# ── Preflight checks ─────────────────────────────────────────────────────────
command -v az >/dev/null 2>&1 || error "Azure CLI not installed. See: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli"
command -v docker >/dev/null 2>&1 || error "Docker not installed."

# Check required environment variables
[ -z "${POSTGRES_ADMIN_PASSWORD:-}" ] && error "POSTGRES_ADMIN_PASSWORD is required (min 8 chars)."
[ -z "${ACR_NAME:-}" ] && error "ACR_NAME is required."

# Verify Azure login
az account show >/dev/null 2>&1 || error "Not logged in to Azure. Run: az login"

SUBSCRIPTION=$(az account show --query "name" -o tsv)
log "Using subscription: ${SUBSCRIPTION}"
log "Resource group: ${RESOURCE_GROUP}"
log "Location: ${LOCATION}"
log "ACR name: ${ACR_NAME}"
echo ""

# ── Step 1: Create Resource Group ────────────────────────────────────────────
log "Step 1/6: Creating resource group..."
if az group show --name "${RESOURCE_GROUP}" >/dev/null 2>&1; then
    ok "Resource group '${RESOURCE_GROUP}' already exists."
else
    az group create \
        --name "${RESOURCE_GROUP}" \
        --location "${LOCATION}" \
        --tags project=angavu-intelligence environment=production managedBy=script
    ok "Resource group created."
fi
echo ""

# ── Step 2: Deploy Bicep template ────────────────────────────────────────────
log "Step 2/6: Deploying infrastructure with Bicep..."

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

az deployment group create \
    --resource-group "${RESOURCE_GROUP}" \
    --template-file "${SCRIPT_DIR}/main.bicep" \
    --parameters \
        administratorLogin="${POSTGRES_ADMIN_USER:-angavu}" \
        administratorLoginPassword="${POSTGRES_ADMIN_PASSWORD}" \
        acrName="${ACR_NAME}" \
    --name "angavu-deploy-$(date +%Y%m%d%H%M%S)" \
    --no-prompt

ok "Infrastructure deployed."
echo ""

# ── Step 3: Get outputs ──────────────────────────────────────────────────────
log "Step 3/6: Retrieving deployment outputs..."

ACR_LOGIN_SERVER=$(az acr show --name "${ACR_NAME}" --query "loginServer" -o tsv)
ACR_PASSWORD=$(az acr credential show --name "${ACR_NAME}" --query "passwords[0].value" -o tsv)

PG_HOST=$(az postgres flexible-server show \
    --resource-group "${RESOURCE_GROUP}" \
    --name "angavu-pg" \
    --query "fullyQualifiedDomainName" -o tsv)

REDIS_HOST=$(az redis show \
    --resource-group "${RESOURCE_GROUP}" \
    --name "angavu-redis" \
    --query "hostName" -o tsv)

REDIS_KEY=$(az redis list-keys \
    --resource-group "${RESOURCE_GROUP}" \
    --name "angavu-redis" \
    --query "primaryKey" -o tsv)

ok "ACR: ${ACR_LOGIN_SERVER}"
ok "PostgreSQL: ${PG_HOST}"
ok "Redis: ${REDIS_HOST}"
echo ""

# ── Step 4: Build and push Docker image ──────────────────────────────────────
log "Step 4/6: Building and pushing Docker image..."

# Navigate to project root (3 levels up from deploy/azure/)
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Login to ACR
echo "${ACR_PASSWORD}" | docker login "${ACR_LOGIN_SERVER}" -u "${ACR_NAME}" --password-stdin

FULL_IMAGE="${ACR_LOGIN_SERVER}/angavu-backend:${IMAGE_TAG}"
log "Building: ${FULL_IMAGE}"

docker build \
    -t "${FULL_IMAGE}" \
    -f "${SCRIPT_DIR}/Dockerfile.azure" \
    "${PROJECT_ROOT}"

docker push "${FULL_IMAGE}"
ok "Image pushed: ${FULL_IMAGE}"
echo ""

# ── Step 5: Update Container App ─────────────────────────────────────────────
log "Step 5/6: Deploying to Container Apps..."

# Build connection strings
DATABASE_URL="postgresql://${POSTGRES_ADMIN_USER:-angavu}:${POSTGRES_ADMIN_PASSWORD}@${PG_HOST}:5432/angavu?sslmode=require"
REDIS_URL="rediss://:${REDIS_KEY}@${REDIS_HOST}:6380/0"

# Check if container app exists
if az containerapp show --name "${CONTAINER_APP_NAME}" --resource-group "${RESOURCE_GROUP}" >/dev/null 2>&1; then
    log "Updating existing Container App..."
    az containerapp update \
        --name "${CONTAINER_APP_NAME}" \
        --resource-group "${RESOURCE_GROUP}" \
        --image "${FULL_IMAGE}"
else
    log "Container App not found — it should have been created by Bicep. Checking environment..."
    ENV_ID=$(az containerapp env show \
        --name "${ENVIRONMENT_NAME}" \
        --resource-group "${RESOURCE_GROUP}" \
        --query "id" -o tsv 2>/dev/null || echo "")

    if [ -z "${ENV_ID}" ]; then
        error "Container Apps environment not found. Bicep deployment may have failed."
    fi

    log "Creating Container App..."
    az containerapp create \
        --name "${CONTAINER_APP_NAME}" \
        --resource-group "${RESOURCE_GROUP}" \
        --environment "${ENVIRONMENT_NAME}" \
        --image "${FULL_IMAGE}" \
        --registry-server "${ACR_LOGIN_SERVER}" \
        --registry-username "${ACR_NAME}" \
        --registry-password "${ACR_PASSWORD}" \
        --target-port 8000 \
        --ingress external \
        --min-replicas 0 \
        --max-replicas 3 \
        --cpu 0.5 \
        --memory 1.0Gi \
        --env-vars \
            "RUST_LOG=info" \
            "ANGAVU_HOST=0.0.0.0" \
            "ANGAVU_PORT=8000" \
            "ANALYTICS_BACKEND=postgresql" \
            "PYTHONPATH=/app/python" \
            "PYTHONUNBUFFERED=1" \
            "DATABASE_URL=${DATABASE_URL}" \
            "REDIS_URL=${REDIS_URL}"
fi

ok "Container App deployed."
echo ""

# ── Step 6: Verify deployment ────────────────────────────────────────────────
log "Step 6/6: Verifying deployment..."

APP_FQDN=$(az containerapp show \
    --name "${CONTAINER_APP_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --query "properties.configuration.ingress.fqdn" -o tsv)

ok "Container App URL: https://${APP_FQDN}"

log "Waiting for health check..."
HEALTHY=false
for i in $(seq 1 20); do
    STATUS=$(curl -sf -o /dev/null -w '%{http_code}' "https://${APP_FQDN}/health" 2>/dev/null || echo "000")
    if [ "${STATUS}" = "200" ]; then
        HEALTHY=true
        break
    fi
    echo "  Attempt ${i}/20: status=${STATUS}, retrying in 15s..."
    sleep 15
done

if [ "${HEALTHY}" = "true" ]; then
    ok "Health check passed! ✅"
else
    warn "Health check not yet passing. The app may still be starting."
    warn "Check logs: az containerapp logs show --name ${CONTAINER_APP_NAME} --resource-group ${RESOURCE_GROUP} --follow"
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "============================================="
echo "  Angavu Intelligence Backend — Azure Deploy  "
echo "============================================="
echo ""
echo "  App URL:      https://${APP_FQDN}"
echo "  Health:       https://${APP_FQDN}/health"
echo "  ACR:          ${ACR_LOGIN_SERVER}"
echo "  PostgreSQL:   ${PG_HOST}"
echo "  Redis:        ${REDIS_HOST}"
echo "  Resource Grp: ${RESOURCE_GROUP}"
echo ""
echo "  Logs:  az containerapp logs show --name ${CONTAINER_APP_NAME} --resource-group ${RESOURCE_GROUP} --follow"
echo "  Scale: az containerapp show --name ${CONTAINER_APP_NAME} --resource-group ${RESOURCE_GROUP}"
echo ""
echo "  To tear down:  az group delete --name ${RESOURCE_GROUP} --yes"
echo ""
