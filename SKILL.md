---
name: angavu-intelligence-backend
description: >
  Angavu Intelligence backend plugin for OpenClaw. Provides economic intelligence
  APIs for Kenya's informal economy — transaction analysis, credit scoring (Alama),
  demand forecasting (Soko Pulse), distribution gap analysis, and multi-agent
  orchestration. Connects to PostgreSQL, Redis, ClickHouse, and WhatsApp.
version: 0.2.0
license: MIT
metadata:
  openclaw:
    emoji: "📊"
    requires:
      config:
        - "angavu.api_url"
        - "angavu.api_key"
      bins: []
    os: ["linux", "darwin"]
allowed-tools:
  - alama_score
  - soko_pulse
  - distribution_gap
  - fmcg_intelligence
  - worker_intelligence
  - angavu_api
  - angavu_health
---

# Angavu Intelligence — Backend Plugin

Africa's operating system for the informal economy. Processing data from 600M+ informal workers into economic intelligence.

## When to Use This Skill

Activate this skill when the user asks about:
- **Credit scoring** — "What's the Alama score for this business?"
- **Market intelligence** — "What are cooking oil prices doing in Kisumu?"
- **Distribution analysis** — "Where are coverage gaps for our FMCG products?"
- **Economic indicators** — "What's the MSME activity index for Nairobi?"
- **Worker insights** — "How is this trader's financial health?"
- **Demand forecasting** — "What's the forecast for maize demand in Western Kenya?"
- **API management** — "Check backend health" or "Show me the API metrics"

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   OpenClaw Plugin                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │ alama_score  │  │ soko_pulse  │  │ dist_gap    │     │
│  │ (Credit)     │  │ (Forecast)  │  │ (FMCG)      │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘     │
│         │                 │                 │             │
│  ┌──────┴─────────────────┴─────────────────┴──────┐     │
│  │              angavu_api (HTTP Client)             │     │
│  │         FastAPI → PostgreSQL + Redis + ClickHouse │     │
│  └─────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

## Configuration

Set these in your OpenClaw config:

```yaml
angavu:
  api_url: "https://api.angavu.io"  # or http://localhost:8000 for dev
  api_key: "${ANGAVU_API_KEY}"       # JWT token for authentication
  timeout: 30                         # Request timeout in seconds
  max_retries: 3                      # Retry failed requests
```

## Available Tools

### `angavu_api`
Generic HTTP client for all backend endpoints. Use for operations not covered by specialized tools.

**Parameters:**
- `method` (string, required): HTTP method — `GET`, `POST`, `PUT`, `DELETE`
- `path` (string, required): API path (e.g., `/api/v1/transactions/`)
- `body` (object, optional): Request body for POST/PUT
- `query` (object, optional): URL query parameters

**Example:**
```json
{
  "method": "GET",
  "path": "/api/v1/health",
  "query": { "detailed": "true" }
}
```

### `alama_score`
Credit scoring for informal businesses. Returns Alama scores (300-850).

**Parameters:**
- `business_id` (string, required): Anonymized business hash (HMAC-SHA256)
- `lookback_days` (integer, optional): 30-365 days (default: 90)
- `query_tier` (string, optional): `basic`, `enhanced`, or `full` (default: basic)

**Returns:**
```json
{
  "score": 720,
  "band": "Good",
  "percentile": 78,
  "components": {
    "activity": 85,
    "stability": 72,
    "growth": 68,
    "consistency": 79,
    "diversity": 65
  },
  "default_probability": 0.12,
  "recommended_limit": 45000
}
```

### `soko_pulse`
FMCG demand forecasting from informal markets.

**Parameters:**
- `product_category` (string, required): `food`, `household`, `health`, `clothing`, `electronics`, `beauty`, `agriculture`, `services`
- `product_name` (string, optional): Specific product name
- `region` (string, optional): Geographic code (`KSM`, `NBI`, `MSA`, etc.) or null for national
- `tier` (string, optional): `basic`, `standard`, `premium`, `enterprise`
- `lookback_days` (integer, optional): 30-365 days (default: 90)

**Returns:**
```json
{
  "demand_forecast": {
    "next_7_days": 125000,
    "next_30_days": 520000,
    "confidence_interval": [480000, 560000]
  },
  "price_intelligence": {
    "current_avg": 185,
    "trend": "increasing",
    "elasticity": -0.72
  },
  "seasonal_pattern": "peak_december"
}
```

### `distribution_gap`
Identifies coverage gaps and expansion opportunities for FMCG companies.

**Parameters:**
- `product_category` (string, required): Product category to analyze
- `region` (string, optional): Geographic focus or null for national
- `tier` (string, optional): `basic`, `standard`, `premium`

**Returns:**
```json
{
  "coverage_rate": 0.67,
  "underserved_markets": [
    {"market": "Turkana", "demand_index": 0.82, "entry_cost": 45000},
    {"market": "Marsabit", "demand_index": 0.71, "entry_cost": 38000}
  ],
  "expansion_roi": {
    "turkana": {"payback_months": 8, "npv": 120000}
  }
}
```

### `fmcg_intelligence`
FMCG-specific intelligence queries.

**Parameters:**
- `query_type` (string, required): `channel_sales`, `route_optimization`, `competitive_pricing`, `fleet_utilization`
- `company` (string, optional): Company filter (`pwani_oil`, `unilever`, `bidco`)
- `product_category` (string, optional): Product filter
- `region` (string, optional): Geographic filter

### `worker_intelligence`
Worker-level financial health and readiness scores.

**Parameters:**
- `worker_id` (string, required): Anonymized worker hash
- `metrics` (array, optional): Specific metrics to retrieve

### `angavu_health`
Check backend service health and metrics.

**Parameters:**
- `detailed` (boolean, optional): Include component-level health (default: false)

**Returns:**
```json
{
  "status": "healthy",
  "version": "0.2.0",
  "uptime_seconds": 864000,
  "components": {
    "database": "healthy",
    "redis": "healthy",
    "clickhouse": "healthy",
    "whatsapp": "degraded"
  }
}
```

## Response Formats

### Credit Assessment
1. **Score Summary** — Alama score, band, percentile
2. **Component Breakdown** — Activity, stability, growth, consistency, diversity
3. **Risk Assessment** — Default probability, risk factors, credit limit
4. **Peer Comparison** — How this business compares to similar businesses
5. **Recommendation** — Lending decision with rationale

### Market Intelligence
1. **Executive Summary** — 2-3 sentence overview of key findings
2. **Demand Analysis** — Volume trends, growth trajectory, seasonal patterns
3. **Price Intelligence** — Current prices, trends, elasticity
4. **Forecast** — Ensemble forecast with confidence intervals
5. **Recommendations** — Actionable insights

### Distribution Analysis
1. **Coverage Summary** — Current distribution map, coverage rate
2. **Gap Analysis** — Top underserved markets with demand estimates
3. **Expansion Recommendations** — Prioritized list with ROI
4. **Competitive Position** — How coverage compares to competitors
5. **Action Plan** — Specific steps for recommended expansions

## Statistical Methods

The backend implements these methods (available via `alama_score` enhanced/full tiers):

- **Heckman Correction** — Selection bias correction for credit scoring
- **Bayesian Estimation** — Beta-Binomial conjugate prior for cold-start
- **Holt-Winters** — Triple exponential smoothing for demand forecasting
- **ARIMA** — Box-Jenkins time series methodology
- **Price Elasticity** — Log-log regression (constant elasticity model)
- **PCA** — Dimensionality reduction of borrower features
- **Monte Carlo** — Revenue distribution simulation
- **Markov Chains** — Credit score transition probabilities

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (all services) |
| `/metrics` | GET | Prometheus metrics |
| `/api/v1/auth/*` | POST | Authentication (OTP, biometric) |
| `/api/v1/transactions/*` | CRUD | Transaction management |
| `/api/v1/reports/*` | GET | Report generation |
| `/api/v1/intelligence/*` | GET | Intelligence products |
| `/api/v1/whatsapp/*` | POST | WhatsApp connection |

## Error Handling

| Error Code | Description | Action |
|------------|-------------|--------|
| 401 | Invalid API key | Check `angavu.api_key` config |
| 403 | Insufficient permissions | Verify API key scopes |
| 429 | Rate limited | Wait and retry with backoff |
| 503 | Service unavailable | Check `angavu_health` for status |

## Data Privacy

- All business IDs are HMAC-SHA256 hashes — never attempt to reverse-hash
- All data is k-anonymized (k≥10) and differentially private
- Never expose individual trader or business identities
- All queries are logged for audit but not linked to individuals

## Deployment

The backend runs on Oracle Cloud Free Tier:
```bash
# One-command deploy
curl -sSL https://raw.githubusercontent.com/ovalentine964/angavu-intelligence-backend/main/deploy.sh | bash
```

**Stack:** Python 3.12, FastAPI, Gunicorn (4 workers), PostgreSQL 16, Redis 7, ClickHouse, Docker

## License

MIT — Angavu Intelligence
