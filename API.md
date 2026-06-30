# Msaidizi API Reference

**Base URL:** `https://api.msaidizi.biashara.ai/v1`

All endpoints require JWT authentication unless marked as **Public**.

---

## Authentication

### Register User

```
POST /api/v1/auth/register
```

Create a new user account on the Msaidizi platform.

**Request Body:**

```json
{
  "phone": "+254712345678",
  "name": "Jane Wanjiku",
  "business_type": "mboga_vendor",
  "language": "sw",
  "location": {
    "county": "Nairobi",
    "sub_county": "Kamukunji"
  }
}
```

**Response (201 Created):**

```json
{
  "user_id": "usr_a1b2c3d4",
  "phone": "+254712345678",
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_at": "2026-07-07T16:00:00Z",
  "created_at": "2026-06-30T12:00:00Z"
}
```

**Errors:**

| Code | Description |
|------|-------------|
| 400 | Invalid phone number format |
| 409 | Phone number already registered |
| 422 | Validation error |

---

### Login

```
POST /api/v1/auth/login
```

**Request Body:**

```json
{
  "phone": "+254712345678",
  "otp_code": "123456"
}
```

**Response (200 OK):**

```json
{
  "user_id": "usr_a1b2c3d4",
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_at": "2026-07-07T16:00:00Z"
}
```

---

### Refresh Token

```
POST /api/v1/auth/refresh
```

**Headers:** `Authorization: Bearer <token>`

**Response (200 OK):**

```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_at": "2026-07-14T16:00:00Z"
}
```

---

## Data Sync

### Upload Transaction Data

```
POST /api/v1/sync
```

Upload batched transaction data from Android device. This is the primary data ingestion endpoint.

**Headers:** `Authorization: Bearer <token>`

**Request Body:**

```json
{
  "device_id": "dev_x9y8z7",
  "sync_timestamp": "2026-06-30T15:30:00Z",
  "transactions": [
    {
      "id": "txn_001",
      "type": "sale",
      "amount": 150.00,
      "currency": "KES",
      "description": "Tomatoes 2kg",
      "category": "vegetables",
      "timestamp": "2026-06-30T09:15:00Z",
      "voice_transcript": "Niliuza nyanya kilo mbili mia moja hamsini"
    },
    {
      "id": "txn_002",
      "type": "purchase",
      "amount": 80.00,
      "currency": "KES",
      "description": "Tomatoes 1kg wholesale",
      "category": "vegetables",
      "timestamp": "2026-06-30T07:00:00Z"
    }
  ],
  "daily_summary": {
    "total_sales": 2500.00,
    "total_purchases": 1200.00,
    "profit": 1300.00,
    "transaction_count": 15
  }
}
```

**Response (200 OK):**

```json
{
  "sync_id": "sync_m1n2o3",
  "status": "accepted",
  "transactions_received": 2,
  "server_timestamp": "2026-06-30T15:30:05Z",
  "next_sync_recommended": "2026-06-30T21:30:00Z"
}
```

**Errors:**

| Code | Description |
|------|-------------|
| 400 | Malformed payload |
| 401 | Missing or expired token |
| 413 | Payload too large (max 5MB) |
| 429 | Rate limit exceeded |

---

## Reports

### Get Business Reports

```
GET /api/v1/reports/{user_id}
```

Retrieve business intelligence reports for a specific user.

**Headers:** `Authorization: Bearer <token>`

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | `7d` | Report period: `1d`, `7d`, `30d`, `90d` |
| `format` | string | `json` | Response format: `json`, `summary` |

**Response (200 OK):**

```json
{
  "user_id": "usr_a1b2c3d4",
  "period": "2026-06-23 to 2026-06-30",
  "summary": {
    "total_revenue": 17500.00,
    "total_expenses": 8400.00,
    "net_profit": 9100.00,
    "profit_margin": 52.0,
    "transaction_count": 105,
    "avg_daily_revenue": 2500.00
  },
  "trends": {
    "revenue_change_pct": 12.5,
    "profit_change_pct": 8.3,
    "best_day": "2026-06-28",
    "best_day_revenue": 3200.00,
    "top_category": "vegetables"
  },
  "advice": [
    {
      "type": "opportunity",
      "message": "Your tomato sales peak on Saturdays. Consider buying 30% more stock on Fridays.",
      "confidence": 0.87
    },
    {
      "type": "warning",
      "message": "Your expenses on transport increased 25% this week. Consider bulk buying to reduce trips.",
      "confidence": 0.72
    }
  ],
  "generated_at": "2026-06-30T16:00:00Z"
}
```

---

### Get Daily Summary

```
GET /api/v1/reports/{user_id}/daily
```

**Headers:** `Authorization: Bearer <token>`

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | No | Date in `YYYY-MM-DD` format (defaults to today) |

**Response (200 OK):**

```json
{
  "user_id": "usr_a1b2c3d4",
  "date": "2026-06-30",
  "sales": {
    "total": 2500.00,
    "count": 15,
    "items": [
      {"category": "vegetables", "amount": 1200.00},
      {"category": "fruits", "amount": 800.00},
      {"category": "other", "amount": 500.00}
    ]
  },
  "purchases": {
    "total": 1200.00,
    "count": 3
  },
  "profit": 1300.00,
  "voice_notes": 8
}
```

---

## Economic Intelligence

### Get Intelligence Reports (For Buyers)

```
GET /api/v1/intelligence/{buyer_type}
```

Access aggregated, anonymized economic intelligence data. Only available to verified institutional buyers.

**Headers:** `Authorization: Bearer <buyer_token>`

**Buyer Types:**

| Type | Description |
|------|-------------|
| `fmcg` | Fast-moving consumer goods companies |
| `government` | Government economic planning agencies |
| `banks` | Financial institutions and lenders |
| `ngos` | NGOs and development organizations |

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `region` | string | `all` | Geographic filter: county name or `all` |
| `sector` | string | `all` | Business sector filter |
| `period` | string | `30d` | Analysis period |
| `metrics` | string | `all` | Comma-separated: `volume,pricing,trends,demand` |

**Response (200 OK):**

```json
{
  "buyer_type": "fmcg",
  "region": "Nairobi",
  "period": "2026-06-01 to 2026-06-30",
  "sample_size": 12500,
  "k_anonymity": 10,
  "metrics": {
    "market_volume": {
      "total_transactions": 187500,
      "total_value_kes": 28125000.00,
      "avg_transaction_kes": 150.00
    },
    "pricing": {
      "avg_retail_markup_pct": 45.0,
      "price_sensitivity_index": 0.78,
      "optimal_price_range_kes": {
        "low": 120.00,
        "high": 180.00
      }
    },
    "demand_signals": [
      {
        "category": "cooking_oil",
        "demand_trend": "increasing",
        "growth_pct": 15.2,
        "peak_days": ["friday", "saturday"]
      },
      {
        "category": "sugar",
        "demand_trend": "stable",
        "growth_pct": 2.1,
        "peak_days": ["saturday"]
      }
    ],
    "geographic_hotspots": [
      {"area": "Kamukunji", "activity_index": 92},
      {"area": "Gikomba", "activity_index": 87},
      {"area": "Eastleigh", "activity_index": 75}
    ]
  },
  "privacy_guarantee": "All data aggregated with k≥10 anonymity. No individual transactions exposed.",
  "generated_at": "2026-06-30T16:00:00Z"
}
```

**Errors:**

| Code | Description |
|------|-------------|
| 401 | Invalid buyer credentials |
| 403 | Buyer type not authorized for this data |
| 429 | Query rate limit exceeded |

---

## WhatsApp Integration

### Connect WhatsApp

```
POST /api/v1/whatsapp/connect
```

Initiate WhatsApp Business API connection for a user.

**Headers:** `Authorization: Bearer <token>`

**Request Body:**

```json
{
  "phone": "+254712345678",
  "connection_type": "business_api"
}
```

**Response (200 OK):**

```json
{
  "status": "pending_verification",
  "verification_method": "sms",
  "expires_in": 300,
  "message": "Verification code sent to +254712345678"
}
```

---

### Send WhatsApp Message

```
POST /api/v1/whatsapp/send
```

Send a message via the WhatsApp bridge (used for automated reports and alerts).

**Headers:** `Authorization: Bearer <token>`

**Request Body:**

```json
{
  "to": "+254712345678",
  "type": "report",
  "template": "daily_summary",
  "data": {
    "date": "2026-06-30",
    "profit": 1300.00,
    "advice": "Good day! You made KSh 1,300 profit today."
  }
}
```

**Response (200 OK):**

```json
{
  "message_id": "wa_p3q4r5",
  "status": "sent",
  "delivered_at": "2026-06-30T16:05:00Z"
}
```

---

## Health & Status

### Health Check (Public)

```
GET /api/v1/health
```

**Response (200 OK):**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 86400,
  "services": {
    "database": "connected",
    "redis": "connected",
    "celery": "running"
  }
}
```

---

## Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| `/auth/*` | 5 requests | 15 minutes |
| `/sync` | 100 requests | 1 hour |
| `/reports/*` | 200 requests | 1 hour |
| `/intelligence/*` | 50 requests | 1 hour |
| `/whatsapp/*` | 30 requests | 1 hour |

Rate limit headers are included in all responses:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1625097600
```

---

## Error Format

All errors follow a consistent format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid phone number format",
    "details": {
      "field": "phone",
      "expected": "E.164 format (e.g., +254712345678)"
    }
  },
  "request_id": "req_s6t7u8"
}
```

---

## SDKs & Integration

- **Android:** Built-in sync via `SyncRepository` class
- **Python:** `pip install msaidizi-sdk` (coming soon)
- **REST:** Any HTTP client (curl, Postman, etc.)

---

*Biashara AI Ltd — Proprietary API*
