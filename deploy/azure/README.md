# Angavu Intelligence Backend — Azure Free Tier Deployment

## Overview

This guide walks you through deploying the Angavu Intelligence Backend (Rust/Axum + Python RAG service) to **Azure Free Tier** services.

> **⚠️ Important Limitations:** Azure Free Tier is very constrained. This setup is suitable for **development, demos, and low-traffic staging**. For production workloads, upgrade to paid tiers.

### Free Tier Resources Used

| Service | Free Tier Limit | Notes |
|---------|----------------|-------|
| **Azure Container Apps** | 180K vCPU-sec/mo, 360K GB-sec/mo | ~180 hrs/month at 0.25 vCPU |
| **Azure Database for PostgreSQL** | 32MB storage, 480 compute-min/mo | Very limited — see §Gotchas |
| **Azure Cache for Redis** | C0 Basic (25MB) | Minimal caching only |
| **Azure Container Registry** | Basic tier (~$0.17/day) | Not truly free; cheapest option |

### Architecture on Azure

```
┌─────────────────────────────────────────────────────┐
│  Azure Container Apps Environment                   │
│  ┌──────────────┐    ┌──────────────────────────┐   │
│  │  Container    │    │  Container               │   │
│  │  App          │    │  App                      │   │
│  │  (Rust/Axum   │───▶│  (Python RAG Sidecar)    │   │
│  │   port 8000)  │    │  (port 8001)              │   │
│  └──────┬───────┘    └──────────────────────────┘   │
│         │                                            │
└─────────┼────────────────────────────────────────────┘
          │
    ┌─────┴──────┐     ┌──────────────┐
    │ PostgreSQL  │     │ Redis C0     │
    │ Flexible    │     │ (25MB)       │
    │ Server      │     │              │
    └─────────────┘     └──────────────┘
```

> **ClickHouse is skipped.** It's not available as a free Azure service. Analytics queries use PostgreSQL with materialized views instead. See [Migrating from ClickHouse](#migrating-from-clickhouse-to-postgresql) below.

---

## Prerequisites

- [Azure account](https://azure.microsoft.com/free/) with free tier activated
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) installed (`az version`)
- [Docker](https://docs.docker.com/get-docker/) installed
- A GitHub repository with the Angavu backend code

---

## Step 1: Login and Set Subscription

```bash
# Login to Azure
az login

# List subscriptions and pick the free one
az account list --output table

# Set active subscription
az account set --subscription "<your-subscription-id>"
```

---

## Step 2: Run the Automated Deploy Script

The included `deploy.sh` automates everything:

```bash
cd deploy/azure

# Make executable
chmod +x deploy.sh

# Set required environment variables
export RESOURCE_GROUP="angavu-rg"
export LOCATION="eastus"               # or westeurope, southeastasia
export ACR_NAME="angavuacr"            # globally unique, 5-50 alphanumeric chars
export POSTGRES_ADMIN_USER="angavu"
export POSTGRES_ADMIN_PASSWORD="YourStr0ng!Pass"  # min 8 chars

# Deploy everything
./deploy.sh
```

The script will:
1. Create the resource group
2. Deploy PostgreSQL Flexible Server (free tier)
3. Deploy Azure Cache for Redis (C0 Basic)
4. Create Azure Container Registry
5. Build and push the Docker image
6. Deploy the Container App

---

## Step 3: Manual Deployment (Step-by-Step)

If you prefer to deploy manually or need to customize:

### 3a. Create Resource Group

```bash
az group create \
  --name angavu-rg \
  --location eastus
```

### 3b. Deploy Infrastructure with Bicep

```bash
az deployment group create \
  --resource-group angavu-rg \
  --template-file main.bicep \
  --parameters \
    administratorLogin="angavu" \
    administratorLoginPassword="YourStr0ng!Pass" \
    acrName="angavuacr" \
    containerAppImage="angavuacr.azurecr.io/angavu-backend:latest"
```

### 3c. Build and Push Docker Image

```bash
# Login to ACR
az acr login --name angavuacr

# Build the Azure-optimized image
docker build -t angavuacr.azurecr.io/angavu-backend:latest \
  -f Dockerfile.azure .

# Push
docker push angavuacr.azurecr.io/angavu-backend:latest
```

### 3d. Update the Container App

```bash
az containerapp update \
  --name angavu-api \
  --resource-group angavu-rg \
  --image angavuacr.azurecr.io/angavu-backend:latest
```

---

## Step 4: Configure Secrets and Environment Variables

```bash
# Set secrets in Container App
az containerapp secret set \
  --name angavu-api \
  --resource-group angavu-rg \
  --secrets \
    jwt-secret="<your-jwt-secret>" \
    encryption-key="<your-32-byte-key>" \
    deepseek-api-key="<your-key>" \
    qwen-api-key="<your-key>"

# Update environment variables to reference secrets
az containerapp update \
  --name angavu-api \
  --resource-group angavu-rg \
  --set-env-vars \
    JWT_SECRET=secretref:jwt-secret \
    ENCRYPTION_KEY=secretref:encryption-key \
    DEEPSEEK_API_KEY=secretref:deepseek-api-key \
    QWEN_API_KEY=secretref:qwen-api-key
```

---

## Step 5: Verify Deployment

```bash
# Get the Container App URL
az containerapp show \
  --name angavu-api \
  --resource-group angavu-rg \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv

# Health check
curl https://<your-app-url>/health

# View logs
az containerapp logs show \
  --name angavu-api \
  --resource-group angavu-rg \
  --follow
```

---

## Migrating from ClickHouse to PostgreSQL

Since ClickHouse isn't available on Azure Free Tier, analytics queries are routed to PostgreSQL.

### What Changes

1. **Set environment variable:**
   ```bash
   ANALYTICS_BACKEND=postgresql
   ```

2. **Run the analytics migration** (creates materialized views):
   ```bash
   # The migration file handles this automatically
   # See: migrations/ for analytics schema
   ```

3. **Code changes needed in Rust** (if not already handled):
   - The `CLICKHOUSE_URL` env var is left unset
   - Analytics modules fall back to PostgreSQL when `CLICKHOUSE_URL` is empty
   - Materialized views handle aggregation queries

### Performance Impact

| Query Type | ClickHouse | PostgreSQL (fallback) |
|-----------|-----------|----------------------|
| Simple aggregations | ~10ms | ~50ms |
| Complex analytics | ~100ms | ~500ms |
| Large table scans | Fast (columnar) | Slower (row-based) |

For a free-tier deployment with low traffic, PostgreSQL is adequate.

---

## GitHub Actions: Azure Deployment Workflow

Add the Azure deployment workflow to your CI/CD:

```yaml
# .github/workflows/deploy-azure.yml
# See the workflow file in this repo for the full configuration
```

### Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `AZURE_CREDENTIALS` | Service principal JSON (see below) |
| `AZURE_RESOURCE_GROUP` | `angavu-rg` |
| `AZURE_ACR_NAME` | `angavuacr` |
| `POSTGRES_ADMIN_PASSWORD` | PostgreSQL admin password |
| `JWT_SECRET` | JWT signing secret |
| `ENCRYPTION_KEY` | 32-byte encryption key |
| `DEEPSEEK_API_KEY` | DeepSeek API key |
| `QWEN_API_KEY` | Qwen API key |

### Create Service Principal for GitHub Actions

```bash
az ad sp create-for-rbac \
  --name "angavu-github-actions" \
  --role contributor \
  --scopes /subscriptions/<subscription-id>/resourceGroups/angavu-rg \
  --sdk-auth

# Copy the JSON output and add it as AZURE_CREDENTIALS secret in GitHub
```

---

## Cost Estimate

| Service | Monthly Cost (Free Tier) | After Free Tier |
|---------|-------------------------|-----------------|
| Container Apps | $0 (within limits) | ~$15-30/mo |
| PostgreSQL Flexible | $0 (within limits) | ~$12/mo (B1ms) |
| Redis C0 | $0 (within limits) | ~$16/mo |
| Container Registry | ~$5/mo (Basic) | ~$5/mo |
| **Total** | **~$5/mo** | **~$48-63/mo** |

> **Note:** Azure Container Registry Basic tier is ~$0.17/day and is the only service without a true free tier.

---

## Gotchas and Limitations

### PostgreSQL 32MB Storage Limit
The free tier PostgreSQL Flexible Server has only **32MB of storage**. This is enough for schema + minimal data, but will fill quickly with any real usage. Monitor with:

```bash
az postgres flexible-server show \
  --resource-group angavu-rg \
  --name angavu-pg \
  --query "storage.storageSizeGb"
```

**Mitigation:** Upgrade to Burstable B1ms (~$12/mo) for 32GB storage when needed.

### Redis 25MB Limit
The C0 Basic tier has 25MB. Session caching and rate limiting will work, but don't store large datasets.

### Container Apps Cold Start
Free tier containers scale to zero. First request after idle takes 5-10 seconds. Keep-alive pings prevent this but consume free quota.

### No Persistent Storage
Container Apps don't have persistent disk storage. Logs and temporary files are ephemeral. Use Azure Blob Storage for anything that needs to persist.

### ClickHouse Absence
Analytics performance is degraded. If analytics become critical, consider:
- Azure Data Explorer (expensive)
- Self-hosted ClickHouse on a separate VM
- TimescaleDB extension for PostgreSQL (free)

---

## Teardown

Delete everything to stop incurring costs:

```bash
# Delete the entire resource group (all resources)
az group delete --name angavu-rg --yes --no-wait

# Verify deletion
az group exists --name angavu-rg
```

---

## Troubleshooting

### Container won't start
```bash
az containerapp logs show --name angavu-api --resource-group angavu-rg --tail 50
```

### Database connection refused
- Check PostgreSQL firewall rules allow Azure services
- Verify `DATABASE_URL` format: `postgresql://user:pass@host:5432/dbname?sslmode=require`

### Image pull errors
```bash
# Re-login to ACR
az acr login --name angavuacr

# Verify image exists
az acr repository list --name angavuacr --output table
```

### Out of free tier quota
```bash
# Check Container Apps usage
az containerapp env show --name angavu-env --resource-group angavu-rg
```

---

## References

- [Azure Container Apps Free Tier](https://learn.microsoft.com/en-us/azure/container-apps/billing)
- [Azure PostgreSQL Flexible Server Free Tier](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concept-free)
- [Azure Cache for Redis Free Tier](https://learn.microsoft.com/en-us/azure/azure-cache-for-redis/cache-overview)
- [Bicep Documentation](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/)
