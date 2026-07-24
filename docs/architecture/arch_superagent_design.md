# Superagent Architecture Design: Msaidizi + Angavu Backend

> **Date:** 2026-07-24
> **Authors:** Superagent Architecture Team
> **Status:** Architecture Design v1.0
> **Classification:** Internal — Angavu Intelligence Ltd.

---

## Executive Summary

This document designs how Msaidizi (on-device, 5-agent Android app) and Angavu Intelligence Backend (6-agent cloud system) evolve from **multi-agent systems** into **true superagents** — domain-specific, self-improving AI systems built for ONE job each, per Jensen Huang's superagent definition.

**Key insight:** A superagent is NOT "many agents working together." A superagent is a **single purpose-built intelligence** with a harness (orchestration), model, context, tools, memory, and guardrails — that improves through a flywheel. The existing multi-agent architecture is restructured into two unified superagents that share intelligence through privacy-preserving channels.

---

## Part 1: Research — Patterns We Reuse

### 1.1 DeerFlow 2.0 Patterns

**What is DeerFlow?**
DeerFlow (Deep Exploration and Efficient Research Flow) is ByteDance's open-source **superagent harness** — GitHub #1 trending (Feb 2026). Version 2.0 is a ground-up rewrite sharing no code with v1.

**Architecture:**
```
┌─────────────────────────────────────────────┐
│           DeerFlow Superagent Harness        │
├─────────────────────────────────────────────┤
│  Skills (loaded progressively, on-demand)   │
│  ├── Deep Search    ├── Code Execution      │
│  ├── Frontend Design └── Custom Skills      │
├─────────────────────────────────────────────┤
│  Sub-Agents (spawned for complex tasks)     │
│  Sandbox (Docker: browser, shell, files)    │
│  Memory (long-term + short-term)            │
│  Context Engineering (compaction, injection) │
├─────────────────────────────────────────────┤
│  LangGraph Orchestration Layer              │
│  Message Gateway (IM channels)              │
└─────────────────────────────────────────────┘
```

**Key DeerFlow patterns applicable to Msaidizi:**

| Pattern | DeerFlow Implementation | Msaidizi Adaptation |
|---------|------------------------|---------------------|
| **Progressive skill loading** | Skills loaded only when needed, not all at once | Agent capabilities activated per context (don't load inventory skills when recording a sale) |
| **Sub-agent spawning** | Complex tasks spawn child agents with isolated context | Orchestrator spawns specialized sub-tasks (e.g., "analyze this week's cash flow" → AnalysisAgent gets temporary deep-context) |
| **Sandbox isolation** | Docker containers for code execution | On-device: isolated execution contexts per agent task; Backend: container sandbox for research agents |
| **Context engineering** | Manual compaction, smart injection, session goals | Compress conversation history into working memory; inject relevant long-term memories per query |
| **Session goals** | User defines what the session should achieve | Worker defines business goal ("I want to understand my profit this week") → all agents align |
| **Long-horizon tasks** | Tasks spanning minutes to hours with checkpointing | Financial analysis tasks that run across multiple sync cycles, checkpointed to disk |
| **Multi-model support** | Different models for different agent roles | On-device: Qwen 0.8B for fast responses; Backend: DeepSeek Reasoner for complex analysis |

### 1.2 OpenClaw Patterns

**What makes OpenClaw special:**

OpenClaw is a production agent runtime with battle-tested patterns for real-world agent deployment:

| OpenClaw Pattern | How It Works | Msaidizi Application |
|-----------------|-------------|---------------------|
| **Tool Registry** | Tools are policy-filtered, named, case-sensitive. Agent sees only what it's allowed to use. | Each agent role sees only its relevant tools (BusinessAgent can't access credit scoring; CreditAgent can't modify transactions) |
| **Session Management** | Sessions are keyed by `agent:main:subagent:UUID`, with full transcript logging, cost tracking, and replay | Every Msaidizi interaction is a session with full audit trail — critical for financial data |
| **Sub-Agent Delegation** | Main agent spawns subagents with specific tasks. Subagents are ephemeral, auto-announce results, don't initiate. | Orchestrator spawns AnalysisAgent for "calculate weekly profit" — it completes, reports back, terminates |
| **TaskFlow** | Durable multi-step jobs with owner context, state, waits, and child tasks. Survives restarts. | Financial workflows that span multiple steps: record transaction → update inventory → check restock alert → notify via WhatsApp |
| **Memory Architecture** | Daily notes (`memory/YYYY-MM-DD.md`) + Long-term curated (`MEMORY.md`) + Wiki (compiled knowledge) | Working memory (current session) + Daily summaries + Long-term business patterns + Compiled financial knowledge |
| **Heartbeat System** | Periodic proactive checks — email, calendar, notifications. Batched, smart timing. | CFO Engine heartbeat: morning briefing, midday check, evening summary. Smart timing based on worker's schedule. |
| **Safety/Guardrails** | Red lines defined in AGENTS.md. No destructive ops without asking. Trash > rm. External actions require confirmation. | Financial guardrails: never delete transactions, confirm large expense entries, flag anomalies before syncing |
| **Skill System** | SKILL.md files define when/how to use capabilities. Loaded on-demand. | Domain skills: `voice_transaction.md`, `credit_assessment.md`, `inventory_management.md` — loaded when context matches |
| **Code-Switching Detection** | OpenClaw handles multi-language, multi-channel (Telegram, Discord, WhatsApp) | Msaidizi already detects code-switching between Swahili/Sheng/English — extend to agent routing |
| **Graceful Degradation** | Safe mode, crash recovery, incomplete task recovery | Every initialization wrapped in try/catch; app degrades instead of crashing — already implemented |

### 1.3 Hermes Model Patterns

**What is Hermes?**
NousResearch's Hermes is a family of open-weight LLMs fine-tuned for **function calling and tool use**. Key variants:

- **Hermes 2/3** — Fine-tuned on structured function calling datasets
- **Hermes models excel at:** JSON schema adherence, parallel tool calls, nested function arguments, system prompt following

**Why Hermes matters for Msaidizi:**

| Capability | Hermes Approach | Msaidizi Relevance |
|-----------|----------------|-------------------|
| **Structured function calling** | Models trained to output valid JSON tool calls | On-device Qwen 0.8B can be fine-tuned Hermes-style for transaction recording functions |
| **Tool use with small models** | Hermes proves 7B-13B models can do reliable function calling | Validates that on-device 0.8B model (with Hermes-style fine-tuning) can handle structured tool calls |
| **System prompt adherence** | Strong instruction following from system prompts | Agent behavior can be controlled via system prompts rather than complex orchestration code |
| **Multi-turn tool use** | Maintains context across multiple tool call rounds | Recording a transaction may require multiple voice clarifications — "How much?" "For which product?" |

**Hermes-style adaptation for on-device:**
The Qwen 0.8B model running on-device should be fine-tuned with Hermes-style function calling datasets specific to:
- Transaction recording: `record_transaction(amount, product, quantity, payment_method, language)`
- Inventory check: `check_inventory(product_name)` → returns stock level
- Cash flow query: `get_cash_flow(period)` → returns summary
- Goal update: `update_goal(goal_id, amount)` → updates progress

This replaces free-form LLM output with **structured, validated function calls** — reducing hallucination and increasing reliability on small models.

---

## Part 2: On-Device Superagent Architecture — Msaidizi

### 2.1 The Transformation: 5 Agents → 1 Superagent

**Current state (multi-agent):**
```
Orchestrator → routes to → BusinessAgent
                         → AnalysisAgent
                         → AdvisorAgent
                         → LearningAgent
```
Each agent is independent. The orchestrator is a router. There's no unified brain.

**Target state (superagent):**
```
┌──────────────────────────────────────────────────────────────┐
│                 MSAIDIZI SUPERAGENT                           │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │              HARNESS (Orchestration Layer)              │  │
│  │  Intent Router → Context Assembly → Agent Selection    │  │
│  │  → Tool Invocation → Response Synthesis → Guard Check  │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                    MODEL LAYER                          │  │
│  │  Primary: Qwen 0.8B (Hermes-style function calling)   │  │
│  │  Fallback: Cloud Qwen 7B (when online)                │  │
│  │  Specialized: Whisper STT + Piper TTS                  │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                   CONTEXT ENGINE                        │  │
│  │  Working Memory (current session state)                │  │
│  │  Conversation Memory (recent interactions)             │  │
│  │  Business Memory (patterns, preferences, history)      │  │
│  │  Knowledge Base (financial_knowledge_sw.json)          │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                    TOOLS REGISTRY                       │  │
│  │  Transaction  │ Inventory │ CFO Analysis │ Voice       │  │
│  │  Goals/Loans  │ Gamific.  │ M-Pesa       │ Scanner     │  │
│  │  WhatsApp     │ Sync      │ Security     │ Language    │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                   MEMORY SYSTEM                         │  │
│  │  L1: Working Memory (in-RAM, session-scoped)           │  │
│  │  L2: Conversation Buffer (last N turns, SQLite)        │  │
│  │  L3: Daily Summaries (compressed daily logs)           │  │
│  │  L4: Long-term Patterns (learned business behaviors)   │  │
│  │  L5: Knowledge Base (curated financial knowledge)      │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                  GUARDRAILS ENGINE                       │  │
│  │  Financial Integrity │ Input Validation │ Privacy       │  │
│  │  Anomaly Detection   │ Rate Limiting    │ Encryption    │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │               ADAPTIVE LEARNING ENGINE                  │  │
│  │  Vocabulary Expansion │ Pattern Recognition            │  │
│  │  User Behavior Model  │ Dialect Adaptation             │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 The Harness — How It Works

The harness is NOT a simple router. It's an **intelligent orchestration loop** inspired by DeerFlow's LangGraph approach and OpenClaw's TaskFlow:

```
INPUT (voice/text) 
  → [1] STT (if voice) + Language Detection
  → [2] Intent Classification (Hermes-style function calling)
  → [3] Context Assembly (pull relevant memories + business state)
  → [4] Capability Resolution (which tools/skills are needed?)
  → [5] Execution (invoke tools, chain results)
  → [6] Response Synthesis (natural language response)
  → [7] Guardrail Check (financial integrity, anomaly detection)
  → [8] Output (TTS or text) + Memory Update
  → [9] Background: Adaptive Learning (vocabulary, patterns)
```

**Key difference from current orchestrator:**
- Current: "This is a business query → route to BusinessAgent"
- Superagent: "This is a business query → assemble context → select relevant capabilities → execute with full business context → synthesize unified response"

The superagent doesn't "route to agents." It **activates capabilities** within a single unified context. The 5 agent roles become **5 capability modules** within one brain.

### 2.3 Memory Architecture — 5-Layer Hierarchy

Inspired by OpenClaw's `MEMORY.md` + daily notes + wiki pattern:

```
┌─────────────────────────────────────────────┐
│  L1: WORKING MEMORY (RAM, <1ms access)      │
│  Current session state, active context       │
│  Max: ~2KB (fits in Qwen context window)     │
│  Eviction: session end                       │
├─────────────────────────────────────────────┤
│  L2: CONVERSATION BUFFER (SQLite, ~5ms)      │
│  Last 20 conversation turns                  │
│  Compressed: key facts extracted per turn    │
│  Eviction: FIFO after 20 turns              │
├─────────────────────────────────────────────┤
│  L3: DAILY SUMMARIES (SQLite, ~10ms)         │
│  End-of-day compressed business summary      │
│  Revenue, expenses, profit, top products     │
│  Eviction: after 90 days (archived)          │
├─────────────────────────────────────────────┤
│  L4: LONG-TERM PATTERNS (SQLite, ~20ms)      │
│  Learned business behaviors & preferences    │
│  "Worker restocks tomatoes every Monday"     │
│  "Peak sales hours: 7-9 AM, 5-7 PM"         │
│  Eviction: never (curated, pruned quarterly) │
├─────────────────────────────────────────────┤
│  L5: KNOWLEDGE BASE (JSON, loaded at boot)   │
│  financial_knowledge_sw.json (46KB)          │
│  intent_patterns.json (21KB)                 │
│  vocab_*_seed.json (dialect seeds)           │
│  Eviction: never (updated via OTA)           │
└─────────────────────────────────────────────┘
```

**Context Assembly Algorithm:**
```
assemble_context(user_input, session_state):
  context = []
  context.append(L1_working_memory)          // Always include
  context.append(relevant_L2_turns)          // Last 5 relevant turns
  context.append(today_L3_summary)           // Today's business snapshot
  context.append(relevant_L4_patterns)       // Matched patterns (e.g., restock alert)
  context.append(matched_L5_knowledge)       // Financial knowledge relevant to query
  
  // Compress to fit model context window (~2048 tokens for Qwen 0.8B)
  return compress_to_budget(context, max_tokens=1500)
```

### 2.4 Flywheel — How the Superagent Improves

```
┌─────────────────────────────────────────────────────┐
│              MSAIDIZI FLYWHEEL                        │
│                                                       │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│   │  USE     │───→│  LEARN   │───→│ IMPROVE  │──┐   │
│   │ Worker   │    │ Adaptive │    │ Model +  │  │   │
│   │ speaks   │    │ learning │    │ patterns │  │   │
│   └──────────┘    └──────────┘    └──────────┘  │   │
│        ↑                                         │   │
│        └─────────────────────────────────────────┘   │
│                  USE MORE                             │
│          (better recognition →                       │
│           more usage → more data)                    │
└─────────────────────────────────────────────────────┘
```

**What feeds the flywheel on-device:**

| Loop | Input | Learning | Improvement |
|------|-------|----------|-------------|
| **Vocabulary loop** | Worker says product names | New words added to personal vocabulary | Better STT recognition for that worker's products |
| **Dialect loop** | Code-switching patterns detected | Language model adapted to worker's mix | More accurate transcription of mixed speech |
| **Business pattern loop** | Transaction history accumulates | Patterns emerge (restock cycles, peak hours) | Proactive alerts become more accurate |
| **CFO insight loop** | Worker follows/ignores advice | Advice relevance scored | Future advice prioritizes what worker actually acts on |
| **Cash flow loop** | Actual vs predicted cash flow | Prediction model calibrated | Forecasts improve accuracy over time |

**On-device flywheel constraints:**
- Can't do heavy model training on 2GB phone
- Flywheel operates through: (1) vocabulary/dictionary updates, (2) pattern rule updates, (3) context memory curation
- Model weights updated only via federated learning from backend (infrequent, WiFi-only)

### 2.5 Guardrails — Financial Data Integrity

```
┌─────────────────────────────────────────────────────┐
│              GUARDRAILS ENGINE                        │
├─────────────────────────────────────────────────────┤
│                                                       │
│  INPUT GUARDRAILS:                                   │
│  ├── Voice confidence threshold (>0.7 to auto-accept)│
│  ├── Amount validation (reasonable range per product) │
│  ├── Duplicate detection (same amount within 30s)     │
│  ├── Language safety filter (no injection attacks)    │
│  └── Rate limiting (max 100 transactions/hour)       │
│                                                       │
│  PROCESSING GUARDRAILS:                              │
│  ├── Transaction immutability (never delete, only     │
│  │   void with reason code)                          │
│  ├── Double-entry verification (revenue/cost balance) │
│  ├── Anomaly flagging (>3σ from rolling average)     │
│  ├── Offline queue integrity (checksummed batch)     │
│  └── Encryption at rest (SQLCipher + PQC)            │
│                                                       │
│  OUTPUT GUARDRAILS:                                  │
│  ├── Financial figures always shown with currency     │
│  ├── Advice disclaimers ("This is a suggestion...")  │
│  ├── No hallucinated numbers (tool-verified only)    │
│  ├── Credit score: never shown to user directly      │
│  │   (shown as "credit readiness" qualitative level) │
│  └── WhatsApp: no sensitive data in messages         │
│                                                       │
│  SYNC GUARDRAILS:                                    │
│  ├── Data anonymized before upload (k≥10)            │
│  ├── Differential privacy (ε=0.1)                    │
│  ├── No raw voice data ever uploaded                 │
│  ├── Encrypted transport (TLS 1.3 + PQC hybrid)     │
│  └── Consent verification before any data sharing    │
└─────────────────────────────────────────────────────┘
```

---

## Part 3: Backend Superagent Architecture — Angavu Intelligence

### 3.1 The Transformation: 6 Agents → 1 Superagent

**Current state (multi-agent):**
```
EventBus → research (DeepSeek Reasoner)
        → credit (DeepSeek Chat)
        → distribution (DeepSeek Chat)
        → fmcg (DeepSeek Chat)
        → health (DeepSeek Chat)
        → development (DeepSeek Reasoner)
```
Six independent agents communicating via EventBus. Each has its own model, config, and context.

**Target state (superagent):**
```
┌──────────────────────────────────────────────────────────────┐
│              ANGAVU BACKEND SUPERAGENT                        │
│              "Africa's Economic Nervous System"               │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │           HARNESS — OODA Orchestrator                  │  │
│  │  Observe → Orient → Decide → Act                       │  │
│  │  (Continuous loop, not per-request)                    │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │  TaskFlow (Durable Workflow Engine)              │  │  │
│  │  │  Long-horizon research jobs                      │  │  │
│  │  │  Cross-agent data pipelines                      │  │  │
│  │  │  Checkpoint + resume on failure                  │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                    MODEL LAYER                          │  │
│  │  Reasoning: DeepSeek Reasoner (complex analysis)       │  │
│  │  Chat: DeepSeek Chat (conversational, fast)            │  │
│  │  Cloud LLM: Qwen 7B (local inference)                 │  │
│  │  Specialized: XGBoost, scikit-learn (ML pipelines)     │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │               INTELLIGENCE MODULES                      │  │
│  │  (Formerly 6 agents, now 6 capability modules)         │  │
│  │                                                        │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐              │  │
│  │  │ Market   │ │ Credit   │ │ Distrib. │              │  │
│  │  │ Research │ │ Scoring  │ │ Analysis │              │  │
│  │  └──────────┘ └──────────┘ └──────────┘              │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐              │  │
│  │  │ FMCG     │ │ Health   │ │ Economic │              │  │
│  │  │ Intel    │ │ Metrics  │ │ Analysis │              │  │
│  │  └──────────┘ └──────────┘ └──────────┘              │  │
│  │                                                        │  │
│  │  All modules share: unified context, shared memory,    │  │
│  │  common data layer, single OODA loop                   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                   MEMORY SYSTEM                         │  │
│  │  L1: Request Context (current OODA cycle)              │  │
│  │  L2: Session Memory (buyer/worker interaction history) │  │
│  │  L3: Daily Intelligence (aggregated daily metrics)     │  │
│  │  L4: Market Patterns (long-term economic patterns)     │  │
│  │  L5: Knowledge Graph (worker profiles, product catalog)│  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │               COLLECTIVE INTELLIGENCE                   │  │
│  │  Federated Learning Aggregator                          │  │
│  │  Differential Privacy Engine (ε=0.1)                   │  │
│  │  Pattern Mining (cross-worker, cross-region)           │  │
│  │  Economic Indicators (GDP, inflation, employment)      │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                  GUARDRAILS ENGINE                       │  │
│  │  Data Anonymization │ k-Anonymity │ Prompt Guard       │  │
│  │  Rate Limiting │ Circuit Breakers │ Secret Rotation    │  │
│  │  Audit Logging │ Compliance │ Human-in-the-Loop       │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 OODA Loop — The Superagent's Brain

The OODA (Observe-Orient-Decide-Act) loop is the **continuous intelligence cycle** that makes the backend a superagent rather than a request-response API:

```
┌─────────────────────────────────────────────────────────────┐
│                    OODA LOOP (Continuous)                     │
│                                                              │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   │
│  │ OBSERVE │──→│ ORIENT  │──→│ DECIDE  │──→│   ACT   │   │
│  └────┬────┘   └────┬────┘   └────┬────┘   └────┬────┘   │
│       │              │              │              │         │
│  Ingest data    Synthesize    Select best    Execute       │
│  from all      context from  action given   decision:     │
│  sources:      memory +      current state  - Generate    │
│  - Sync data   patterns +    + constraints  report        │
│  - Market      market intel  + capabilities - Update      │
│  signals       + worker                   model           │
│  - Buyer       profiles                   - Alert         │
│  queries                                          partner  │
│  - WhatsApp    Orient phase              - Trigger        │
│  commands      identifies:               retraining       │
│  - Model       - Trends                               │
│  drift         - Anomalies      Decide phase         │
│  - Time        - Opportunities  uses:                 │
│  signals       - Risks          - Rule engine         │
│                                - ML model             │
│                                - LLM reasoning        │
│                                - Human escalation     │
└─────────────────────────────────────────────────────────────┘
```

**OODA cycle timing:**

| Cycle | Frequency | Trigger | Example |
|-------|-----------|---------|---------|
| **Fast loop** | Every sync event | New transaction batch from worker | Update worker profile, check anomaly, update daily summary |
| **Medium loop** | Every hour | Cron trigger | Aggregate hourly market signals, update Soko Pulse |
| **Slow loop** | Daily | 00:00 UTC | Generate daily intelligence reports, retrain drift-detected models |
| **Deep loop** | Weekly | Sunday 02:00 UTC | Full federated learning aggregation, economic indicator recalculation |

### 3.3 Federated Learning → Collective Intelligence

The federated learning system feeds the superagent's collective intelligence:

```
┌──────────────────────────────────────────────────────────────┐
│           FEDERATED LEARNING → COLLECTIVE INTELLIGENCE        │
│                                                              │
│  DEVICE LEVEL (Msaidizi App):                                │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Local Training (on-device)                            │  │
│  │  ├── Transaction pattern learning                      │  │
│  │  ├── Vocabulary adaptation                             │  │
│  │  ├── Cash flow prediction calibration                  │  │
│  │  └── Privacy: Differential Privacy (ε=0.1)            │  │
│  │                                                        │  │
│  │  Gradients only (never raw data)                       │  │
│  │  └── Encrypted → Sent to backend                      │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  AGGREGATION LEVEL (Angavu Backend):                         │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Federated Aggregator                                  │  │
│  │  ├── Secure aggregation of encrypted gradients         │  │
│  │  ├── k-Anonymity enforcement (k≥10 per cohort)        │  │
│  │  ├── Cohort formation: by region, worker type, lang   │  │
│  │  ├── Model update generation                           │  │
│  │  └── Push updated models back to devices              │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  INTELLIGENCE LEVEL (Superagent Brain):                      │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Collective Intelligence Emerges From:                  │  │
│  │  ├── Cross-worker pattern mining (anonymized)          │  │
│  │  ├── Regional economic indicators                      │  │
│  │  ├── Product demand signals                            │  │
│  │  ├── Pricing optimization data                         │  │
│  │  ├── Credit risk calibration                           │  │
│  │  └── Economic forecasting models                       │  │
│  │                                                        │  │
│  │  This intelligence is NOT individual worker data.      │  │
│  │  It's emergent knowledge from aggregate patterns.      │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 3.4 How the Flywheel Works on Backend

```
┌─────────────────────────────────────────────────────────────┐
│              ANGAVU BACKEND FLYWHEEL                          │
│                                                              │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐             │
│   │ COLLECT  │───→│ ANALYZE  │───→│ MONETIZE │──┐          │
│   │ Worker   │    │ OODA     │    │ Sell     │  │          │
│   │ data     │    │ loop     │    │ intel    │  │          │
│   └──────────┘    └──────────┘    └──────────┘  │          │
│        ↑                                         │          │
│        └─────────────────────────────────────────┘          │
│                  MORE USERS (revenue funds growth)           │
│                                                              │
│   Sub-flywheels:                                             │
│                                                              │
│   ALAMA SCORE FLYWHEEL:                                      │
│   More transactions → Better credit model → More banks       │
│   adopt → More workers get credit → More transactions        │
│                                                              │
│   SOKO PULSE FLYWHEEL:                                       │
│   More workers → Better demand data → FMCGs buy intel        │
│   → Revenue improves product → More workers attracted        │
│                                                              │
│   FEDERATED LEARNING FLYWHEEL:                               │
│   More devices → Better aggregate model → Better on-device   │
│   predictions → More worker trust → More data shared         │
└─────────────────────────────────────────────────────────────┘
```

---

## Part 4: On-Device + Backend Sync Architecture

### 4.1 What Syncs vs. What Stays Local

```
┌──────────────────────────────────────────────────────────────┐
│              SYNC ARCHITECTURE                                │
│                                                              │
│  DEVICE (Msaidizi)              BACKEND (Angavu)             │
│  ┌──────────────────┐          ┌──────────────────┐         │
│  │ STAYS LOCAL       │          │ STAYS CLOUD      │         │
│  │ • Raw voice data  │          │ • Worker PII     │         │
│  │ • Full transcripts│          │ • Raw transactions│        │
│  │ • Personal vocab  │          │ • Individual data │         │
│  │ • Biometric data  │          │ • Buyer queries   │         │
│  │ • PIN/password    │          │ • Model weights   │         │
│  │ • Detailed logs   │          │ • Revenue data    │         │
│  └──────────────────┘          └──────────────────┘         │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  WHAT SYNCS (Privacy-Preserving)                      │   │
│  │                                                       │   │
│  │  UP (Device → Backend):                               │   │
│  │  ├── Transaction summaries (anonymized, ε=0.1)       │   │
│  │  ├── Aggregated metrics (daily totals, not items)    │   │
│  │  ├── Model gradients (encrypted, federated learning) │   │
│  │  ├── Vocabulary updates (new product names, dialect) │   │
│  │  ├── Error signals (what the model got wrong)        │   │
│  │  └── Business type + region (for cohort formation)   │   │
│  │                                                       │   │
│  │  DOWN (Backend → Device):                             │   │
│  │  ├── Updated model weights (federated aggregation)   │   │
│  │  ├── Market intelligence (aggregate, anonymized)     │   │
│  │  ├── Vocabulary updates (new Sheng/dialect terms)    │   │
│  │  ├── Credit readiness signal (qualitative only)      │   │
│  │  ├── Restock alerts (based on aggregate demand)      │   │
│  │  ├── Pricing suggestions (market-rate, not personal) │   │
│  │  └── App updates + new financial knowledge           │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Privacy-Preserving Intelligence Sharing

```
┌──────────────────────────────────────────────────────────────┐
│         PRIVACY-PRESERVING INTELLIGENCE PIPELINE              │
│                                                              │
│  Step 1: ON-DEVICE ANONYMIZATION                             │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Raw Transaction                                       │  │
│  │  → Strip: name, phone, GPS, exact time                 │  │
│  │  → Keep: business_type, region, product_category,      │  │
│  │          amount_bucket, payment_method                  │  │
│  │  → Add: Laplacian noise (ε=0.1)                       │  │
│  │  → Output: Anonymous transaction record                 │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Step 2: SECURE TRANSPORT                                    │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  TLS 1.3 + Post-Quantum Hybrid Key Exchange            │  │
│  │  (ML-KEM-768 + X25519)                                │  │
│  │  Certificate pinning                                   │  │
│  │  Batch encryption (AES-256-GCM per batch)             │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Step 3: BACKEND AGGREGATION                                 │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  k-Anonymity check: is this cohort ≥ 10 workers?      │  │
│  │  → YES: proceed to aggregation                         │  │
│  │  → NO: hold until cohort threshold met                 │  │
│  │                                                        │  │
│  │  Aggregate into: market signals, demand patterns,      │  │
│  │  pricing data, economic indicators                     │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Step 4: INTELLIGENCE GENERATION                             │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  OODA loop processes aggregated data                   │  │
│  │  → Generates: Soko Pulse, Alama Score components,      │  │
│  │    distribution intelligence, economic indicators       │  │
│  │                                                        │  │
│  │  No individual worker is ever identifiable.            │  │
│  │  Intelligence is about MARKETS, not PEOPLE.            │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Step 5: FEDERATED MODEL UPDATE                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Secure aggregation of encrypted gradients             │  │
│  │  → Global model update                                 │  │
│  │  → Pushed back to devices                              │  │
│  │  → Each device applies update locally                  │  │
│  │  → No device's individual data is reconstructable      │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 4.3 Two Superagents Working Together

```
┌──────────────────────────────────────────────────────────────┐
│              DUAL SUPERAGENT ARCHITECTURE                     │
│                                                              │
│  ┌─────────────────────────┐  ┌─────────────────────────┐  │
│  │   MSAIDIZI SUPERAGENT   │  │   ANGAVU SUPERAGENT     │  │
│  │   (On-Device)           │  │   (Backend)             │  │
│  │                         │  │                         │  │
│  │   Domain: INDIVIDUAL    │  │   Domain: COLLECTIVE    │  │
│  │   WORKER BUSINESS       │  │   ECONOMIC INTELLIGENCE │  │
│  │                         │  │                         │  │
│  │   "Help THIS worker     │  │   "Understand ALL       │  │
│  │    run their business   │  │    workers' economy     │  │
│  │    better today"        │  │    and monetize it"     │  │
│  │                         │  │                         │  │
│  │   Model: Qwen 0.8B     │  │   Model: DeepSeek       │  │
│  │   Memory: Personal      │  │   Memory: Aggregate     │  │
│  │   Tools: Transaction    │  │   Tools: Analytics      │  │
│  │   Flywheel: Personal    │  │   Flywheel: Market      │  │
│  │   improvement           │  │   intelligence          │  │
│  └────────────┬────────────┘  └────────────┬────────────┘  │
│               │                             │               │
│               │    ┌───────────────┐        │               │
│               └───→│   SYNC LAYER  │←───────┘               │
│                    │               │                         │
│                    │  • Anonymized  │                         │
│                    │    aggregates  │                         │
│                    │  • Model       │                         │
│                    │    gradients   │                         │
│                    │  • Market      │                         │
│                    │    intelligence│                         │
│                    │  • Vocabulary  │                         │
│                    │    updates     │                         │
│                    │  • Credit      │                         │
│                    │    signals     │                         │
│                    └───────────────┘                         │
│                                                              │
│  INTERACTION MODEL:                                          │
│  • Device superagent handles real-time, personal interactions│
│  • Backend superagent handles analysis, intelligence, revenue│
│  • They are INDEPENDENTLY INTELLIGENT                        │
│  • They SHARE KNOWLEDGE but not DATA                         │
│  • Either can function if the other is unavailable           │
│  • Together they are greater than the sum of parts           │
└──────────────────────────────────────────────────────────────┘
```

---

## Part 5: Implementation Roadmap

### Phase 1: Harness Unification (Weeks 1-4)
- [ ] Replace 5-agent router with unified capability activation system
- [ ] Implement 5-layer memory hierarchy on-device
- [ ] Build context assembly algorithm with compression
- [ ] Port TaskFlow pattern from OpenClaw for durable workflows
- [ ] Implement guardrails engine (financial integrity checks)

### Phase 2: Hermes-Style Model Training (Weeks 3-8)
- [ ] Create function-calling training dataset for Msaidizi domain
- [ ] Fine-tune Qwen 0.8B with Hermes-style structured outputs
- [ ] Validate: transaction recording, inventory check, cash flow query
- [ ] Benchmark: accuracy vs. current free-form approach
- [ ] Deploy via model update mechanism

### Phase 3: Backend Superagent (Weeks 5-10)
- [ ] Unify 6 backend agents into single OODA loop with capability modules
- [ ] Implement continuous OODA cycling (not just per-request)
- [ ] Build TaskFlow for long-horizon intelligence generation
- [ ] Implement collective intelligence emergence from aggregated data
- [ ] Connect federated learning to OODA loop feedback

### Phase 4: Sync & Flywheel (Weeks 8-14)
- [ ] Implement privacy-preserving sync pipeline (anonymization → transport → aggregation)
- [ ] Build federated learning aggregation with secure computation
- [ ] Implement on-device flywheel (vocabulary, patterns, predictions)
- [ ] Implement backend flywheel (market intelligence, credit scoring)
- [ ] End-to-end testing: device → sync → backend → intelligence → device

### Phase 5: Adaptive Learning Integration (Weeks 12-18)
- [ ] Connect adaptive learning engine to memory system
- [ ] Implement pattern recognition across L3-L4 memory layers
- [ ] Build user behavior model from conversation patterns
- [ ] Implement feedback loops (worker actions → model improvement)
- [ ] A/B testing: superagent vs. multi-agent performance

---

## Part 6: Key Design Principles

1. **One Job, Done Well** — Msaidizi superagent's job: "Help this informal worker understand and grow their business." Angavu superagent's job: "Transform anonymized worker data into economic intelligence." Not general-purpose. Not chatbots.

2. **Flywheel First** — Every feature must feed the flywheel. If a feature doesn't generate data that improves the system, it's not a superagent feature — it's just a feature.

3. **Privacy as Architecture** — Privacy isn't a bolt-on. The sync layer is designed so that individual data NEVER leaves the device in identifiable form. The backend operates on aggregates, not individuals.

4. **Offline-First Intelligence** — The device superagent must be fully functional without network. Backend intelligence is a bonus, not a requirement. This means the on-device model, memory, and flywheel must work independently.

5. **Guardrails Are Non-Negotiable** — Financial data has zero tolerance for hallucination. Every number the superagent outputs must be tool-verified, not generated. "I don't know" is always better than a wrong number.

6. **Memory Is Identity** — The superagent's memory IS its intelligence. Lose the memory, lose the agent. Memory must be encrypted, backed up, and portable across devices.

7. **Progressive Enhancement** — Start with the 0.8B model on a 2GB phone. As the device gets better (more RAM, faster CPU), activate more capabilities. The architecture scales vertically (better device → better agent) and horizontally (more workers → better collective intelligence).

---

## Appendix A: DeerFlow-Adapted Configuration for Msaidizi

```yaml
# msaidizi-superagent-config.yaml (inspired by DeerFlow's config.yaml)

superagent:
  name: "Msaidizi"
  domain: "informal-worker-business-assistant"
  language: "sw"  # Primary, with 14+ dialect support

model:
  primary:
    name: qwen-0.8b-hermes
    source: on-device
    quantization: Q4_K_M
    max_tokens: 2048
    function_calling: true  # Hermes-style
  fallback:
    name: qwen-7b-cloud
    source: backend
    when: online && complex_task

memory:
  layers:
    - name: working
      type: ram
      max_size: 2KB
      ttl: session
    - name: conversation
      type: sqlite
      max_turns: 20
      compression: extract_key_facts
    - name: daily
      type: sqlite
      ttl: 90d
      content: business_summary
    - name: patterns
      type: sqlite
      ttl: permanent
      content: learned_behaviors
    - name: knowledge
      type: json
      source: assets/
      ttl: permanent

guardrails:
  financial:
    immutable_transactions: true
    voice_confidence_threshold: 0.7
    anomaly_sigma_threshold: 3.0
    max_hourly_transactions: 100
  privacy:
    never_upload: [voice_raw, transcripts, biometric, pin]
    anonymize_before_sync: true
    differential_privacy_epsilon: 0.1
    k_anonymity_min: 10

flywheel:
  loops:
    - name: vocabulary
      input: worker_speech
      learning: new_product_names
      output: better_stt_recognition
    - name: dialect
      input: code_switching_patterns
      learning: language_mix_model
      output: accurate_mixed_speech_transcription
    - name: business_pattern
      input: transaction_history
      learning: restock_cycles_peak_hours
      output: accurate_proactive_alerts
    - name: advice_quality
      input: worker_follows_or_ignores
      learning: advice_relevance_score
      output: prioritized_useful_advice
    - name: cash_flow
      input: actual_vs_predicted
      learning: prediction_calibration
      output: accurate_forecasts

sync:
  direction: bidirectional
  frequency: on_wifi + battery > 20%
  up:
    - anonymized_transaction_summaries
    - encrypted_model_gradients
    - vocabulary_updates
    - error_signals
  down:
    - updated_model_weights
    - aggregate_market_intelligence
    - dialect_vocabulary_updates
    - credit_readiness_signal
    - restock_alerts
    - pricing_suggestions
```

---

## Appendix B: Comparison — Multi-Agent vs. Superagent

| Dimension | Multi-Agent (Current) | Superagent (Target) |
|-----------|----------------------|---------------------|
| **Brain** | 6 independent agents, each with own context | 1 unified brain with 6 capability modules |
| **Orchestration** | EventBus routes messages between agents | OODA loop continuously integrates all capabilities |
| **Memory** | Per-agent memory, siloed | Shared 5-layer memory hierarchy |
| **Learning** | Each agent learns independently | Unified flywheel — learning in one area benefits all |
| **Context** | Agent only sees what's routed to it | Full business context available to every capability |
| **Improvement** | Manual tuning per agent | Automatic improvement through flywheel |
| **Failure mode** | Agent failure blocks that capability | Graceful degradation — other capabilities compensate |
| **Latency** | Message passing between agents adds latency | Single inference pass activates needed capabilities |
| **Cost** | Multiple model invocations per query | Single model invocation, capability selection via function calling |

---

## Appendix C: Jensen Huang's Superagent Criteria — How We Meet Each One

| Criteria | Msaidizi On-Device | Angavu Backend |
|----------|-------------------|----------------|
| **Domain-specific** | ✅ Informal worker business assistant | ✅ Economic intelligence from informal markets |
| **Proprietary** | ✅ Custom-trained on African business data | ✅ Unique dataset (600M+ workers) |
| **Built for ONE job** | ✅ "Help this worker run their business" | ✅ "Transform worker data into economic intelligence" |
| **Flywheel** | ✅ Use → learn vocabulary/patterns → better recognition → more use | ✅ More workers → better data → better intelligence → more buyers → more revenue → more workers |
| **Harness** | ✅ Intent router + context assembly + capability activation | ✅ OODA loop + TaskFlow + EventBus |
| **Model** | ✅ Qwen 0.8B (Hermes-style) on-device | ✅ DeepSeek Reasoner + Chat + XGBoost |
| **Context** | ✅ 5-layer memory hierarchy | ✅ Market patterns + worker profiles + knowledge graph |
| **Tools** | ✅ Transaction, inventory, CFO, voice, scanner, WhatsApp | ✅ Analytics, scoring, research, reporting, federated learning |
| **Memory** | ✅ Working → conversation → daily → patterns → knowledge | ✅ Request → session → daily → market patterns → knowledge graph |
| **Guardrails** | ✅ Financial integrity, privacy, encryption, anomaly detection | ✅ k-Anonymity, differential privacy, audit, human-in-the-loop |

---

*This architecture transforms Msaidizi and Angavu from "apps that use AI" into "AI systems that happen to run as apps" — the fundamental distinction of a superagent.*
