# Website Migration Plan: GitHub Pages → Cloudflare Pages

## Executive Summary

Migrate the Angavu marketing site from GitHub Pages to Cloudflare Pages to:
- Remove 100GB/month bandwidth limit
- Gain global CDN with 300+ edge locations
- Enable custom domain with free SSL
- Add CDN-backed APK distribution
- Reduce latency for Kenyan users (Cloudflare has Nairobi POP)

## Current State

| Aspect | GitHub Pages | Cloudflare Pages |
|--------|-------------|-----------------|
| Bandwidth | 100GB/month limit | Unlimited (free tier) |
| Build | GitHub Actions | Cloudflare Workers |
| CDN | Fastly (limited) | 300+ global POPs |
| Custom Domain | Yes (manual SSL) | Yes (auto SSL) |
| APK Hosting | Not suitable | R2 Storage + CDN |
| Cost | Free | Free tier sufficient |

## Migration Steps

### Phase 1: Setup Cloudflare Pages (Day 1)

1. **Create Cloudflare account** → `dash.cloudflare.com`
2. **Connect GitHub repo** → Cloudflare Pages → Connect to Git
3. **Configure build settings:**
   - Framework: Static HTML (or Next.js/Hugo if applicable)
   - Build command: (leave empty for static)
   - Build output directory: `/` or `/dist`
4. **Custom domain:**
   - Add `angavu.com` in Cloudflare DNS
   - Cloudflare auto-provisions SSL certificate
   - Update nameservers at registrar to Cloudflare's

### Phase 2: APK Distribution via R2 (Day 2)

1. **Create R2 bucket:** `angavu-releases`
2. **Enable public access** with custom domain: `releases.angavu.com`
3. **Upload APK files:**
   ```bash
   # Install Wrangler CLI
   npm install -g wrangler
   wrangler login

   # Upload APK
   wrangler r2 object put angavu-releases/app/angavu-v1.0.0.apk \
     --file=./build/angavu-v1.0.0.apk \
     --content-type application/vnd.android.package-archive
   ```
4. **Set cache headers** for APK files (cache 1 hour for latest, immutable for versioned)

### Phase 3: DNS Cutover (Day 3)

1. **Lower DNS TTL** to 300s (5 min) 24h before migration
2. **Update DNS records:**
   ```
   angavu.com      → Cloudflare Pages (proxied)
   www.angavu.com  → CNAME angavu.com (proxied)
   api.angavu.com  → Oracle Cloud IP (DNS only, no proxy)
   releases.angavu.com → R2 bucket (proxied)
   ```
3. **Verify SSL** is active in Cloudflare dashboard
4. **Test all endpoints**

### Phase 4: Cleanup (Day 4+)

1. **Remove GitHub Pages** deployment from repo settings
2. **Update CI/CD** to deploy to Cloudflare Pages on push
3. **Monitor** Cloudflare Analytics for bandwidth and performance
4. **Remove old GitHub Pages workflow** if exists

## Rollback Plan

1. **Keep GitHub Pages active** for 7 days after migration
2. **Revert DNS** to GitHub Pages if issues found
3. **GitHub Pages remains** as backup deployment target

## Post-Migration Checklist

- [ ] `angavu.com` loads from Cloudflare
- [ ] SSL certificate valid (auto-renewed)
- [ ] APK download works from `releases.angavu.com`
- [ ] API endpoints still work (`api.angavu.com`)
- [ ] Analytics tracking functional
- [ ] No mixed content warnings
- [ ] Lighthouse score ≥ 90
- [ ] Cloudflare WAF rules configured
- [ ] Rate limiting on download endpoints
