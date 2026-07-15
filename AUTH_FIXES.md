# Authentication Fixes — Critical Security Patches

**Date:** 2026-07-16
**Severity:** CRITICAL
**Author:** Security Engineer (automated fix)

## Summary

Three API modules had endpoints accepting unauthenticated requests for sensitive operations (deployment management, model registry mutations, and federated learning gradient submissions). All write/mutating endpoints now require JWT authentication via the existing `get_current_user` dependency from `app/api/auth.py`.

---

## 1. `app/api/deployment.py` — Deployment Harness Endpoints

**Issue:** All 20 deployment lifecycle and management endpoints lacked authentication. Any unauthenticated caller could start, pause, resume, or rollback canary deployments; create/delete feature flags; and record metrics.

**Fix:** Added `user: User = Depends(get_current_user)` to every endpoint function signature.

### Protected Endpoints (20 total)

| Method | Path | Operation |
|--------|------|-----------|
| POST | `/deploy/start` | Start canary deployment |
| GET | `/deploy/status/{deployment_id}` | Get deployment status |
| POST | `/deploy/pause/{deployment_id}` | Pause deployment |
| POST | `/deploy/resume/{deployment_id}` | Resume deployment |
| POST | `/deploy/rollback/{deployment_id}` | Rollback deployment |
| GET | `/deploy/active` | List active deployments |
| GET | `/deploy/history` | Deployment history |
| GET | `/deploy/versions` | Version map |
| GET | `/deploy/versions/serving` | Serving versions |
| GET | `/deploy/routes` | Traffic routes |
| GET | `/deploy/flags` | List feature flags |
| POST | `/deploy/flags` | Create feature flag |
| POST | `/deploy/flags/{name}/enable` | Enable feature flag |
| POST | `/deploy/flags/{name}/disable` | Disable feature flag |
| POST | `/deploy/flags/{name}/check` | Check feature flag |
| DELETE | `/deploy/flags/{name}` | Delete feature flag |
| GET | `/deploy/metrics` | All deployment metrics |
| GET | `/deploy/metrics/{component}` | Component metrics |
| POST | `/deploy/metrics/record` | Record request metric |
| GET | `/deploy/health` | Harness health |

**Imports added:** `Depends` from `fastapi`, `get_current_user` from `app.api.auth`, `User` from `app.models.user`

---

## 2. `app/api/infrastructure_v2.py` — Model Registry & Infrastructure Management

**Issue:** Write endpoints for model registration, deployment, rollback, promotion, A/B testing, federated learning submissions, cost recording, and metric recording lacked authentication. An attacker could deploy malicious models, manipulate A/B tests, or poison federated learning data.

**Fix:** Added `user: User = Depends(get_current_user)` to all 10 write/mutating endpoints. Read-only endpoints (health checks, model listings, status queries) remain public for monitoring dashboards.

### Protected Endpoints (10 total)

| Method | Path | Operation |
|--------|------|-----------|
| POST | `/infrastructure/health/metrics` | Record server metrics |
| POST | `/infrastructure/inference` | Record inference event |
| POST | `/infrastructure/models` | Register model version |
| POST | `/infrastructure/models/deploy` | Deploy model to traffic |
| POST | `/infrastructure/models/{model_name}/rollback` | Rollback model |
| POST | `/infrastructure/models/{model_name}/promote/{version}` | Promote model to champion |
| POST | `/infrastructure/ab-test` | Start A/B test |
| POST | `/infrastructure/ab-test/{test_id}/end` | End A/B test |
| POST | `/infrastructure/federated` | Submit federated learning update |
| POST | `/infrastructure/costs` | Record cost entry |

### Unprotected Endpoints (read-only, intentionally public)

- `GET /infrastructure/health` — Cluster health status
- `GET /infrastructure/health/servers` — Server health
- `GET /infrastructure/inference` — Inference metrics
- `GET /infrastructure/models` — Model listing
- `GET /infrastructure/models/{model_name}/champion` — Champion model
- `GET /infrastructure/models/{model_name}/performance` — Model performance
- `GET /infrastructure/ab-tests` — A/B test listing
- `GET /infrastructure/federated/status` — FL status
- `GET /infrastructure/federated/models` — FL models
- `GET /infrastructure/federated/model/{category}/{dialect}` — FL model details
- `GET /infrastructure/costs` — Cost summary
- `GET /infrastructure/alerts` — Alerts

**Imports added:** `Depends` from `fastapi`, `get_current_user` from `app.api.auth`, `User` from `app.models.user`

---

## 3. `app/api/fl_aggregator.py` — Federated Learning Aggregator

**Issue:** The gradient submission endpoint (`POST /fl-aggregator/delta`) and aggregation trigger endpoint (`POST /fl-aggregator/aggregate`) accepted unauthenticated requests. An attacker could submit poisoned gradients to manipulate model training or trigger unauthorized aggregation rounds.

**Fix:** Added `user: User = Depends(get_current_user)` to both write endpoints. Read-only endpoints (status, cohort stats, model retrieval) remain public.

### Protected Endpoints (2 total)

| Method | Path | Operation |
|--------|------|-----------|
| POST | `/fl-aggregator/delta` | Submit gradient delta |
| POST | `/fl-aggregator/aggregate` | Trigger aggregation |

### Unprotected Endpoints (read-only)

- `GET /fl-aggregator/status` — System-wide aggregator status
- `GET /fl-aggregator/cohort/{cohort_id}` — Per-cohort stats
- `GET /fl-aggregator/model/{cohort_id}` — Latest aggregated model

**Imports added:** `Depends` from `fastapi`, `get_current_user` from `app.api.auth`, `User` from `app.models.user`

---

## Authentication Pattern

All fixes use the same dependency injection pattern established in `app/api/auth.py`:

```python
from app.api.auth import get_current_user
from app.models.user import User

@router.post("/example")
async def example_endpoint(user: User = Depends(get_current_user)):
    # user is guaranteed to be authenticated and active
    ...
```

The `get_current_user` dependency:
1. Extracts the JWT from the `Authorization: Bearer <token>` header
2. Validates the token signature, expiry, issuer, and audience
3. Confirms the token type is `access` (not `refresh`)
4. Verifies the user exists and is active in the database
5. Returns the `User` model instance

---

## Testing Recommendations

1. **Verify 401 responses**: All protected endpoints should return `401 Unauthorized` with `{"detail": "Invalid token"}` when called without a valid JWT.
2. **Verify expired tokens**: Expired tokens should be rejected.
3. **Verify refresh token rejection**: Refresh tokens should not be accepted on these endpoints.
4. **Run existing test suite**: Ensure no regressions in existing functionality.
5. **Penetration test**: Attempt to call protected endpoints with manipulated/forged tokens.

---

## Files Modified

- `app/api/deployment.py` — 20 endpoints secured
- `app/api/infrastructure_v2.py` — 10 endpoints secured
- `app/api/fl_aggregator.py` — 2 endpoints secured

**Total: 32 endpoints secured across 3 files.**
