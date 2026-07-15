# Integration Fixes: Msaidizi App ↔ Angavu Backend

**Date:** 2026-07-16
**Scope:** Backend-side fixes for integration issues with the Msaidizi Android app

---

## Fix 1: OTP Field Name Mismatch (HIGH)

**Problem:** The Msaidizi app sends `{"phone": "...", "otp": "..."}` but the backend expected `{"phone": "...", "code": "...", "device_id": "..."}`. The app also doesn't always send `device_id`.

**Files changed:** `app/api/otp_auth.py`

**Changes:**
- `OTPVerifyRequest.code`: Added `alias="otp"` so the field accepts both `"code"` and `"otp"` from the JSON body
- `OTPVerifyRequest.device_id`: Changed from required to `Optional[str] = None` since the app doesn't always send it
- `OTPRegisterRequest.code`: Added `alias="otp"` (same as above)
- `OTPRegisterRequest.device_id`: Changed from required to `Optional[str] = None`
- Both models: Added `model_config = {"populate_by_name": True}` to accept both alias and field name
- `verify_otp()`: Added `if request.device_id:` guard before updating user device_id
- `register_with_otp()`: Uses `request.device_id or "unknown"` as fallback
- `OTPResponse`: Added `serialization_alias="ttl"` on `otp_expires_in_seconds` (app expects `ttl`)
- `/request` endpoint: Added `response_model_by_alias=True` to serialize with alias

---

## Fix 2: FL Endpoint Path Mismatch (HIGH)

**Problem:** The app calls `/api/v1/federated/*` but `fl_aggregator.py` only exposed `/fl-aggregator/*` routes. The `federated_learning.py` already had some `/federated/` aliases but was missing the version check endpoint.

**Files changed:** `app/api/fl_aggregator.py`, `app/api/federated_learning.py`

**Changes in `fl_aggregator.py`:**
- `/fl-aggregator/delta` → also routed at `/federated/delta`
- `/fl-aggregator/aggregate` → also routed at `/federated/aggregate`
- `/fl-aggregator/status` → also routed at `/federated/status`
- `/fl-aggregator/cohort/{cohort_id}` → also routed at `/federated/cohort/{cohort_id}`
- `/fl-aggregator/model/{cohort_id}` → also routed at `/federated/model/{cohort_id}`
- All aliases use `include_in_schema=False` to avoid OpenAPI duplication

**Changes in `federated_learning.py`:**
- `/fl/check-version/{dialect}` → also routed at `/federated/check-version/{dialect}`

---

## Fix 3: Model Version Check Endpoint (HIGH)

**Problem:** The app needs to check for model updates before downloading. The backend already had a `/fl/check-version/{dialect}` endpoint but it wasn't accessible via the `/federated/` prefix the app uses.

**Files changed:** `app/api/federated_learning.py`

**Changes:**
- Added `/federated/check-version/{dialect}` as an alias route for the existing version check endpoint
- The endpoint returns `{update_available, latest_version, download_url}` — already implemented in `FederatedLearningService.check_version()`

---

## Fix 4: Sync Schema Field Name Mismatches (MEDIUM)

**Problem:** The Msaidizi app sends transaction fields with different names than the backend expects:
| App field | Backend field |
|-----------|--------------|
| `type` | `transaction_type` |
| `total_amount` | `amount` |
| `occurred_at` | `timestamp` |
| `category` | `item_category` |

**Files changed:** `app/schemas/sync.py`

**Changes in `TransactionRecord`:**
- `transaction_type`: Added `alias="type"`
- `item_category`: Added `alias="category"`
- `amount`: Added `alias="total_amount"`
- `timestamp`: Added `alias="occurred_at"`
- Added `model_config = {"populate_by_name": True}` to accept both original names and aliases

**Changes in `AnonymizedTransaction`:**
- `transaction_type`: Added `alias="type"`
- `item_category`: Added `alias="category"`
- `amount`: Added `alias="total_amount"`
- `timestamp`: Added `alias="occurred_at"`
- Added `model_config = {"populate_by_name": True}`

---

## Compatibility Notes

- All fixes are **backward-compatible** — existing clients using the original field names will continue to work
- `populate_by_name=True` ensures both alias and original field names are accepted in request bodies
- Route aliases (`include_in_schema=False`) avoid OpenAPI schema duplication
- The `/fl-aggregator/*` routes remain as the canonical paths; `/federated/*` are aliases
