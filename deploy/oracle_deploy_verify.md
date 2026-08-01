# Oracle Free Tier Deploy Script — Verification Report

**Date:** 2026-08-01  
**Script:** `deploy/oracle-setup.sh`  
**Status:** ✅ FIXED — 9 critical issues found and resolved  

---

## Summary

The original deploy script had **9 issues** that would have prevented successful deployment on Oracle Free Tier ARM64. All have been fixed and pushed.

---

## Critical Issues Found & Fixed

### 1. 🔴 Binary Name Mismatch (WOULD FAIL)
- **Problem:** Systemd service referenced `angavu-intelligence-backend` but `Cargo.toml` defines the binary as `angavu-server`
- **Impact:** Service would fail to start — "ExecStart binary not found"
- **Fix:** Changed `ExecStart` to `$INSTALL_DIR/target/release/angavu-server`

### 2. 🔴 Environment Variable Mismatch (WOULD BIND WRONG PORT)
- **Problem:** Script set `BIND_ADDR=0.0.0.0:8080` but `main.rs` reads `ANGAVU_HOST` and `ANGAVU_PORT` separately
- **Impact:** App would ignore the .env file, bind to default `0.0.0.0:8000` instead of `:8080`, health check on `:8080` would fail
- **Fix:** Changed .env to use `ANGAVU_HOST=0.0.0.0` and `ANGAVU_PORT=8080`

### 3. 🔴 Migrations Path Wrong (WOULD FAIL)
- **Problem:** Script ran `sqlx migrate run --source rust-api/migrations` but migrations are at repo root `migrations/`
- **Impact:** `sqlx-cli` would not find any migration files
- **Fix:** Replaced with the built-in `angavu-migrate` binary (defined in `Cargo.toml`), which correctly reads from `migrations/`

### 4. 🔴 SQLx Compile-Time Query Checks (BUILD WOULD FAIL)
- **Problem:** `Cargo.toml` uses `sqlx` with compile-time query verification, but there's no `.sqlx/` directory in the repo. Without a running database during build, `cargo build` fails
- **Impact:** Build hangs or errors out trying to connect to DB
- **Fix:** Added `SQLX_OFFLINE=true` environment variable before `cargo build`

### 5. 🟡 pgvector Extension Not Installed (DEGRADED)
- **Problem:** Script ran `CREATE EXTENSION IF NOT EXISTS vector` but never installed pgvector. Default Ubuntu PostgreSQL packages don't include it
- **Impact:** Extension creation fails silently; vector search features degrade
- **Fix:** Added PGDG repo install + `postgresql-16-pgvector` apt package, with build-from-source fallback for ARM64

### 6. 🟡 Missing python3-dev (BUILD MAY FAIL)
- **Problem:** `Cargo.toml` depends on `pyo3 = "0.22"` which requires Python development headers
- **Impact:** `cargo build` fails with "Python not found" or missing headers
- **Fix:** Added `python3-dev python3-pip` to apt install list

### 7. 🟡 No Firewall Rules (SECURITY RISK)
- **Problem:** Script never configured UFW. Oracle Cloud instances have both cloud-level and OS-level firewalls
- **Impact:** Port 8080 may be blocked; service unreachable from outside
- **Fix:** Added UFW rules: `ufw allow 22/tcp` and `ufw allow 8080/tcp`

### 8. 🟡 ClickHouse Repo Not ARM64-Aware
- **Problem:** Deb repo line didn't specify `arch=`, may pull wrong packages
- **Fix:** Added `arch=$ARCH` parameter using `dpkg --print-architecture`

### 9. 🟡 Cargo Env Not Sourced in Piped Mode
- **Problem:** When script is piped via `curl | bash`, `$HOME/.cargo/env` sourcing can fail
- **Fix:** Added explicit `CARGO_HOME` and `RUSTUP_HOME` export with fallbacks

---

## Verified Working

| Check | Status | Notes |
|-------|--------|-------|
| `bash -n` syntax check | ✅ Pass | No syntax errors |
| Binary name `angavu-server` in Cargo.toml | ✅ Matches | `[[bin]] name = "angavu-server"` |
| Binary name `angavu-migrate` in Cargo.toml | ✅ Exists | Used for migrations |
| `rust-api/src/main.rs` reads .env | ✅ Via systemd | Uses `std::env::var()`, no dotenvy |
| Binds to 0.0.0.0 | ✅ Correct | `ANGAVU_HOST` defaults to `0.0.0.0` |
| `/health` endpoint exists | ✅ Yes | `telemetry/health.rs` — returns `{"status":"ok"}` |
| Migrations at repo root | ✅ Yes | `migrations/` dir with 16 SQL files |
| `set -euo pipefail` | ✅ Correct | Fails fast on errors |
| DB password generation | ✅ Secure | `openssl rand -hex 16` = 128-bit |
| JWT secret generation | ✅ Secure | `openssl rand -hex 32` = 256-bit |

---

## Remaining Recommendations (Not Script Bugs)

### SSL/TLS (Manual Step)
The script deploys HTTP only. For production, add a reverse proxy (nginx) with certbot:
```bash
sudo apt install nginx certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```
The script now prints this guidance at the end.

### Oracle Cloud Firewall
Oracle Cloud has a **separate network security group** in the web console. Users must also add an ingress rule for TCP 8080 in:
**Oracle Console → Networking → Virtual Cloud Networks → Security Lists → Add Ingress Rules**

### ARM64 Build Time
First `cargo build --release` on 4 ARM cores with LTO=fat will take **15-25 minutes**. The script prints progress. Subsequent builds are cached.

### RAM Usage
With 24GB on Oracle Free Tier, the build should be fine. The `lto = "fat"` + `codegen-units = 1` settings maximize binary performance but increase build time and memory.

---

## Changes Committed

```
commit 14c0b89
fix(deploy): critical fixes for oracle-setup.sh
- Fix binary name: angavu-server (not angavu-intelligence-backend)
- Fix env vars: ANGAVU_HOST/ANGAVU_PORT (not BIND_ADDR)
- Fix migrations path: use angavu-migrate binary, not sqlx-cli
- Add SQLX_OFFLINE=true for build (no .sqlx in repo)
- Add python3-dev for PyO3 dependency
- Add pgvector build-from-source fallback for ARM64
- Add UFW firewall rules (port 8080)
- Add arch= parameter for ClickHouse deb repo
- Fix cargo env sourcing for piped execution
- Add SSL setup guidance in output
- Add better error diagnostics on failure
```

Pushed to `main` branch.
