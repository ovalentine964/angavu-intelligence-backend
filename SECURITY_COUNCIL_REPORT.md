# Angavu Intelligence Backend — Security Council Report
## Backend Security Council Assessment

**Date:** 2026-08-03  
**Scope:** Full privacy, security, and compliance audit  
**Status:** Production-grade with identified gaps  

---

## 1. Privacy Mechanism Inventory

### 1.1 Differential Privacy Engine
**Location:** `rust-api/src/statistical/differential_privacy.rs`  
**Status:** ✅ Fully Implemented

| Property | Value |
|----------|-------|
| Default ε | 0.1 (strong privacy) |
| Max budget | 10.0 per session |
| Mechanisms | Laplace (ε,0)-DP + Gaussian (ε,δ)-DP |
| Budget tracking | Cumulative, per-session |
| Suppression | Queries blocked when budget exhausted |

**Implementation Quality:**
- Laplace mechanism correctly implements `result = true_value + Laplace(0, sensitivity/ε)`
- Gaussian mechanism correctly calibrates noise: `σ = Δf × √(2 × ln(1.25/δ)) / ε`
- Proper sensitivity computation for counts (Δ=1), sums (Δ=max_value), means (Δ=max_value/n)
- Budget exhaustion returns `suppressed: true` and blocks further queries
- Clean API: `laplace_count()`, `gaussian_mean()`, etc.

**Concern:** The `DPResult` struct exposes `true_value` alongside `noisy_value`. This is labeled "only available to authorized callers" but there's no enforcement — any code path can access it. Consider gating behind a feature flag or removing from production responses.

### 1.2 Privacy Budget Tracker (RDP Composition)
**Location:** `rust-api/src/credit/privacy_budget.rs`  
**Status:** ✅ Fully Implemented

| Property | Value |
|----------|-------|
| Composition method | Rényi Differential Privacy (RDP) |
| Per-query-type budgets | 8 types (credit, market, FL, etc.) |
| Window duration | 24 hours (configurable) |
| Default budget/window | ε=1.0 per query type |
| RDP → DP conversion | Optimal α scanning (2..=128) |

**Implementation Quality:**
- Correct RDP composition: `ε_total(α) = Σᵢ εᵢ(α)` (additive for same α)
- Proper Gaussian RDP: `ε_RDP(α) = α × Δ² / (2σ²)`
- Correct RDP-to-DP conversion: `ε_DP = ε_RDP + log(1/δ) / (α - 1)`
- Per-type isolation prevents one category from exhausting global budget
- Time-windowed resets limit long-term privacy leakage
- Fail-closed design: queries blocked when budget exceeded

**Concern:** The `to_dp_epsilon` method scans α from 2 to 128 but doesn't use the actual RDP α from the query — it recomputes. This is correct for reporting but the actual composition uses fixed α per query. The tracker should ideally use the same α across queries for tight composition.

### 1.3 k-Anonymity Enforcer
**Location:** `rust-api/src/gateway/k_anonymity.rs`  
**Status:** ✅ Fully Implemented

| Property | Value |
|----------|-------|
| Minimum k | 10 (system-wide, enforced) |
| Cohort merging | Supported (nearest-neighbor) |
| Audit trail | In-memory ring buffer (1000 entries) |
| Alerting | `tracing::warn` on violations |

**Implementation Quality:**
- Hard minimum: `k.max(MIN_K_ANONYMITY)` prevents configuration below 10
- `enforce_with_audit()` captures endpoint, cohort key, and decision for every query
- `merge_small_cohorts()` handles cases where cohorts are too small
- Batch enforcement for multiple cohorts
- Violation counting for monitoring dashboards

**Concern:** The audit log is in-memory only (`parking_lot::Mutex<Vec<…>>`). If the process restarts, all audit history is lost. Consider persisting k-anonymity decisions to PostgreSQL alongside the main audit log.

### 1.4 Federated Learning (FedProx + DP)
**Location:** `rust-api/src/credit/federated.rs`  
**Status:** ✅ Fully Implemented

| Property | Value |
|----------|-------|
| Algorithm | FedProx (proximal term μ=0.01) |
| Gradient clipping | L2 norm clipping (clip_norm=1.0) |
| DP noise | Gaussian, σ = noise_multiplier × clip_norm |
| Byzantine robustness | TrimmedMean, CoordinateMedian, Krum |
| Gradient sparsification | Top-K, Threshold, Random-K |
| Convergence monitoring | Loss tracking, gradient explosion detection |

**Implementation Quality:**
- `credit_default()` sets noise_multiplier=0.0 (NO DP) — clearly documented as NOT for production
- `credit_private(epsilon, delta)` correctly calibrates: `noise_multiplier = √(2 × ln(1.25/δ)) / ε`
- Per-dimension Gaussian noise after aggregation
- Gradient clipping ensures bounded sensitivity
- Byzantine-robust aggregation strategies (TrimmedMean default)
- `aggregate_with_metadata()` returns DP audit trail

**Concern:** `credit_default()` has NO differential privacy. The code warns via `tracing::warn` but a misconfigured deployment could run FL without DP. Consider making `credit_private()` the only constructor, or adding a compile-time feature flag.

### 1.5 Federated Dialect Learning (Python)
**Location:** `python/dialect/federated_dialect_learning.py`  
**Status:** ✅ Fully Implemented

| Property | Value |
|----------|-------|
| DP mechanism | Gaussian (ε=1.0, δ=1e-5) |
| Gradient clipping | L2 norm clipping |
| Minimum participants | 10 per round |
| Bayesian aggregation | Posterior over dialect parameters |
| Secure aggregation | Sum before adding noise |

**Concern:** `MIN_PARTICIPANTS = 10` is lower than the k-anonymity threshold of 10 used elsewhere. For dialect learning this may be acceptable (gradients are aggregated, not raw data), but should be documented.

---

## 2. SHAP Explainer & EU AI Act Compliance
**Location:** `rust-api/src/credit/shap_explainer.rs`  
**Status:** ✅ Fully Implemented

### Implementation
- **Linear model path:** Exact Shapley values via `φᵢ = βᵢ × (xᵢ - x̄ᵢ)` — mathematically exact for logistic regression
- **KernelSHAP fallback:** Weighted linear regression on coalitions (256 samples default)
- **Background statistics:** Computed from training data (mean, std, n_observations)
- **Human-readable descriptions:** Feature-specific explanations in English/Swahili

### EU AI Act Compliance (Art. 13 — Transparency)
- ✅ Every credit score has a `CreditExplanation` with Shapley values
- ✅ `top_factors` provides ranked human-readable explanations
- ✅ `base_value` shows the population baseline
- ✅ `shapley_sum` verifies reconstruction accuracy
- ✅ `model_version` tracked for audit
- ✅ `computed_at` timestamp for temporal tracking
- ✅ `/api/v1/tools/credit/:score_id/explain` endpoint exposes explanations

### Gap
- ❌ No explanation persistence — explanations are computed on-the-fly but not stored. EU AI Act requires retention of decision records for audit.
- ❌ No counterfactual explanations ("what would change the decision")
- ❌ No explanation quality metrics (e.g., faithfulness scores)

---

## 3. Fairness Testing
**Location:** `rust-api/src/credit/fairness.rs`  
**Status:** ✅ Fully Implemented

### Three Fairness Criteria
| Criterion | Threshold | Test |
|-----------|-----------|------|
| Demographic Parity | 20% max difference | Across worker types |
| Equalized Odds | 15% max TPR/FPR difference | Across regions |
| Predictive Parity | 10% max PPV difference | Across groups |

### Implementation Quality
- ✅ Statistical significance testing (z-test for proportions, α=0.05)
- ✅ Minimum group size enforcement (n≥30)
- ✅ Disparate impact ratio (4/5ths rule monitoring)
- ✅ Severity classification: Warning / Moderate / Critical
- ✅ Full `FairnessReport` with pairwise comparisons
- ✅ `run_fairness_audit()` as single entry point

### Gap
- ❌ No automated fairness monitoring — tests exist but no evidence of periodic execution
- ❌ No fairness-aware model retraining pipeline
- ❌ Thresholds are configurable but no evidence of tuning based on Kenya-specific context

---

## 4. Auth & Security Assessment

### 4.1 JWT Authentication
**Location:** `rust-api/src/gateway/auth.rs`  
**Status:** ✅ Production-Grade

| Feature | Status |
|---------|--------|
| Token format | JWT with `jti` (UUID v4) |
| Algorithm | Default (HS256 via `jsonwebtoken`) |
| Token revocation | Redis blacklist with TTL |
| Refresh tokens | One-time use (old token revoked) |
| Client IP extraction | X-Forwarded-For → X-Real-IP → ConnectInfo |
| Logout | Revokes current token |
| Minimum secret length | 32 characters (enforced at startup) |

**Auth Flow:**
1. Client → `POST /api/v1/auth/token` with API key
2. Server validates → returns access + refresh token pair
3. Client → Bearer token on all requests
4. Middleware: decode JWT → check expiry → check Redis blacklist → inject claims
5. Refresh: old refresh token revoked, new pair issued
6. Logout: current token added to Redis blacklist

**Concerns:**
- ⚠️ HS256 (symmetric) is used, not RS256 (asymmetric). SECURITY.md claims RS256 but code uses `Header::default()` which is HS256. This means the signing key = verification key, which is fine for single-service but doesn't match the documented claim.
- ⚠️ Token endpoint accepts `tier` from the client request body rather than looking it up from a database. A client could claim "enterprise" tier. This appears to be a simplified implementation — production should validate API keys against a database.

### 4.2 Rate Limiting
**Location:** `rust-api/src/gateway/rate_limit.rs`  
**Status:** ✅ Implemented

| Tier | Requests/min | Queries/month |
|------|-------------|---------------|
| Free | 10 | 100 |
| Starter | 100 | 5,000 |
| Pro | 1,000 | 50,000 |
| Enterprise | 10,000 | Unlimited |

- Token-bucket algorithm per buyer key
- Per-IP rate limiter for webhooks (60 req/min)
- Returns `X-RateLimit-Remaining` and `Retry-After` headers
- 429 Too Many Requests on exhaustion

### 4.3 Security Headers
**Location:** `rust-api/src/gateway/security_headers.rs`  
**Status:** ✅ Comprehensive

| Header | Value |
|--------|-------|
| HSTS | max-age=31536000; includeSubDomains |
| X-Content-Type-Options | nosniff |
| X-Frame-Options | DENY |
| X-XSS-Protection | 1; mode=block |
| CSP | default-src 'self' |
| Referrer-Policy | strict-origin-when-cross-origin |
| Permissions-Policy | camera=(), microphone=(), geolocation=(), payment=() |

### 4.4 CORS
**Status:** ✅ Hardened

- Explicit `ALLOWED_ORIGINS` env var (no wildcard)
- No localhost fallback in production (`ANGAVU_ENV=production`)
- Mobile/server-to-server requests (no origin) allowed
- `Vary: Origin` header for proper CDN caching

### 4.5 Input Validation
**Status:** ✅ Implemented

- `garde` crate validation on webhook and approval request bodies
- Pattern validation on action types
- Length limits on descriptions and comments
- Request body size limit: 10 MB
- Request timeout: 30 seconds

### 4.6 Audit Logging
**Location:** `rust-api/src/gateway/audit.rs`  
**Status:** ✅ Production-Grade

- Every API request logged with: org_id, endpoint, method, status, latency, IP, user agent
- Batch INSERT to PostgreSQL for 10× write throughput
- Fallback to individual INSERTs on batch failure
- In-memory buffer with configurable flush threshold
- SQL migration for audit_log table with proper indices

---

## 5. Data Retention & Right-to-Erasure
**Location:** `rust-api/src/gateway/data_retention.rs`  
**Status:** ✅ Implemented

### Retention Policies

| Category | Retention | Legal Basis |
|----------|-----------|-------------|
| Raw Transactions | 2 years | Kenya DPA: legitimate interest |
| Aggregated Statistics | 5 years | Anonymized (not personal data) |
| Audit Logs | 7 years | Kenya DPA: accountability |
| Credit Scores | 3 years | EU AI Act: decision records |
| Federated Gradients | 90 days | Minimization |
| Webhook Events | 1 year | Dispute resolution |
| Session Data | 30 days | Minimization |
| Billing Records | 7 years | Kenya Tax Act |
| Approval Records | 3 years | EU AI Act: human oversight |
| Model Training Data | 1 year | Audit/retraining |

### Right-to-Erasure
- `generate_erasure_queries(person_id)` produces cascading DELETE statements
- Covers: transactions, credit_score_history, audit_log
- `erasure_requests` table tracks deletion requests with status
- `data_retention_log` table tracks enforcement runs

**Concern:** The erasure implementation generates raw SQL strings with the person_id interpolated directly. This is a SQL injection risk if `person_id` is not sanitized upstream. Use parameterized queries.

---

## 6. Database Encryption
**Location:** `migrations/20260801000006_pgcrypto_encryption.sql`  
**Status:** ✅ Implemented

- `pgcrypto` extension enabled
- `encrypt_sensitive(plaintext, key)` — AES-256 via PGP symmetric encryption
- `decrypt_sensitive(ciphertext, key)` — with graceful failure (returns NULL)
- Key passed via `app.encryption_key` session variable from `ENCRYPTION_KEY` env var
- Commented-out examples for encrypted phone/email columns

---

## 7. Human-in-the-Loop Approval
**Location:** `rust-api/src/gateway/human_approval.rs`  
**Status:** ✅ Production-Grade

- 8 action types: transaction, loan_application, credit_decision, tax_filing, chama_withdrawal, group_contribution, large_expense, report_delivery
- Timeouts: 30s (transactions) to 48h (chama operations)
- Redis storage with TTL-based expiry
- One-time use: approval deleted after resolution
- Authorization: authenticated user must own the approval
- Input validation via `garde` crate
- Full audit trail with client IP
- Swahili-language prompts for Kenyan users

---

## 8. CI/CD Security Pipeline
**Location:** `.github/workflows/security.yml`  
**Status:** ✅ Comprehensive

| Check | Frequency | Status |
|-------|-----------|--------|
| cargo-audit (CVE) | Push + Weekly | ✅ |
| cargo-deny (licenses, advisories, bans, sources) | Push + Weekly | ✅ |
| Dependency review | PRs only | ✅ Blocks high-severity |
| Secret scanning | Push + Weekly | ✅ Regex patterns |
| Docker image scan (Trivy) | Push to main | ✅ CRITICAL + HIGH |

---

## 9. Compliance Gaps

### 9.1 Kenya Data Protection Act 2019

| Requirement | Status | Gap |
|-------------|--------|-----|
| S25: Lawful processing | ✅ | Consent + legitimate interest documented |
| S26: Purpose limitation | ✅ | Documented in DPIA |
| S27: Data minimization | ✅ | Only essential fields |
| S28: Accuracy | ⚠️ | User correction workflow not implemented |
| S29: Storage limitation | ✅ | Retention policies defined |
| S30: Security | ✅ | Technical controls comprehensive |
| S31: DPIA | ✅ | Complete document exists |
| S32: Data portability | ❌ | Export API not implemented |
| S33: Right to erasure | ⚠️ | SQL generation exists but no API endpoint |
| S34: Breach notification | ❌ | No automated breach detection |
| S35: Cross-border transfer | ✅ | Data residency in Kenya (Oracle Cloud) |
| ODPC Registration | ❌ | Not completed |
| DPO Appointment | ❌ | Not completed |

### 9.2 EU AI Act (enforced 2026)

| Requirement | Status | Gap |
|-------------|--------|-----|
| Art. 9: Risk management | ⚠️ | Fairness tests exist but no periodic execution |
| Art. 10: Data governance | ✅ | k-anonymity, DP, retention policies |
| Art. 11: Technical documentation | ⚠️ | DPIA exists but not EU AI Act-specific |
| Art. 13: Transparency | ✅ | SHAP explanations on all credit decisions |
| Art. 14: Human oversight | ✅ | Human-in-the-loop approval system |
| Art. 15: Accuracy/robustness | ⚠️ | No automated drift detection pipeline |
| Art. 17: Post-market monitoring | ❌ | No monitoring system for deployed models |

### 9.3 GDPR (if serving EU users)

| Requirement | Status | Gap |
|-------------|--------|-----|
| Art. 5: Principles | ✅ | Minimization, purpose limitation |
| Art. 6: Lawful basis | ✅ | Documented |
| Art. 13/14: Information | ❌ | No privacy policy published |
| Art. 15: Access | ❌ | No subject access request API |
| Art. 17: Erasure | ⚠️ | SQL exists, no API endpoint |
| Art. 20: Portability | ❌ | Not implemented |
| Art. 22: Automated decisions | ✅ | SHAP + human-in-the-loop |
| Art. 25: Privacy by design | ✅ | DP, k-anonymity, FL |
| Art. 30: Records of processing | ❌ | Not documented |
| Art. 32: Security | ✅ | Comprehensive |
| Art. 33/34: Breach notification | ❌ | No automated detection |
| Art. 35: DPIA | ✅ | Exists |
| Art. 37: DPO | ❌ | Not appointed |

---

## 10. Security Vulnerabilities & Concerns

### 🔴 Critical

1. **SQL Injection in Erasure Queries** — `generate_erasure_queries(person_id)` interpolates `person_id` directly into SQL strings. If this value comes from user input, it's exploitable. **Fix:** Use parameterized queries.

2. **Token Endpoint Trusts Client-Claimed Tier** — `issue_token()` accepts `tier` from the request body. A free-tier user could claim "enterprise" to bypass rate limits. **Fix:** Look up tier from database using the API key.

### 🟠 High

3. **DPResult Exposes True Values** — `DPResult.true_value` is always populated in the engine. If serialized to API responses (even accidentally), it defeats the purpose of differential privacy. **Fix:** Gate behind feature flag or never serialize in production.

4. **No Persistent k-Anonymity Audit** — k-anonymity decisions are stored in-memory only. Process restart loses all audit history. **Fix:** Persist to PostgreSQL.

5. **Federated Learning Default Has No DP** — `FedProxAggregator::credit_default()` sets `noise_multiplier=0.0`. Code warns but doesn't enforce. **Fix:** Make DP mandatory or add compile-time check.

### 🟡 Medium

6. **JWT Algorithm Mismatch** — SECURITY.md claims RS256 but code uses HS256 (`Header::default()`). For multi-service deployments, RS256 is preferred. **Fix:** Document correctly or switch to RS256.

7. **No Automated Fairness Monitoring** — Fairness tests exist but no evidence they're run periodically. EU AI Act requires ongoing monitoring. **Fix:** Add to CI/CD or scheduled job.

8. **No Explanation Persistence** — SHAP explanations computed on-the-fly but not stored. EU AI Act requires decision records. **Fix:** Store explanations alongside credit scores.

9. **Privacy Budget Reset Not Persisted** — If the process restarts, all privacy budgets reset to zero, potentially allowing more queries than intended in a time window. **Fix:** Persist budget state to Redis.

10. **No CORS Preflight Caching** — `max-age` is set to 3600s which is fine, but the `Vary: Origin` header means CDN caching may be inefficient for multi-origin setups.

### 🟢 Low

11. **Metrics Endpoint IP Restriction** — `/metrics` is restricted to `127.0.0.1` and `172.16.0.0/12` in nginx, but the Rust backend has no equivalent restriction. If nginx is bypassed, metrics are exposed.

12. **No Content-Length Validation** — Request body limit is 10 MB, which is generous for an API. Consider reducing for non-upload endpoints.

13. **Audit Log Fallback** — When PostgreSQL is unavailable, audit logs go to structured logging only. These may not be retained.

---

## 11. Recommendations

### Immediate (P0 — This Sprint)

1. **Fix SQL injection in erasure queries** — Use parameterized queries in `generate_erasure_queries()`
2. **Fix token endpoint tier validation** — Look up API key in database, don't trust client-claimed tier
3. **Remove `true_value` from DPResult serialization** — Gate behind `#[cfg(debug_assertions)]` or remove entirely

### Short-term (P1 — Next 3 Months)

4. **Persist k-anonymity audit to PostgreSQL** — Extend audit_log table with k-anonymity decisions
5. **Persist privacy budget state to Redis** — Survive process restarts
6. **Make FL differential privacy mandatory** — Remove `credit_default()` or add compile-time enforcement
7. **Add data export API** — Kenya DPA S32 and GDPR Art. 20
8. **Add erasure request API endpoint** — Expose `generate_erasure_queries()` via authenticated endpoint
9. **Store SHAP explanations** — Add `explanation_json` column to credit_score_history
10. **Appoint DPO and register with ODPC** — Legal requirement

### Medium-term (P2 — Next 12 Months)

11. **Automated fairness monitoring** — Scheduled job to run fairness audits monthly
12. **Counterfactual explanations** — "What would you need to change to get approved?"
13. **Privacy policy** — Publish in English and Swahili
14. **Breach detection system** — Automated monitoring for data exfiltration patterns
15. **Post-market monitoring** — EU AI Act Art. 17 compliance for deployed models
16. **Switch to RS256** — For multi-service JWT verification without sharing the signing key

---

## 12. Summary

| Area | Score | Status |
|------|-------|--------|
| Differential Privacy | 9/10 | Excellent — dual mechanism, budget tracking, RDP composition |
| k-Anonymity | 8/10 | Strong — enforced minimum, cohort merging, audit trail (in-memory) |
| Federated Learning | 8/10 | Strong — FedProx, Byzantine robustness, DP support (opt-in) |
| SHAP Explainability | 8/10 | Strong — exact linear, KernelSHAP fallback, human-readable |
| Fairness Testing | 7/10 | Good — three criteria, statistical tests, but no automation |
| Authentication | 7/10 | Good — JWT + revocation + refresh, but tier trust issue |
| Rate Limiting | 9/10 | Excellent — per-tier, per-IP, token bucket |
| Security Headers | 9/10 | Excellent — comprehensive, hardened CORS |
| Data Retention | 8/10 | Strong — 10 categories, right-to-erasure, audit trail |
| Encryption | 8/10 | Strong — pgcrypto AES-256, TLS 1.2/1.3 |
| Audit Logging | 8/10 | Strong — batch PostgreSQL, comprehensive fields |
| CI/CD Security | 9/10 | Excellent — CVE, license, secret scanning, Docker scan |
| **Overall** | **8.2/10** | **Production-ready with P0 fixes needed** |

The Angavu Intelligence backend demonstrates a sophisticated, defense-in-depth approach to privacy and security. The privacy mechanisms (DP, k-anonymity, FL) are mathematically sound and well-implemented. The primary concerns are operational (persistence of audit state, automated monitoring) and a few implementation issues (SQL injection in erasure, tier trust) that should be addressed before production launch.
