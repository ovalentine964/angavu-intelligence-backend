# Harness Concept Applied to Angavu Intelligence Backend

**Date:** 2026-07-14  
**Scope:** Architecture research + implementation plan

---

## 1. What Is a "Harness"?

A harness wraps around models/agents to **control, monitor, and orchestrate** them. Think of it as the "exoskeleton" around raw AI capabilities:

| Function | What It Does | Example |
|---|---|---|
| **Control** | Timeout, retry, circuit-break, rate-limit | Kill an agent call after 30s |
| **Monitor** | Trace, measure, alert on every call | Log every LLM call with latency + tokens |
| **Orchestrate** | Route, fallback, load-balance | If model A fails, try model B |
| **Validate** | Check inputs/outputs against schemas | Reject a credit score outside 300-850 |
| **Govern** | Cost tracking, privacy, audit trail | Per-user monthly spend cap |

**Industry context (2026):**
- **DeerFlow** (ByteDance) explicitly calls itself a "super-agent harness" — it orchestrates sub-agents, memory, and sandboxes via LangGraph
- **Microsoft Agent Framework** (BUILD 2026) introduced "Agent Harness" as a first-class primitive
- **Self-Harness** (research, June 2026) lets agents rewrite their own harness rules, boosting performance up to 60%

---

## 2. Existing Harness Patterns in Angavu

**The good news: Angavu already has significant harness infrastructure.** The patterns are there but fragmented — they need to be unified and gaps filled.

### 2.1 ✅ AgentFactory (factory.py) — Lifecycle Harness

**What it does:** Creates, wires, starts, and stops all agents in dependency order. This IS a harness — it controls the full agent lifecycle.

**Harness functions present:**
- Startup ordering (EventBus → Tracer → Protocols → Utility → Core → Domain → MetaAgent)
- Graceful shutdown in reverse order
- Service dependency injection
- Optional feature toggles (`enable_loops`, `enable_long_horizon`, `enable_deerflow`)

**What's missing:**
- No per-agent health probes during startup
- No automatic restart on agent crash
- No resource limits (memory, CPU per agent)

### 2.2 ✅ EventBus (event_bus.py) — Communication Harness

**What it does:** Redis Streams-based inter-agent communication with consumer groups, dead letter queues, backpressure, idempotency, and event persistence.

**Harness functions present:**
- **Dead letter queue** — failed events are captured, not lost
- **Backpressure** — high-water/low-water throttling prevents overload
- **Idempotency** — deduplicates events within a 1-hour window
- **Event persistence** — JSONL audit trail for replay
- **Horizontal scaling** — consumer groups for multi-instance deployment
- **Graceful degradation** — falls back to in-memory when Redis is unavailable

**What's missing:**
- No event-level cost attribution
- No priority queuing (all events are equal)
- No schema validation on published events

### 2.3 ✅ SupervisorAgent (loops/core.py) — Execution Harness

**What it does:** Wraps agent execution with supervision policies: retry, fallback, escalate, skip. Tracks per-agent performance metrics.

**Harness functions present:**
- **Retry** with configurable max attempts
- **Fallback** to alternative agents on failure
- **Escalation** when retries exhausted
- **Performance tracking** per agent (success rate, avg duration)
- **Result validation** via pluggable validation functions

**What's missing:**
- No timeout enforcement (relies on agent's own timeout)
- No circuit breaker pattern (keeps trying failing agents)
- No cost tracking

### 2.4 ✅ MetaAgent (meta_agent.py) — Routing Harness

**What it does:** Routes requests to best-suited agent based on capabilities and historical performance. Resolves conflicts. Facilitates cross-agent learning.

**Harness functions present:**
- **Capability-based routing** — matches required capability to agent
- **Performance-ranked selection** — prefers agents with higher success rates
- **Conflict resolution** — auto-resolves by preferring higher-performing agent
- **Health checking** — can check all registered agents
- **Cross-agent learning** — shares insights across agents

### 2.5 ✅ DeerFlow Integration (deerflow/) — Orchestration Harness

**What it does:** Bridges DeerFlow's LangGraph-based agent harness with Angavu's services. Uses DeerFlow's 21+ middlewares (summarization, memory, loop detection, etc.).

**Harness functions present:**
- Agent creation via DeerFlow factory (not custom code)
- Middleware chain configuration
- Runtime features toggling (sandbox, memory, vision, loop detection)
- Thread state management via LangGraph

### 2.6 ✅ ModelRouter (services/model_router.py) — Inference Harness

**What it does:** Routes inference across providers with fallback chains, token compression, cost tracking, and per-user budgets.

**Harness functions present:**
- **Task-based routing** — simple tasks → on-device, complex → Angavu Cloud
- **Fallback chains** — on-device → Angavu Cloud → degraded mode
- **Token compression** — reduces cost
- **Per-user budget tracking** — caps monthly spend
- **Reasoning effort scaling** — adjusts compute based on task complexity

### 2.7 ✅ AgentTracer (observability.py) — Observability Harness

**What it does:** Traces every agent lifecycle event (observe → think → act → reflect) with structured logging and in-memory trace store.

**Harness functions present:**
- Full lifecycle tracing (start → decision → result → end)
- Per-agent metrics (count, error rate, avg/p95 latency)
- Active trace monitoring
- Context sanitization (truncates large values)

### 2.8 ✅ EvalHarness (evals/harness.py) — Quality Harness

**What it does:** Runs test cases through LLM/agent pipelines and scores outputs against expected results.

**Harness functions present:**
- Test case loading and execution
- Heuristic + LLM-judge scoring
- Per-category metrics and pass rates
- Concurrent execution with semaphore

### 2.9 ✅ Loop Patterns (loops/core.py) — Reasoning Harness

Five loop patterns that harness agent reasoning:
- **ReAct** — explicit reasoning trace (think → act → observe → reflect)
- **Reflexion** — self-critique with retry (execute → critique → revise → re-execute)
- **Plan-and-Execute** — multi-step planning with replanning on failure
- **Event Sourcing** — full audit trail with replay capability
- **OODA Loop** — fast decision loop with persistent orientation state

---

## 3. What's MISSING — Gaps to Fill

Despite the rich existing infrastructure, several critical harness functions are absent:

### 3.1 🔴 Unified Agent Execution Harness

**Problem:** Each agent's `handle_event()` has its own error handling. There's no single wrapper that enforces timeout, retry, circuit-breaking, and metrics collection around EVERY agent call.

**Current state:** The SupervisorAgent does this, but it's optional and only used when explicitly invoked. Most agent calls go through `handle_event()` directly.

**What to build:** A decorator/middleware that wraps `BiasharaAgent.handle_event()`:

```python
class AgentExecutionHarness:
    """Wraps every agent call with timeout, retry, circuit-breaker, metrics."""
    
    def __init__(self, timeout_s=30, max_retries=2, circuit_breaker_threshold=5):
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._metrics = AgentMetricsCollector()
    
    async def execute(self, agent: BiasharaAgent, event: AgentEvent) -> AgentResult:
        cb = self._get_circuit_breaker(agent.name)
        if cb.is_open:
            return AgentResult(success=False, error=f"Circuit open for {agent.name}")
        
        for attempt in range(self._max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    agent.handle_event(event),
                    timeout=self._timeout_s,
                )
                cb.record_success()
                self._metrics.record(agent.name, result)
                return result
            except asyncio.TimeoutError:
                cb.record_failure()
                if attempt == self._max_retries:
                    return AgentResult(success=False, error="Timeout after retries")
            except Exception as e:
                cb.record_failure()
                if attempt == self._max_retries:
                    return AgentResult(success=False, error=str(e))
```

### 3.2 🔴 Circuit Breaker Pattern

**Problem:** If an agent keeps failing (e.g., DB down), the system keeps trying it, wasting resources and delaying fallback.

**What to build:**

```python
class CircuitBreaker:
    """Prevents cascading failures by stopping calls to failing agents."""
    
    def __init__(self, failure_threshold=5, recovery_timeout_s=60):
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._recovery_timeout_s = recovery_timeout_s
        self._state = "closed"  # closed | open | half-open
        self._last_failure_time = 0
    
    def record_success(self):
        self._failure_count = 0
        self._state = "closed"
    
    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self._failure_threshold:
            self._state = "open"
    
    @property
    def is_open(self) -> bool:
        if self._state == "open":
            if time.time() - self._last_failure_time > self._recovery_timeout_s:
                self._state = "half-open"
                return False
            return True
        return False
```

### 3.3 🔴 Per-Agent Cost Tracking

**Problem:** The ModelRouter tracks inference cost, but there's no attribution to specific agents or users at the agent execution level.

**What to build:** A cost tracker that hooks into the AgentTracer:

```python
@dataclass
class AgentCostRecord:
    agent_name: str
    user_id: Optional[str]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: float
    model_used: str
    timestamp: float

class AgentCostTracker:
    """Tracks cost per agent, per user, per task type."""
    
    def __init__(self, monthly_budget_usd: float = 0.0):  # $0 for zero-cost strategy
        self._records: List[AgentCostRecord] = []
        self._monthly_budget = monthly_budget_usd
        self._monthly_totals: Dict[str, float] = defaultdict(float)  # user_id → cost
    
    def record(self, record: AgentCostRecord):
        self._records.append(record)
        if record.user_id:
            self._monthly_totals[record.user_id] += record.cost_usd
    
    def is_over_budget(self, user_id: str) -> bool:
        return self._monthly_totals[user_id] >= self._monthly_budget
    
    def get_agent_costs(self, agent_name: str, days: int = 30) -> Dict:
        cutoff = time.time() - days * 86400
        records = [r for r in self._records if r.agent_name == agent_name and r.timestamp > cutoff]
        return {
            "total_calls": len(records),
            "total_tokens": sum(r.input_tokens + r.output_tokens for r in records),
            "total_cost_usd": sum(r.cost_usd for r in records),
            "avg_latency_ms": sum(r.duration_ms for r in records) / max(len(records), 1),
        }
```

### 3.4 🟡 Canary Deployment Harness

**Problem:** No way to gradually roll out new agent versions (1% → 10% → 50% → 100%).

**What to build:**

```python
class CanaryRouter:
    """Routes a percentage of traffic to a new agent version."""
    
    def __init__(self):
        self._versions: Dict[str, List[Tuple[BiasharaAgent, float]]] = {}
        # agent_name → [(agent_instance, traffic_weight), ...]
    
    def register_version(self, agent_name: str, agent: BiasharaAgent, weight: float):
        if agent_name not in self._versions:
            self._versions[agent_name] = []
        self._versions[agent_name].append((agent, weight))
    
    def route(self, agent_name: str) -> BiasharaAgent:
        versions = self._versions.get(agent_name, [])
        if not versions:
            raise ValueError(f"No versions registered for {agent_name}")
        # Weighted random selection
        total = sum(w for _, w in versions)
        r = random.uniform(0, total)
        cumulative = 0
        for agent, weight in versions:
            cumulative += weight
            if r <= cumulative:
                return agent
        return versions[-1][0]
```

### 3.5 🟡 Data Pipeline Validation Harness

**Problem:** Intelligence pipeline outputs are not validated against schemas or business rules before delivery.

**What to build:** A validation layer for the intelligence pipeline:

```python
class PipelineValidator:
    """Validates intelligence pipeline outputs before delivery."""
    
    def __init__(self):
        self._validators: Dict[str, List[Callable]] = {}
    
    def register(self, output_type: str, validator: Callable[[Dict], Tuple[bool, str]]):
        self._validators.setdefault(output_type, []).append(validator)
    
    def validate(self, output_type: str, data: Dict) -> Tuple[bool, List[str]]:
        errors = []
        for validator in self._validators.get(output_type, []):
            ok, msg = validator(data)
            if not ok:
                errors.append(msg)
        return len(errors) == 0, errors

# Example validators:
def validate_credit_score(data: Dict) -> Tuple[bool, str]:
    score = data.get("credit_score", 0)
    if not (300 <= score <= 850):
        return False, f"Credit score {score} outside valid range 300-850"
    return True, ""

def validate_market_forecast(data: Dict) -> Tuple[bool, str]:
    confidence = data.get("confidence", 0)
    if not (0 <= confidence <= 1):
        return False, f"Confidence {confidence} outside 0-1 range"
    return True, ""
```

### 3.6 🟡 Federated Learning Privacy Harness

**Problem:** The federated learning API exists but lacks privacy guarantees beyond k-anonymity.

**What to build:** Privacy-preserving wrapper around FL aggregation:

```python
class PrivacyHarness:
    """Enforces privacy guarantees on federated learning."""
    
    def __init__(self, epsilon=1.0, delta=1e-5, min_clients=10):
        self._epsilon = epsilon  # Differential privacy budget
        self._delta = delta
        self._min_clients = min_clients
    
    def validate_round(self, gradients: List[Dict], metadata: Dict) -> Tuple[bool, str]:
        if len(gradients) < self._min_clients:
            return False, f"Need {self._min_clients} clients, got {len(gradients)}"
        # Check gradient clipping
        for i, grad in enumerate(gradients):
            norm = self._compute_norm(grad)
            if norm > self._max_grad_norm:
                return False, f"Client {i} gradient norm {norm:.2f} exceeds max {self._max_grad_norm}"
        return True, ""
    
    def add_noise(self, aggregated_gradient: Dict) -> Dict:
        """Add calibrated Gaussian noise for differential privacy."""
        noise_scale = self._max_grad_norm * sqrt(2 * log(1.25 / self._delta)) / self._epsilon
        return {k: v + np.random.normal(0, noise_scale, v.shape) for k, v in aggregated_gradient.items()}
```

---

## 4. Implementation Plan

### Phase 1: Unified Execution Harness (Week 1) — **HIGHEST PRIORITY**

This is the fastest path to measurable improvement. Every agent call gets wrapped.

**Files to create:**
```
app/agents/harness/
├── __init__.py
├── execution.py      # AgentExecutionHarness + CircuitBreaker
├── cost_tracker.py   # Per-agent, per-user cost tracking
└── validators.py     # Output validation schemas
```

**Changes to existing files:**
- `app/agents/base.py` — Add `harness` parameter to `handle_event()`; integrate harness into lifecycle
- `app/agents/factory.py` — Create and inject harness during `create_all()`
- `app/agents/observability.py` — Extend `AgentTracer` with cost recording hooks

**Integration point:** Modify `BiasharaAgent.handle_event()` to route through the harness:

```python
# In base.py — modify handle_event to use harness
async def handle_event(self, event: AgentEvent) -> AgentResult:
    if self._harness:
        return await self._harness.execute(self, event)
    return await self._handle_event_inner(event)  # existing logic
```

### Phase 2: Circuit Breakers + Model Fallback (Week 2)

**Files to create:**
```
app/agents/harness/
├── circuit_breaker.py   # Standalone circuit breaker with Redis state
└── model_harness.py     # Wraps ModelRouter with circuit breakers per provider
```

**Integration:** Wire circuit breakers into:
- `AgentFactory._attach_deerflow()` — circuit-break DeerFlow agent calls
- `ModelRouter` — circuit-break individual providers
- `EventBus` — circuit-break Redis operations (already has fallback, add circuit breaker)

### Phase 3: Canary + Observability Dashboard (Week 3-4)

**Files to create:**
```
app/agents/harness/
├── canary.py           # CanaryRouter for gradual rollouts
└── dashboard.py        # API endpoints for harness metrics
```

**API endpoints:**
```
GET  /api/v1/harness/status          — Overall harness health
GET  /api/v1/harness/agents          — Per-agent metrics (cost, latency, errors)
GET  /api/v1/harness/circuit-breakers — Circuit breaker states
GET  /api/v1/harness/costs           — Cost breakdown by agent/user
POST /api/v1/harness/canary          — Configure canary routing
```

### Phase 4: Data Pipeline + FL Privacy (Week 5+)

- Pipeline validators for intelligence outputs
- Privacy harness for federated learning
- Automated drift detection

---

## 5. Concrete Code-Level Recommendations

### Recommendation 1: Create `app/agents/harness/execution.py`

This is the single most impactful change. It wraps every agent call with:
- Timeout (configurable per agent, default 30s)
- Retry (configurable, default 2 retries)
- Circuit breaker (opens after 5 consecutive failures, recovers after 60s)
- Metrics collection (latency, success rate, token usage)
- Cost attribution (per agent, per user)

### Recommendation 2: Extend `AgentTracer` with cost hooks

Add `record_cost()` method to `AgentTracer` that also writes to a cost tracker. This piggybacks on existing infrastructure.

### Recommendation 3: Add `PipelineValidator` to intelligence pipeline

The intelligence pipeline (`intelligence_pipeline.py`) produces outputs that are delivered via WhatsApp. Add validation before delivery:

```python
# In intelligence_pipeline.py, before delivering results:
validator = PipelineValidator()
ok, errors = validator.validate("market_forecast", result)
if not ok:
    result = {"error": "Validation failed", "details": errors}
```

### Recommendation 4: Wire circuit breakers into DeerFlow integration

The DeerFlow integration (`deerflow/integration.py`) creates agents via factory. Wrap each agent creation with a circuit breaker so that if DeerFlow agents fail, the system falls back to native Angavu agents.

### Recommendation 5: Add harness health endpoint

Create `GET /api/v1/harness/health` that returns:
```json
{
  "execution_harness": {
    "active_circuit_breakers": 0,
    "total_calls_24h": 15420,
    "success_rate": 0.987,
    "avg_latency_ms": 245
  },
  "cost_tracker": {
    "total_cost_24h_usd": 0.00,
    "top_agents": ["IntelligenceGenerator", "ReportGenerator"]
  },
  "validators": {
    "total_validations": 3200,
    "validation_failures": 12
  }
}
```

---

## 6. Summary: Harness Maturity Assessment

| Harness Layer | Status | Maturity | Priority |
|---|---|---|---|
| **Lifecycle** (AgentFactory) | ✅ Exists | 🟢 Strong | — |
| **Communication** (EventBus) | ✅ Exists | 🟢 Strong | — |
| **Supervision** (SupervisorAgent) | ✅ Exists | 🟡 Good | Extend with circuit breakers |
| **Routing** (MetaAgent) | ✅ Exists | 🟡 Good | Add cost-awareness |
| **Orchestration** (DeerFlow) | ✅ Exists | 🟡 Good | Add circuit breakers |
| **Inference** (ModelRouter) | ✅ Exists | 🟢 Strong | — |
| **Observability** (AgentTracer) | ✅ Exists | 🟡 Good | Add cost tracking |
| **Quality** (EvalHarness) | ✅ Exists | 🟡 Good | Wire into CI/CD |
| **Reasoning** (Loop patterns) | ✅ Exists | 🟢 Strong | — |
| **Execution** (timeout/retry/CB) | ❌ Missing | 🔴 Gap | **Build first** |
| **Cost Attribution** | ❌ Missing | 🔴 Gap | **Build second** |
| **Canary Deployment** | ❌ Missing | 🟡 Gap | Build in phase 3 |
| **Pipeline Validation** | ❌ Missing | 🟡 Gap | Build in phase 4 |
| **FL Privacy** | ❌ Missing | 🟡 Gap | Build in phase 4 |

**Bottom line:** Angavu already has ~70% of a production harness. The critical missing piece is a **unified execution harness** that wraps every agent call with timeout/retry/circuit-breaker/cost-tracking. Building this single component unlocks the remaining 30% incrementally.
