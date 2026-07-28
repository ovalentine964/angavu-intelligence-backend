# Angavu Intelligence — SLO Definitions

## Service Level Objectives

### 1. API Availability
| Field | Value |
|-------|-------|
| **SLO** | 99.5% availability |
| **Window** | 30-day rolling |
| **Metric** | `(1 - 5xx_responses / total_responses) * 100` |
| **Error Budget** | 0.5% (~3.6 hours/month downtime) |
| **Severity** | Critical |
| **Alert** | Fires when availability < 99.5% for 1 hour |
| **Owner** | Backend team |

**Measurement:**
```promql
(1 - sum(rate(http_requests_total{status=~"5.."}[30d]))
    / sum(rate(http_requests_total[30d]))) * 100
```

### 2. Sync Success Rate
| Field | Value |
|-------|-------|
| **SLO** | 95% sync success rate |
| **Window** | 7-day rolling |
| **Metric** | `successful_syncs / total_syncs * 100` |
| **Error Budget** | 5% failed syncs per week |
| **Severity** | Warning |
| **Alert** | Fires when success rate < 95% for 1 hour |
| **Owner** | Backend team |

**Measurement:**
```promql
sum(rate(sync_operations_total{status="success"}[7d]))
/ sum(rate(sync_operations_total[7d])) * 100
```

### 3. Intent Classification Accuracy
| Field | Value |
|-------|-------|
| **SLO** | 90% accuracy |
| **Window** | 7-day rolling |
| **Metric** | `correct_classifications / total_classifications * 100` |
| **Error Budget** | 10% misclassifications per week |
| **Severity** | Warning |
| **Alert** | Fires when accuracy < 90% for 1 hour |
| **Owner** | AI/ML team |

**Measurement:**
```promql
avg(intent_classification_accuracy) * 100
```

### 4. Credit Scoring Accuracy
| Field | Value |
|-------|-------|
| **SLO** | 80% accuracy |
| **Window** | 30-day rolling |
| **Metric** | Model accuracy on validation set |
| **Error Budget** | 20% inaccuracy |
| **Severity** | Warning |
| **Alert** | Fires when accuracy < 80% for 1 hour |
| **Owner** | ML team |

**Measurement:**
```promql
avg(credit_score_accuracy) * 100
```

---

## Error Budget Policy

| Budget Remaining | Action |
|-----------------|--------|
| > 50% | Normal development velocity |
| 25-50% | Heightened awareness, prioritize reliability |
| 10-25% | Freeze non-critical deployments, focus on fixes |
| < 10% | Emergency mode — only critical fixes deployed |

## Grafana Dashboard

SLO tracking is built into the main Grafana dashboard (`angavu-backend-main`):
- **API Availability (SLO)** panel — 30-day rolling availability
- **SLO Error Budget Remaining** panel — visual error budget gauge
- **Sync Success Rate** gauge — real-time sync health
- **Intent Classification Accuracy** stat — current accuracy
- **Credit Scoring Accuracy** time series — accuracy trend

## Alert Routing

| Alert | Severity | Channel |
|-------|----------|---------|
| SLOAvailabilityBurn | Critical | #alerts-critical |
| SyncSLOBreach | Warning | #alerts-warning |
| CreditAccuracySLOBreach | Warning | #alerts-warning |
| ErrorBudgetExhausted | Critical | #alerts-critical |
