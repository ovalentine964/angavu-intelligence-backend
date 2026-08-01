# Angavu Intelligence Backend — API Documentation

**Version:** 0.3.0  
**Base URL:** `https://api.angavu.io` (production) / `http://localhost:8000` (development)  
**Authentication:** JWT Bearer tokens  
**Content-Type:** `application/json`

---

## Table of Contents

1. [Authentication](#authentication)
2. [Health & Status](#health--status)
3. [Sync API](#sync-api)
4. [Tools API](#tools-api)
5. [OODA Loop API](#ooda-loop-api)
6. [Pipeline API](#pipeline-api)
7. [Graph Analytics API](#graph-analytics-api)
8. [GraphQL API](#graphql-api)
9. [Webhook API](#webhook-api)
10. [Billing API](#billing-api)
11. [Observability API](#observability-api)
12. [Human-in-the-Loop API](#human-in-the-loop-api)
13. [Error Handling](#error-handling)
14. [Rate Limiting](#rate-limiting)
15. [k-Anonymity](#k-anonymity)

---

## Authentication

All protected endpoints require a JWT Bearer token in the `Authorization` header.

### Token Format

```
Authorization: Bearer <access_token>
```

### Token Claims

```json
{
  "sub": "user_id",
  "aud": "angavu-api",
  "iat": 1700000000,
  "exp": 1700003600,
  "jti": "uuid-v4",
  "tier": "partner",
  "permissions": ["read", "write"]
}
```

### Token Lifetimes

| Token Type | TTL |
|-----------|-----|
| Access Token | 15 minutes |
| Refresh Token | 30 days (one-time use) |

### Auth Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/auth/token` | Public | Issue access + refresh token pair |
| POST | `/api/v1/auth/refresh` | Public | Exchange refresh token for new pair (one-time use) |
| POST | `/api/v1/auth/logout` | Protected | Revoke current access token (Redis blacklist) |

### Token Revocation

All tokens carry a UUID v4 `jti` claim. Revoked tokens are stored in Redis with TTL matching the token's remaining lifetime. The auth middleware checks the blacklist on every request.

---

## Health & Status

### GET /health

Health check endpoint (no auth required).

**Response:**
```
200 OK
"OK"
```

### GET /api/v1/tools

List available intelligence tools (no auth required).

**Response:**
```json
{
  "tools": [
    "market_analyzer",
    "credit_scorer",
    "distribution_analyzer",
    "fmcg_intelligence",
    "health_metrics",
    "economic_analyzer"
  ]
}
```

---

## Sync API

### POST /api/v1/sync/anonymized

Push anonymized data from devices. Supports bidirectional sync (push + pull).

**Headers:**
- `Authorization: Bearer <token>` (required)
- `X-Sync-Protocol-Version: 2` (required)

**Request Body:**
```json
{
  "device_id_hash": "sha256:abc123...",
  "cohort_hash": "sha256:def456...",
  "timestamp": "2026-07-28T12:00:00Z",
  "transactions": [
    {
      "category": "vegetables",
      "amount_kes": 1500,
      "count": 5,
      "payment_channel": "mpesa"
    }
  ],
  "sync_cursor": "cursor_abc123",
  "data_version": 1
}
```

**Response (200):**
```json
{
  "status": "accepted",
  "records_processed": 1,
  "new_cursor": "cursor_def456",
  "pull_updates": []
}
```

**k-Anonymity:** Data is only accepted if the cohort has ≥10 members.

---

## Graph Sync API

### POST /api/v1/sync/graph

Device-server graph sync. Push node/edge/fact deltas to the knowledge graph with k-anonymity enforcement.

**Headers:**
- `Authorization: Bearer <token>` (required)

**Request Body:**
```json
{
  "device_id_hash": "sha256:abc123...",
  "cohort_hash": "sha256:def456...",
  "last_sync_timestamp": 1700000000000,
  "current_timestamp": 1700000060000,
  "node_deltas": [
    {
      "id": "uuid",
      "type": "PRODUCT",
      "label": "Tomatoes",
      "properties": {},
      "updated_at": 1700000000000,
      "operation": "UPSERT"
    }
  ],
  "edge_deltas": [
    {
      "from_id": "uuid1",
      "to_id": "uuid2",
      "relation": "SUPPLIES",
      "properties": {},
      "weight": 0.8,
      "updated_at": 1700000000000,
      "operation": "UPSERT"
    }
  ],
  "fact_deltas": [
    {
      "subject": "tomatoes",
      "predicate": "category",
      "object": "vegetables",
      "confidence": 0.95,
      "source": "device",
      "updated_at": 1700000000000,
      "operation": "UPSERT"
    }
  ],
  "stats": {
    "transaction_count_today": 15,
    "total_revenue_today": 5000.0,
    "product_count": 8,
    "customer_count": 0,
    "dominant_product_category": "vegetables",
    "worker_type_detected": "mama_mboga"
  }
}
```

**Response (200):**
```json
{
  "success": true,
  "server_timestamp": 1700000060000,
  "deltas_applied": 3,
  "market_signals": [],
  "price_updates": [],
  "demand_signals": [],
  "cohort_insights": [],
  "error": null
}
```

**k-Anonymity:** Rejected if cohort has < 10 members. PII (customer nodes, phone numbers, names) is rejected.

**Safe node types:** PRODUCT, SUPPLIER only. CUSTOMER and TRANSACTION are rejected.
**Safe edge types:** SUPPLIES, BELONGS_TO, PRICED_AT, LOCATED_AT, ALTERNATIVE_TO, COMPLEMENTS, SUBCATEGORY_OF.

---

## Tools API

### POST /api/v1/tools/credit-scores

Compute credit score (Alama Score) for a cohort.

**Request Body:**
```json
{
  "cohort_hash": "sha256:abc123...",
  "worker_type": "mama_mboga",
  "region": "nairobi-eastlands",
  "transaction_history_months": 6,
  "include_components": true
}
```

**Response (200):**
```json
{
  "alama_score": 680,
  "risk_tier": "moderate",
  "default_probability": 0.12,
  "components": {
    "transaction_consistency": 0.82,
    "revenue_stability": 0.75,
    "payment_diversity": 0.68,
    "seasonal_adjustment": 0.90,
    "peer_comparison": 0.71
  },
  "cohort_size": 50,
  "confidence": 0.85,
  "scored_at": "2026-07-28T12:00:00Z"
}
```

### GET /api/v1/tools/market-analyses

Market analysis for a product category and region.

**Query Parameters:**
- `category` (required): Product category code
- `region` (required): Region code
- `timeframe_days` (optional, default: 30)

**Response (200):**
```json
{
  "category": "vegetables",
  "region": "nairobi-eastlands",
  "avg_price_kes": 120.5,
  "price_trend": "rising",
  "price_change_pct": 8.5,
  "demand_signal": "strong",
  "supply_status": "adequate",
  "competition_level": "moderate",
  "opportunities": [
    "Price increase of 8.5% in last 7 days suggests undersupply"
  ],
  "risks": [
    "Seasonal peak ending in 2 weeks"
  ]
}
```

### GET /api/v1/tools/demand-forecasts

Demand forecast for a product category.

**Query Parameters:**
- `category` (required): Product category code
- `region` (required): Region code
- `horizon_days` (optional, default: 7)

**Response (200):**
```json
{
  "category": "vegetables",
  "region": "nairobi-eastlands",
  "forecast_horizon_days": 7,
  "predicted_demand_change_pct": 12.3,
  "confidence": 0.78,
  "factors": [
    "Upcoming holiday increases demand",
    "Weather forecast favorable for supply"
  ]
}
```

### POST /api/v1/tools/economic-indicators

Compute economic indicators for a region.

**Request Body:**
```json
{
  "region": "nairobi-eastlands",
  "indicators": ["cpi_proxy", "employment_index", "transaction_volume"],
  "timeframe_days": 30
}
}
```

**Response (200):**
```json
{
  "region": "nairobi-eastlands",
  "indicators": {
    "cpi_proxy": {
      "value": 112.5,
      "change_pct": 2.1,
      "trend": "rising"
    },
    "employment_index": {
      "value": 0.87,
      "change_pct": -0.5,
      "trend": "stable"
    },
    "transaction_volume": {
      "value": 15000,
      "change_pct": 5.2,
      "trend": "rising"
    }
  },
  "computed_at": "2026-07-28T12:00:00Z"
}
```

### GET /api/v1/tools/distribution-gaps

Distribution gap analysis.

**Query Parameters:**
- `region` (required): Region code
- `product_category` (optional): Filter by category

**Response (200):**
```json
{
  "region": "nairobi-eastlands",
  "gaps": [
    {
      "category": "dairy",
      "penetration": 0.35,
      "potential_market_size_kes": 500000,
      "recommended_action": "Partner with dairy cooperatives"
    }
  ],
  "overall_coverage": 0.72
}
```

### GET /api/v1/tools/fmcg-reports

FMCG intelligence report.

**Query Parameters:**
- `region` (required)
- `brand` (optional)

**Response (200):**
```json
{
  "region": "nairobi-eastlands",
  "top_categories": [
    {"category": "beverages", "share_pct": 25.3},
    {"category": "snacks", "share_pct": 18.7}
  ],
  "channel_mix": {
    "kiosk": 0.45,
    "market_stall": 0.30,
    "shop": 0.25
  },
  "growth_opportunities": [
    "Cold beverage demand up 15% in afternoon hours"
  ]
}
```

### POST /api/v1/tools/privacy/noise

Add differential privacy noise to a value.

**Request Body:**
```json
{
  "value": 15000.0,
  "epsilon": 1.0,
  "sensitivity": 1000.0,
  "mechanism": "laplace"
}
```

**Response (200):**
```json
{
  "original_value": 15000.0,
  "noisy_value": 15234.5,
  "epsilon": 1.0,
  "mechanism": "laplace",
  "privacy_guarantee": "ε=1.0 differential privacy"
}
```

### POST /api/v1/tools/anonymization

Anonymize a data record.

**Request Body:**
```json
{
  "data": {
    "name": "John Doe",
    "phone": "+254712345678",
    "revenue": 15000
  },
  "fields_to_anonymize": ["name", "phone"],
  "method": "hash"
}
```

### GET /api/v1/tools/federated-learning/status

Federated learning status.

**Response (200):**
```json
{
  "current_round": 42,
  "model_name": "alama_score_v2",
  "status": "aggregating",
  "participants": 150,
  "cohorts_contributing": 12,
  "global_accuracy": 0.82,
  "privacy_budget_remaining": 0.65
}
```

### POST /api/v1/tools/reports

Generate an intelligence report.

**Request Body:**
```json
{
  "report_type": "market_intelligence",
  "region": "nairobi-eastlands",
  "timeframe_days": 30,
  "sections": ["executive_summary", "market_trends", "demand_signals", "recommendations"]
}
```

---

## OODA Loop API

### GET /api/v1/ooda/status

Current OODA cycle status.

**Response (200):**
```json
{
  "current_cycle": {
    "id": "uuid...",
    "cycle_speed": "daily",
    "cycle_number": 127,
    "started_at": "2026-07-28T00:00:00Z",
    "completed_at": null,
    "status": "running"
  },
  "phases_completed": [
    {"phase": "observe", "status": "completed", "duration_ms": 1200},
    {"phase": "orient", "status": "running", "duration_ms": null}
  ],
  "pipeline_progress": 0.45
}
```

### POST /api/v1/ooda/trigger

Manually trigger an OODA cycle.

**Request Body:**
```json
{
  "speed": "fast",
  "trigger_source": "manual"
}
```

**Response (200):**
```json
{
  "cycle_id": "uuid...",
  "status": "started"
}
```

**Cycle Speeds:**
| Speed | Frequency | Use Case | Implementation |
|-------|-----------|----------|----------------|
| `fast` | Every sync event | Real-time signal processing | DB-backed: validates sync, updates profiles, flags anomalies |
| `hourly` | Every hour | Market aggregation | DB-backed: aggregates market signals, updates Soko Pulse |
| `daily` | Daily at 00:00 UTC | Intelligence reports | DB-backed: generates reports, runs drift detection |
| `weekly` | Sunday 02:00 UTC | Federated learning | DB-backed: FedProx gradient aggregation, Alama recalibration |

---

## Pipeline API

The intelligence pipeline DAG: Sync → Anonymize → Aggregate → Analyze → Generate → Distribute.

### Pipeline Nodes

| Node | Type | Dependencies | Description |
|------|------|-------------|-------------|
| `sync_transactions` | Sync | — | Sync transaction data from devices |
| `sync_market_data` | Sync | — | Sync market price data |
| `sync_external` | Sync | — | Sync external signals (weather, events) |
| `anonymize` | Anonymize | All sync | Strip PII, add DP noise |
| `aggregate` | Aggregate | anonymize | Aggregate across cohorts and regions |
| `analyze_patterns` | Analyze | aggregate | Pattern detection |
| `analyze_credit` | Analyze | aggregate | Credit scoring |
| `analyze_market` | Analyze | aggregate | Market analysis |
| `generate_reports` | Generate | All analyze | Generate intelligence reports |
| `generate_signals` | Generate | analyze_patterns, analyze_market | Generate signals |
| `distribute` | Distribute | All generate | Distribute to consumers |

### Pipeline Features

- **Parallel execution:** Independent nodes run concurrently
- **Circuit breakers:** Per-node fault isolation
- **Retry logic:** Automatic retry with backoff
- **Topological ordering:** Dependency-aware execution

---

## Graph Analytics API

The backend implements **7 graph algorithms** over the knowledge graph, powered by the `UnifiedKnowledgeLayer` that bridges in-memory, PostgreSQL, and Harness graphs:

#### PageRank
Ranks nodes by importance. Useful for identifying the most influential worker cohorts, product categories, or market nodes.

#### Community Detection
Identifies clusters of related nodes using label propagation. Useful for identifying worker cohorts with similar behavior patterns.

#### Degree Centrality
Measures node connectivity. Identifies the most connected nodes (key hubs in the knowledge graph).

#### Shortest Path
Finds the shortest weighted path between two nodes using Dijkstra's algorithm. Useful for understanding relationship chains.

#### Betweenness Centrality (Brandes' Algorithm)
Finds nodes that serve as bridges between communities. Complexity: O(VE). Identifies important intermediary suppliers serving multiple regions.

#### k-Core Decomposition
Finds the k-core: maximal subgraph where every node has degree ≥ k. Complexity: O(V+E). Identifies tightly-connected economic communities.

#### Weighted Shortest Path (Inverse Weight)
Uses inverse weights: stronger relationships (higher weight) have lower traversal cost. Complements raw-weight Dijkstra.

### Graph Index: HNSW + Matryoshka

All vector similarity queries use HNSW indexes with Matryoshka truncation:
- **Recall@10:** 95-99% (vs 85-95% for IVFFlat)
- **Query time:** 2-6ms
- **Storage:** 83% savings via 256-dim truncation (from 1536)
- **Parameters:** m=16, ef_construction=64

---

## GraphQL API

**Endpoint:** `POST /graphql`  
**Playground:** `GET /graphql` (browser)  
**Schema SDL:** `GET /graphql/schema`

### Queries

#### Get a Node
```graphql
query {
  node(id: "uuid...") {
    id
    nodeType
    label
    properties
  }
}
```

#### List Nodes
```graphql
query {
  nodes(filter: {
    nodeType: "worker_cohort"
    region: "nairobi-eastlands"
    limit: 20
  }) {
    id
    nodeType
    label
    properties
  }
}
```

#### Get Edges
```graphql
query {
  edges(filter: {
    edgeType: "generates_signal"
    sourceId: "uuid..."
    minWeight: 0.5
    limit: 50
  }) {
    id
    sourceId
    targetId
    edgeType
    weight
    confidence
    properties
  }
}
```

#### Find Shortest Path
```graphql
query {
  shortestPath(from: "uuid1...", to: "uuid2...", maxDepth: 5) {
    path
    totalWeight
    hopCount
  }
}
```

#### Get Subgraph
```graphql
query {
  subgraph(center: "uuid...", maxHops: 2, limit: 100) {
    nodes { id nodeType label properties }
    edges { id sourceId targetId edgeType weight }
    nodeCount
    edgeCount
  }
}
```

#### PageRank
```graphql
query {
  pagerank(iterations: 30, damping: 0.85, limit: 20) {
    nodeId
    score
    label
  }
}
```

#### Community Detection
```graphql
query {
  communities(minSize: 3) {
    id
    members
    internalEdges
    modularityScore
  }
}
```

#### Degree Centrality
```graphql
query {
  degreeCentrality(topK: 20) {
    nodeId
    degree
    inDegree
    outDegree
    label
  }
}
```

#### Graph Statistics
```graphql
query {
  graphStats {
    totalNodes
    totalEdges
    nodeTypeCounts { nodeType count }
  }
}
```

---

## Webhook API

### POST /api/v1/webhooks/mpesa

M-Pesa payment callback endpoint. Auto-categorizes incoming payments.

### POST /api/v1/webhooks/market

Market data feed webhook.

### POST /api/v1/webhooks/generic

Generic webhook for external event ingestion.

**Headers:**
- `X-Webhook-API-Key: <key>` (required)

---

## Billing API

### GET /api/v1/billing/tiers

List available billing tiers.

### POST /api/v1/billing/subscriptions

Create a subscription.

### POST /api/v1/billing/api-keys

Generate an API key for a subscription.

---

## Observability API

### GET /observability/slo

Current SLO status.

**Response (200):**
```json
{
  "slos": [
    {
      "name": "api_availability",
      "description": "API uptime percentage",
      "target_percent": 99.9,
      "current_value": 99.95,
      "is_met": true,
      "error_budget_remaining_percent": 85.0
    }
  ],
  "all_met": true
}
```

### GET /observability/slo/breached

Currently breached SLOs.

### GET /observability/traces/stats

Agent trace statistics.

**Query Parameters:**
- `hours` (optional, default: 24): Time range

---

## Human-in-the-Loop API

Endpoints for human approval of sensitive decisions.

### POST /api/v1/approval/credit

Request human approval for credit decisions.

### POST /api/v1/approval/sensitive

Request human approval for sensitive actions.

### GET /api/v1/approval/pending

List pending approval requests.

### POST /api/v1/approval/{id}/approve

Approve a pending request.

### POST /api/v1/approval/{id}/reject

Reject a pending request.

---

## New Endpoints (v0.3)

### Credit Explainability

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/tools/credit/{id}/explain` | SHAP-based credit score explanation with feature contributions |
| POST | `/api/v1/tools/fairness/audit` | Run fairness audit (demographic parity, equalized odds, predictive parity) |

### Health & Observability

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | No | Liveness check (Docker HEALTHCHECK) |
| GET | `/health/ready` | No | Readiness check (PostgreSQL + Redis + ClickHouse) |
| GET | `/health/detailed` | No | Full diagnostics (pool stats, memory, CPU, uptime) |
| GET | `/observability/traces/stats` | Yes | Agent trace statistics |

### Privacy (Working Implementations)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/tools/privacy/noise` | Inject Laplace/Gaussian differential privacy noise (was 501 stub) |
| POST | `/api/v1/tools/anonymization` | Apply k-anonymity + DP noise (was 501 stub) |

### Data Retention

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/retention/policies` | List data retention policies |
| POST | `/api/v1/retention/erasure` | Request right-to-erasure (Kenya DPA 2019) |

### Market Intelligence (PostgreSQL-backed)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/tools/market-analyses` | Market analysis with k-anonymity + DP noise (PostgreSQL-backed) |
| GET | `/api/v1/tools/demand-forecasts` | Demand forecast with Laplace DP noise on predictions |
| GET | `/api/v1/tools/service-prices` | Aggregated service pricing intelligence |

---

## Error Handling

All errors follow a consistent format:

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Missing required field: cohort_hash",
    "details": {},
    "request_id": "req_abc123"
  }
}
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request — invalid input |
| 401 | Unauthorized — missing or invalid token |
| 403 | Forbidden — insufficient permissions |
| 404 | Not Found |
| 409 | Conflict — resource already exists |
| 429 | Too Many Requests — rate limited |
| 500 | Internal Server Error |
| 501 | Not Implemented — stubbed endpoint ("Coming Soon") |
| 503 | Service Unavailable — circuit breaker open |

### Error Codes

| Code | Description |
|------|-------------|
| `INVALID_REQUEST` | Malformed request body or parameters |
| `AUTH_EXPIRED` | JWT token has expired |
| `AUTH_INVALID` | JWT token is invalid |
| `RATE_LIMITED` | Rate limit exceeded |
| `K_ANONYMITY_VIOLATION` | Cohort size below k=10 threshold |
| `CIRCUIT_OPEN` | Service circuit breaker is open |
| `DEPTH_LIMIT_EXCEEDED` | Graph traversal depth exceeds maximum (10) |
| `COHORT_NOT_FOUND` | Worker cohort not found |
| `INSUFFICIENT_DATA` | Not enough data for computation |

---

## Rate Limiting

All authenticated endpoints are rate-limited.

| Tier | Requests/Minute | Burst |
|------|-----------------|-------|
| Free | 10 | 5 |
| Partner | 100 | 20 |
| Enterprise | 1000 | 100 |

Rate limit headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1700000060
```

---

## k-Anonymity

The Angavu platform enforces k-anonymity (k≥10) on all data queries:

- Worker cohorts must have ≥10 members
- Queries returning individual-level data are suppressed if group size < 10
- Differential privacy noise is added to aggregate values
- Embedding vectors are computed at cohort level, never individual

**Error Response (k-Anonymity Violation):**
```json
{
  "error": {
    "code": "K_ANONYMITY_VIOLATION",
    "message": "Query result set too small for k-anonymity (k=10 required)",
    "details": {
      "actual_size": 7,
      "minimum_size": 10
    }
  }
}
```

---

## Graph Performance Limits

To prevent expensive traversals, the following limits are enforced:

| Operation | Limit |
|-----------|-------|
| Maximum traversal depth | 10 hops |
| Maximum subgraph nodes | 1,000 |
| Maximum edges per query | 5,000 |
| PageRank iterations (default) | 30 |
| PageRank iterations (max) | 100 |
| Community detection iterations | 50 |

---

## Examples

### cURL: Get PageRank Results

```bash
curl -X POST http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "{ pagerank(limit: 10) { nodeId score label } }"
  }'
```

### cURL: Find Shortest Path

```bash
curl -X POST http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "{ shortestPath(from: \"uuid1\", to: \"uuid2\") { path totalWeight hopCount } }"
  }'
```

### cURL: Market Analysis

```bash
curl "http://localhost:8000/api/v1/tools/market-analyses?category=vegetables&region=nairobi-eastlands" \
  -H "Authorization: Bearer $TOKEN"
```

### Python: GraphQL Client

```python
import requests

url = "http://localhost:8000/graphql"
headers = {"Authorization": f"Bearer {token}"}

query = """
{
  nodes(filter: {nodeType: "worker_cohort", limit: 10}) {
    id
    label
    properties
  }
}
"""

response = requests.post(url, json={"query": query}, headers=headers)
print(response.json())
```
