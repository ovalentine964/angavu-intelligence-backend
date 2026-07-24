# Superagent Tools Definition — Msaidizi + Angavu Backend

> **Per Jensen Huang's Vision:** "One domain-specific superagent connected to many tools"

---

## MSAIDIZI SUPERAGENT — 20 Tools

**ONE BRAIN, 20 TOOLS, ONE JOB:** "Help THIS worker run THEIR business better"

### Tool 1: TransactionRecorder
- **Purpose:** Records business transactions by voice or text
- **Input:** Voice text ("Nimeuza nyanya kilo 5, elfu moja"), parsed amount (1000), product (nyanya), quantity (5kg), payment method (cash/mpesa)
- **Output:** TransactionRecord(id, amount, product, quantity, payment_method, timestamp, category)
- **Activation:** Every time worker speaks about a sale or purchase
- **Integration:** Core tool — feeds all other tools (CFO, Inventory, Gamification, Sync)

### Tool 2: InventoryTracker
- **Purpose:** Tracks product stock levels
- **Input:** Product name, quantity added (restock) or removed (sale)
- **Output:** InventoryLevel(current_stock, restock_threshold, days_until_stockout)
- **Activation:** After every transaction recording
- **Integration:** Feeds RestockPredictor, CFOEngine

### Tool 3: CFOEngine
- **Purpose:** Daily briefings, cash flow predictions, savings advice
- **Input:** Transaction history (last 30 days), current date, business type
- **Output:** DailyBriefing(revenue, expenses, profit, top_products), CashFlowPrediction(next_7_days), SavingsAdvice
- **Activation:** Morning briefing (8AM), on-demand query, evening summary (6PM)
- **Integration:** Uses TransactionRecorder, InventoryTracker, GoalTracker data

### Tool 4: VoicePipeline
- **Purpose:** Speech-to-text and text-to-speech in 15+ African languages
- **Input:** Audio buffer (PCM/WAV)
- **Output:** Text (STT), Audio (TTS)
- **Activation:** When worker speaks or requests voice response
- **Integration:** Entry point for all voice interactions, feeds LanguageDetector

### Tool 5: LanguageDetector
- **Purpose:** Detects language/dialect from speech
- **Input:** Text or audio features
- **Output:** Language(code, confidence), Dialect(code, confidence)
- **Activation:** On every voice input
- **Integration:** Feeds VoicePipeline (selects STT/TTS model), CodeSwitchHandler

### Tool 6: CodeSwitchHandler
- **Purpose:** Handles mixed-language speech (Kiswahili + English + Sheng)
- **Input:** Multi-language text ("Nimeuza tomatoes mbili, fifty bob each")
- **Output:** Parsed intent with language-tagged tokens
- **Activation:** When LanguageDetector detects code-switching
- **Integration:** Feeds TransactionRecorder for accurate parsing

### Tool 7: GamificationEngine
- **Purpose:** Points, levels, streaks, badges
- **Input:** Action type (recorded_transaction, followed_advice, daily_streak, helped_peer)
- **Output:** PointsEarned(amount), LevelUp(new_level), BadgeUnlocked(badge_name), StreakUpdated(days)
- **Activation:** After every meaningful action
- **Integration:** Uses TransactionRecorder, CFOEngine data

### Tool 8: GoalTracker
- **Purpose:** Savings goals and loan repayment tracking
- **Input:** Goal(name, target_amount, deadline), contributions
- **Output:** GoalProgress(percentage, days_remaining, on_track)
- **Activation:** On goal creation, contribution, or query
- **Integration:** Feeds CFOEngine (advice based on goals)

### Tool 9: ReceiptScanner
- **Purpose:** CameraX + OCR for receipt scanning
- **Input:** Camera image
- **Output:** ExtractedText, ParsedReceipt(items, amounts, total)
- **Activation:** When worker points camera at receipt
- **Integration:** Feeds TransactionRecorder

### Tool 10: WhatsAppReporter
- **Purpose:** Sends business reports via WhatsApp
- **Input:** Report content, recipient phone, schedule
- **Output:** DeliveryStatus(sent, delivered, read)
- **Activation:** Daily (8AM), weekly (Monday), on-demand
- **Integration:** Uses CFOEngine for report content

### Tool 11: SyncEngine
- **Purpose:** Syncs anonymized data to backend
- **Input:** Local transactions (anonymized), model gradients
- **Output:** SyncStatus(success, conflicts_resolved), MarketIntelligence(received)
- **Activation:** When WiFi available + battery > 20%
- **Integration:** All data sources → anonymization → backend

### Tool 12: SecurityGuard
- **Purpose:** Encryption, biometric auth, PIN protection
- **Input:** Auth request (biometric/PIN), data to encrypt
- **Output:** AuthResult(granted/denied), EncryptedData
- **Activation:** App launch, sensitive operations
- **Integration:** Wraps all data access

### Tool 13: ModelDownloader
- **Purpose:** Downloads/updates AI models (Qwen, Whisper, Piper)
- **Input:** Model name, version, network condition
- **Output:** DownloadProgress, ModelReady status
- **Activation:** First launch, WiFi-only updates
- **Integration:** Feeds VoicePipeline, LlmEngine

### Tool 14: AdaptiveLearner
- **Purpose:** Learns vocabulary, business patterns, dialect
- **Input:** New word detected, correction from worker, transaction pattern
- **Output:** Updated vocabulary, detected pattern, calibrated model
- **Activation:** Continuously (background process)
- **Integration:** Feeds VoicePipeline (vocabulary), CFOEngine (patterns)

### Tool 15: MemoryManager
- **Purpose:** 5-layer memory hierarchy
- **Input:** Memory request (context needed for current query)
- **Output:** Relevant context from working/conversation/daily/patterns/knowledge layers
- **Activation:** On every superagent inference
- **Integration:** Central to all tools — provides context

### Tool 16: GuardrailsEngine
- **Purpose:** Financial integrity checks
- **Input:** Transaction to validate, advice to check
- **Output:** ValidationResult(accept/reject/flag), reason
- **Activation:** Before every transaction save, before every advice output
- **Integration:** Wraps TransactionRecorder, CFOEngine outputs

### Tool 17: AnomalyDetector
- **Purpose:** Flags unusual transactions
- **Input:** New transaction, historical patterns
- **Output:** AnomalyScore(0-1), AnomalyType(unusual_amount, unusual_time, unusual_product)
- **Activation:** On every transaction
- **Integration:** Feeds GuardrailsEngine

### Tool 18: MpesaParser
- **Purpose:** Parses M-Pesa SMS messages
- **Input:** SMS text ("Confirmed. Ksh500.00 received from...")
- **Output:** ParsedTransaction(amount, sender, type, reference)
- **Activation:** When M-Pesa SMS received
- **Integration:** Feeds TransactionRecorder

### Tool 19: PricingAdvisor
- **Purpose:** Suggests optimal pricing
- **Input:** Product name, current price, market data
- **Output:** SuggestedPrice(range), MarketComparison(above/below average)
- **Activation:** When worker queries pricing, or periodically
- **Integration:** Uses backend MarketIntelligence + local transaction history

### Tool 20: RestockPredictor
- **Purpose:** Predicts when to restock
- **Input:** Current inventory, sales velocity, supplier schedule
- **Output:** RestockAlert(product, suggested_quantity, optimal_day)
- **Activation:** Daily check, after inventory changes
- **Integration:** Uses InventoryTracker, TransactionRecorder patterns

---

## ANGAVU BACKEND SUPERAGENT — 20 Tools

**ONE BRAIN, 20 TOOLS, ONE JOB:** "Transform anonymized worker data into economic intelligence"

### Tool 1: OODAOrchestrator
- **Purpose:** Continuous Observe-Orient-Decide-Act intelligence loop
- **Input:** Data from all sources (sync, market signals, buyer queries)
- **Output:** Actions (generate report, update model, alert partner)
- **Activation:** Continuous (fast: per-sync, medium: hourly, slow: daily, deep: weekly)
- **Integration:** Central brain — all other tools are capabilities

### Tool 2: MarketAnalyzer
- **Purpose:** Aggregated demand patterns from anonymized data
- **Input:** 100K+ anonymized transactions
- **Output:** DemandSignal(product, region, trend), PriceElasticity, SeasonalPattern
- **Activation:** Hourly aggregation, daily analysis
- **Integration:** Feeds Soko Pulse, PricingAdvisor on devices

### Tool 3: CreditScorer (Alama Score)
- **Purpose:** Credit scoring from business transaction data
- **Input:** Worker transaction history (anonymized aggregates)
- **Output:** CreditScore(300-850), confidence, factors[], risk_level
- **Activation:** On-demand from bank partners, weekly batch recalculation
- **Integration:** Uses TransactionRecorder data from devices

### Tool 4: DistributionAnalyzer
- **Purpose:** FMCG distribution gap analysis
- **Input:** Product sales by region, product availability
- **Output:** DistributionGap(region, product, opportunity_size)
- **Activation:** Weekly analysis
- **Integration:** Feeds Soko Pulse for FMCG buyers

### Tool 5: FMCGIntelligence
- **Purpose:** Manufacturer intelligence products
- **Input:** Aggregated market data
- **Output:** FMCGReport(demand_forecast, competitor_analysis, pricing_optimization)
- **Activation:** Monthly reports, on-demand queries
- **Integration:** Uses MarketAnalyzer, DistributionAnalyzer

### Tool 6: HealthMetrics
- **Purpose:** Worker health economics
- **Input:** Work patterns, income stability, insurance coverage
- **Output:** HealthRiskScore, InsuranceEligibility, HealthSavingsAdvice
- **Activation:** Quarterly analysis
- **Integration:** Uses CreditScorer, transaction patterns

### Tool 7: EconomicAnalyzer
- **Purpose:** GDP estimation, inflation tracking from informal sector data
- **Input:** Aggregated transaction volumes, prices across regions
- **Output:** GDPEstimate, InflationRate, EmploymentIndex, RegionalEconomicHealth
- **Activation:** Monthly (compared with official KNBS data)
- **Integration:** Uses MarketAnalyzer aggregated data

### Tool 8: FederatedAggregator
- **Purpose:** Privacy-preserving model aggregation
- **Input:** Encrypted gradients from 100K+ devices
- **Output:** Aggregated model update, global model version
- **Activation:** Weekly aggregation round
- **Integration:** Receives from SyncEngine on devices, pushes ModelDistributor

### Tool 9: DifferentialPrivacyEngine
- **Purpose:** Adds calibrated noise for privacy (ε=0.1)
- **Input:** Raw aggregated data
- **Output:** Noised data (ε=0.1 differential privacy)
- **Activation:** Before any data leaves aggregation layer
- **Integration:** Wraps all data outputs from MarketAnalyzer, CreditScorer

### Tool 10: kAnonymityEnforcer
- **Purpose:** Ensures k≥10 anonymity for all queries
- **Input:** Query result, cohort data
- **Output:** Query result (if k≥10), or "insufficient data" (if k<10)
- **Activation:** On every data query
- **Integration:** Wraps APIGateway responses

### Tool 11: SyncReceiver
- **Purpose:** Receives and validates data from devices
- **Input:** Encrypted batch from device
- **Output:** Acknowledgment, sync status, conflicts resolved
- **Activation:** On every device sync
- **Integration:** Entry point for device data → OODA loop

### Tool 12: ModelDistributor
- **Purpose:** Pushes model updates to devices
- **Input:** Aggregated model update from FederatedAggregator
- **Output:** Delta-encoded update (200KB-2MB), delivery status
- **Activation:** After FederatedAggregator completes
- **Integration:** Pushes to devices via SyncEngine

### Tool 13: WhatsAppSender
- **Purpose:** Sends reports and alerts to workers via WhatsApp
- **Input:** Report content, recipient phone, message type
- **Output:** DeliveryStatus(sent, delivered, read)
- **Activation:** Daily reports, alerts, on-demand
- **Integration:** Uses ReportEngine, AlertGenerator

### Tool 14: AlertGenerator
- **Purpose:** Generates proactive alerts
- **Input:** Worker data, market conditions, anomalies
- **Output:** Alert(type, urgency, message, action_required)
- **Activation:** On anomaly detection, market changes, goal milestones
- **Integration:** Uses AnomalyDetector, MarketAnalyzer, CreditScorer

### Tool 15: ReportEngine
- **Purpose:** Generates business and intelligence reports
- **Input:** Data from all tools, report type, format
- **Output:** Report(HTML/PDF/JSON)
- **Activation:** Daily (worker reports), monthly (buyer reports), on-demand
- **Integration:** Uses all intelligence tools

### Tool 16: APIGateway
- **Purpose:** REST API for external intelligence buyers
- **Input:** API request with JWT auth
- **Output:** Intelligence data (anonymized, k≥10)
- **Activation:** On API request
- **Integration:** Wraps all intelligence tools with auth + rate limiting

### Tool 17: AuditLogger
- **Purpose:** Logs all operations for compliance
- **Input:** Action, actor, timestamp, data accessed
- **Output:** AuditEntry stored, compliance report
- **Activation:** On every operation
- **Integration:** Wraps all tools

### Tool 18: CircuitBreaker
- **Purpose:** Prevents cascade failures
- **Input:** Service health status
- **Output:** CircuitState(closed/open/half-open), fallback response
- **Activation:** On every external call
- **Integration:** Wraps database, Redis, ClickHouse, external API calls

### Tool 19: RateLimiter
- **Purpose:** Prevents API abuse
- **Input:** API request, client identifier
- **Output:** Allowed/Denied, retry_after
- **Activation:** On every API request
- **Integration:** Wraps APIGateway

### Tool 20: SecretRotator
- **Purpose:** Auto-rotates encryption keys and secrets
- **Input:** Current secret, rotation schedule
- **Output:** New secret, old secret deprecated
- **Activation:** Encryption keys (90d), JWT (30d), webhooks (90d), API keys (180d)
- **Integration:** Wraps SecurityGuard, all authentication

---

## Architecture: One Brain, Many Tools

```
MSAIDIZI SUPERAGENT (On-Device)
┌─────────────────────────────────────────────┐
│              ONE BRAIN                       │
│         SuperagentHarness                    │
│  Intent → Context → Tools → Response → Guard │
├─────────────────────────────────────────────┤
│  20 TOOLS (activated as needed):            │
│  TransactionRecorder  InventoryTracker      │
│  CFOEngine           VoicePipeline          │
│  LanguageDetector    CodeSwitchHandler       │
│  GamificationEngine  GoalTracker            │
│  ReceiptScanner      WhatsAppReporter       │
│  SyncEngine          SecurityGuard          │
│  ModelDownloader     AdaptiveLearner        │
│  MemoryManager       GuardrailsEngine       │
│  AnomalyDetector     MpesaParser            │
│  PricingAdvisor      RestockPredictor       │
├─────────────────────────────────────────────┤
│  5-LAYER MEMORY                             │
│  Working → Conversation → Daily →           │
│  Patterns → Knowledge                       │
├─────────────────────────────────────────────┤
│  FLYWHEEL                                   │
│  Use → Learn → Improve → Use More           │
└─────────────────────────────────────────────┘

ANGAVU BACKEND SUPERAGENT (Cloud)
┌─────────────────────────────────────────────┐
│              ONE BRAIN                       │
│         OODAOrchestrator                     │
│  Observe → Orient → Decide → Act            │
├─────────────────────────────────────────────┤
│  20 TOOLS (activated as needed):            │
│  OODAOrchestrator    MarketAnalyzer         │
│  CreditScorer        DistributionAnalyzer   │
│  FMCGIntelligence    HealthMetrics          │
│  EconomicAnalyzer    FederatedAggregator    │
│  DifferentialPrivacy kAnonymityEnforcer     │
│  SyncReceiver        ModelDistributor       │
│  WhatsAppSender      AlertGenerator         │
│  ReportEngine        APIGateway             │
│  AuditLogger         CircuitBreaker         │
│  RateLimiter         SecretRotator          │
├─────────────────────────────────────────────┤
│  COLLECTIVE INTELLIGENCE                    │
│  Aggregate → Analyze → Monetize → Grow      │
├─────────────────────────────────────────────┤
│  DUAL FLYWHEEL                              │
│  Device ←→ Sync ←→ Backend                  │
│  Personal improvement + Collective intel     │
└─────────────────────────────────────────────┘
```

---

## Summary

| Superagent | Tools | Job | Flywheel |
|-----------|-------|-----|----------|
| **Msaidizi** (on-device) | 20 tools | Help THIS worker run THEIR business | Personal learning loop |
| **Angavu Backend** (cloud) | 20 tools | Transform worker data into economic intelligence | Collective intelligence loop |
| **Together** | 40 tools | Make informal economy visible | Dual flywheel (device ↔ backend) |

**ONE BRAIN. 20 TOOLS. ONE JOB.** That's the superagent per Jensen Huang's vision.

---

*Defined by Council CTO. July 2025.*
