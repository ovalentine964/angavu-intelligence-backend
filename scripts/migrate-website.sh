#!/bin/bash
# =============================================================================
# Angavu — Website Migration Script
# Migrates marketing site from GitHub Pages to Cloudflare Pages
# =============================================================================

set -euo pipefail

# Configuration
CLOUDFLARE_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-}"
CLOUDFLARE_API_TOKEN="${CLOUDFLARE_API_TOKEN:-}"
PROJECT_NAME="${CLOUDFLARE_PAGES_PROJECT:-angavu-website}"
DOMAIN="${DOMAIN:-angavu.com}"
R2_BUCKET="${R2_BUCKET:-angavu-releases}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[MIGRATE]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Pre-flight Checks ────────────────────────────────────────────────────────
preflight() {
    log "Running pre-flight checks..."

    if [ -z "$CLOUDFLARE_ACCOUNT_ID" ]; then
        error "CLOUDFLARE_ACCOUNT_ID not set"
        exit 1
    fi

    if [ -z "$CLOUDFLARE_API_TOKEN" ]; then
        error "CLOUDFLARE_API_TOKEN not set"
        exit 1
    fi

    # Check wrangler CLI
    if ! command -v wrangler &> /dev/null; then
        log "Installing wrangler CLI..."
        npm install -g wrangler
    fi

    # Verify Cloudflare auth
    if ! wrangler whoami &> /dev/null; then
        error "Wrangler not authenticated. Run: wrangler login"
        exit 1
    fi

    log "Pre-flight checks passed ✓"
}

# ── Step 1: Create Cloudflare Pages Project ──────────────────────────────────
setup_pages() {
    log "Setting up Cloudflare Pages project: ${PROJECT_NAME}"

    # Create Pages project via API
    curl -s -X POST \
        "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/pages/projects" \
        -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"${PROJECT_NAME}\",
            \"production_branch\": \"main\"
        }" | jq -r '.result.name' || warn "Project may already exist"

    log "Pages project ready ✓"
}

# ── Step 2: Setup R2 Bucket for APK Distribution ─────────────────────────────
setup_r2() {
    log "Setting up R2 bucket: ${R2_BUCKET}"

    # Create R2 bucket
    wrangler r2 bucket create "${R2_BUCKET}" 2>/dev/null || warn "Bucket may already exist"

    # Enable public access via custom domain
    log "Configure R2 custom domain: releases.${DOMAIN}"
    log "→ Go to Cloudflare Dashboard → R2 → ${R2_BUCKET} → Settings → Public Access"
    log "→ Add custom domain: releases.${DOMAIN}"

    log "R2 bucket ready ✓"
}

# ── Step 3: Configure Custom Domain ──────────────────────────────────────────
configure_domain() {
    log "Configuring custom domain: ${DOMAIN}"

    # Add custom domain to Pages project
    curl -s -X POST \
        "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/pages/projects/${PROJECT_NAME}/domains" \
        -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"${DOMAIN}\"}" | jq '.' || warn "Domain may already be configured"

    # Add www subdomain
    curl -s -X POST \
        "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/pages/projects/${PROJECT_NAME}/domains" \
        -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"www.${DOMAIN}\"}" | jq '.' || warn "WWW domain may already be configured"

    log "Custom domain configured ✓"
}

# ── Step 4: Deploy Site ──────────────────────────────────────────────────────
deploy_site() {
    local site_dir="${1:-.}"
    log "Deploying site from: ${site_dir}"

    # Deploy to Cloudflare Pages
    wrangler pages deploy "${site_dir}" \
        --project-name="${PROJECT_NAME}" \
        --branch=main \
        --commit-dirty=true

    log "Site deployed ✓"
}

# ── Step 5: Upload APK to R2 ─────────────────────────────────────────────────
upload_apk() {
    local apk_path="$1"
    local version="$2"

    if [ ! -f "$apk_path" ]; then
        error "APK file not found: ${apk_path}"
        return 1
    fi

    log "Uploading APK: ${apk_path} → r2://${R2_BUCKET}/app/angavu-${version}.apk"

    # Upload versioned APK
    wrangler r2 object put "${R2_BUCKET}/app/angavu-${version}.apk" \
        --file="${apk_path}" \
        --content-type="application/vnd.android.package-archive"

    # Upload as latest (overwrite)
    wrangler r2 object put "${R2_BUCKET}/app/angavu-latest.apk" \
        --file="${apk_path}" \
        --content-type="application/vnd.android.package-archive"

    log "APK uploaded ✓"
    log "Download URLs:"
    log "  https://releases.${DOMAIN}/app/angavu-${version}.apk"
    log "  https://releases.${DOMAIN}/app/angavu-latest.apk"
}

# ── Step 6: Update DNS ───────────────────────────────────────────────────────
update_dns() {
    log "DNS Configuration Required:"
    log ""
    log "  1. Add CNAME record for ${DOMAIN} → ${PROJECT_NAME}.pages.dev"
    log "  2. Add CNAME record for www.${DOMAIN} → ${PROJECT_NAME}.pages.dev"
    log "  3. Add CNAME record for releases.${DOMAIN} → ${R2_BUCKET}.r2.dev"
    log "  4. Keep A record for api.${DOMAIN} → Oracle Cloud IP"
    log ""
    log "  → Cloudflare Dashboard → DNS → Records"
    log "  → Enable proxy (orange cloud) for web domains"
    log "  → Disable proxy (grey cloud) for api.${DOMAIN}"
}

# ── Main ──────────────────────────────────────────────────────────────────────
usage() {
    echo "Usage: $0 <command> [args]"
    echo ""
    echo "Commands:"
    echo "  preflight              Run pre-flight checks"
    echo "  setup                  Setup Cloudflare Pages + R2"
    echo "  deploy <dir>           Deploy site from directory"
    echo "  upload-apk <apk> <ver> Upload APK to R2"
    echo "  dns                    Show DNS configuration"
    echo "  full <dir>             Run full migration"
    exit 1
}

COMMAND="${1:-}"
shift || true

case "$COMMAND" in
    preflight)    preflight ;;
    setup)        preflight; setup_pages; setup_r2; configure_domain ;;
    deploy)       preflight; deploy_site "${1:-.}" ;;
    upload-apk)   preflight; upload_apk "${1:-}" "${2:-v0.0.0}" ;;
    dns)          update_dns ;;
    full)         preflight; setup_pages; setup_r2; configure_domain; deploy_site "${1:-.}"; update_dns ;;
    *)            usage ;;
esac
