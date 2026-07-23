# Msaidizi Super Agent Architecture — Design Document

**Date:** 2026-07-24
**Author:** Lead Super Agent Architect
**Scope:** Design a "super agent" for Msaidizi that goes beyond multi-agent systems
**Context:** Jensen Huang's super agent vision + current AI landscape + Msaidizi's existing architecture

---

## EXECUTIVE SUMMARY

**The question:** What does a "super agent" look like for Msaidizi — a capability BEYOND multi-agentic systems?

**The answer:** A super agent is NOT "more agents." It is a **self-evolving, domain-embedded, progressively autonomous system** that learns from every interaction, gets smarter with use, and iterates until the job is done. It is grounded in knowledge + tools + memory + safeguards as a unified system, not separate layers.

**Key insight:** Msaidizi already has many building blocks (intent routing, dialect adapters, LoRA fine-tuning, behavioral memory, progressive autonomy levels). The gap is in **connecting them into a flywheel** and **shifting from static agent orchestration to self-evolving intelligence.**

**The transformation:** From "app with AI features" → "AI that lives in an app" → "super agent that understands the informal economy better than any human."

---

## PART 1: RESEARCH — SUPER AGENT ARCHITECTURES (July 2026)

### 1.1 What Is a Super Agent?

A super agent is a system that exhibits **all** of the following properties simultaneously:

| Property | Multi-Agent System | Super Agent |
|----------|-------------------|-------------|
| **Learning** | Static prompts, manual updates | Flywheel: use → smarter → more use |
| **Knowledge** | Retrieved (RAG) at query time | Embedded in the agent's weights + memory |
| **Architecture** | Separate tools, memory, safeguards | Unified grounding: info + knowledge + tools + memory + safeguards |
| **Trust** | User controls each action | Progressive autonomy based on accumulated trust |
| **Persistence** | Stateless or session-bound | Contextual memory across weeks, months, years |
| **Modality** | Text or voice, separate | Multimodal: voice + vision + text integrated |
| **Iteration** | Single attempt, returns result | Iterates until job is done, retries, finds alternatives |
| **Transparency** | Black box | Open, controllable, explainable |

### 1.2 Industry State of the Art (July 2026)

#### NVIDIA's Vision (Jensen Huang, GTC 2025-2026)

Jensen Huang's framing of agentic AI:

> "Enterprise AI agents would create a multi-trillion-dollar industry... Employees will work alongside AI agents."

NVIDIA's implementation stack:
- **NVIDIA Agent Toolkit** (March 2026): Open-source framework for building self-evolving agents
- **NVIDIA OpenShell**: Secure runtime for autonomous agents with policy-based guardrails
- **NVIDIA NemoClaw**: Self-evolving agent framework that learns preferences and patterns, writing new memories and skills
- **NVIDIA Nemotron 3**: Open models optimized for agent workloads (MoE architecture for cost efficiency)

**Key architectural pattern from NVIDIA NemoClaw:**
```
User Interaction → Agent Observes → Writes New Memory → Updates Skills → 
Gets Better → More Interactions → Flywheel Accelerates
```

The NemoClaw pattern (June 2026): An agent that learns a recurring report format from a chat conversation — no code changes or gateway restarts required. The more users work with the agent, the better it gets.

#### LangChain's Agent Architecture Evolution

LangChain (Jan 2026) identified four multi-agent patterns:
1. **Subagents**: Centralized orchestration — supervisor calls specialized agents as tools
2. **Skills**: Modular capability registration — agents expose capabilities
3. **Handoffs**: Context transfer between agents — conversation routing
4. **Routers**: Dynamic dispatch — match queries to specialized agents

**Critical insight from LangChain:** "Many agentic tasks are best handled by a single agent with well-designed tools. You should start here."

**Anthropic's multi-agent research system** (2026): Lead agent (Claude Opus 4) + subagents (Claude Sonnet 4) outperformed single-agent by 90.2% on internal research evaluations. The architecture distributed work across agents with separate context windows.

#### Agent Protocol Stack (2025-2026)

Four protocols enable the "Agentic Internet":
- **MCP (Model Context Protocol)**: Agent ↔ Tools (Anthropic, donated Dec 2025)
- **A2A (Agent-to-Agent)**: Agent ↔ Agent peer communication (Google, April 2025)
- **ACP (Agent Communication Protocol)**: Open standard for agent-to-agent
- **ANP (Agent Network Protocol)**: Decentralized agent discovery, "HTTP of the agentic web"

**For Msaidizi:** MCP is most relevant (connecting the agent to M-Pesa, WhatsApp, financial tools). A2A becomes relevant when Msaidizi agents need to communicate with external agents (lenders, suppliers).

#### Arxiv: "From Prompt-Response to Goal-Directed Systems" (Feb 2026)

This paper establishes the reference architecture for production-grade agentic AI:
- **Cognitive kernel** (LLM) separated from **execution layer** (typed tool interfaces)
- **Closed-loop control**: perceive → plan → act → adapt
- **Persistent state** across interactions
- **Memory-augmented reasoning** (not just retrieval)
- **Convergence toward**: standardized agent loops, registries, auditable control

#### McKinsey: AI Flywheel (2024-2026)

McKinsey's framework for competitive moats in AI:
> "Better technology enables more applications. More applications generate more data. More data attracts more investment."

The data flywheel: **Use → Data → Better Model → More Use → More Data → Even Better Model**

For Msaidizi: The transaction data from informal workers IS the flywheel. Every recorded sale, every M-Pesa SMS parsed, every profit/loss calculation feeds the system that makes the next recommendation better.

### 1.3 Super Agent vs Multi-Agent: The Fundamental Difference

| Dimension | Multi-Agent (Current State) | Super Agent (Target State) |
|-----------|---------------------------|---------------------------|
| **Intelligence** | Distributed across specialized agents | Unified intelligence with specialized execution |
| **Learning** | Manual prompt engineering | Self-evolving through interaction |
| **Memory** | Session-bound or short-term | Long-term behavioral learning per user |
| **Autonomy** | Fixed permission levels | Progressive: builds trust → earns autonomy |
| **Failure** | Returns error or gives up | Iterates, retries, finds alternatives |
| **Knowledge** | Retrieved from vector DB | Embedded in model weights + structured memory |
| **Coordination** | Explicit agent-to-agent messaging | Emergent coordination from shared context |

---

## PART 2: GAP ANALYSIS — Msaidizi Current vs Super Agent

### 2.1 What Msaidizi Already Has (Strengths to Build On)

| Capability | Current State | Super Agent Relevance |
|-----------|--------------|----------------------|
| **Intent Routing** | 90% code-only, 29/31 intent types | ✅ Foundation for fast, reliable task execution |
| **Dialect Adapters** | 15+ African dialects (Swahili, Sheng, Hausa, etc.) | ✅ Critical for voice-first super agent |
| **Behavioral Memory (L3)** | Pattern learning from user behavior | ✅ Core of flywheel learning |
| **LoRA On-Device Fine-Tuning** | Real gradient descent, convergence detection | ✅ Enables personalized model adaptation |
| **Progressive Autonomy Levels** | 5 levels (Tool → Assistant → Colleague → Delegate → Autonomous) | ✅ Framework for trust-based autonomy |
| **Device-Tier Adaptation** | LOW/MEDIUM/HIGH with mutual exclusion | ✅ Enables super agent on $50 phones |
| **10-Layer Output Sanitization** | AGI safety boundaries | ✅ Safeguards for autonomous operation |
| **Federated Learning Client** | Differential privacy (ε=0.1), gradient aggregation | ✅ Privacy-preserving collective learning |
| **Voice Pipeline** | Sherpa-ONNX + Piper + Qwen 0.8B | ✅ Multimodal foundation |
| **M-Pesa Integration** | SMS parser + DarajaClient | ✅ Financial data ingestion |
| **OODA/ReAct/Reflexion Loops** | Implemented but untested | ⚠️ Foundation for iteration |
| **MoE Router** | Implemented but premature | ⚠️ Cost optimization for inference routing |

### 2.2 What's Missing for Super Agent

| Gap | Severity | Description |
|-----|----------|-------------|
| **Flywheel Learning Loop** | 🔴 Critical | No feedback loop from user behavior → model improvement → better behavior |
| **Backend Server** | 🔴 Critical | App has API client but no server. All cloud capabilities dead. |
| **Memory Integration** | 🔴 Critical | L1/L2/L3 memory layers disconnected — three separate systems |
| **Cross-Session Learning** | 🔴 Critical | No mechanism to learn across sessions and apply to future interactions |
| **Iterative Problem Solving** | 🟡 High | OODA/ReAct loops exist but don't actually retry or find alternatives |
| **Domain Knowledge Embedding** | 🟡 High | Financial knowledge is in prompts, not in model weights or structured KB |
| **Progressive Autonomy Triggers** | 🟡 High | Autonomy levels defined but no mechanism to advance based on trust |
| **Multimodal Integration** | 🟡 High | Voice, vision (receipt OCR), and text exist but aren't unified |
| **Agent-to-Agent Protocol** | 🟢 Medium | A2A protocol stub exists but no real agent communication |
| **Self-Diagnosis & Repair** | 🟢 Medium | No mechanism to detect when the agent is wrong and self-correct |
| **Explainability** | 🟢 Medium | No mechanism to explain WHY a recommendation was made |
| **User Feedback Loop** | 🟢 Medium | FeedbackCollector exists but doesn't feed back into learning |

### 2.3 Gap Severity Matrix

```
                    EXISTS IN CODE    MISSING
                    ───────────────   ─────────────────
HIGH IMPACT         Intent Routing    Flywheel Learning
                    Dialect Adapters  Memory Integration  
                    LoRA Fine-Tuning  Backend Server
                    Prog. Autonomy    Cross-Session Learning

MEDIUM IMPACT       OODA/ReAct        Iterative Problem Solving
                    Voice Pipeline    Domain Knowledge Embedding
                    M-Pesa Parser     Multimodal Integration
                    Safety Layers     Self-Diagnosis

LOWER IMPACT        MoE Router        A2A Protocol
                    FL Client         Explainability
                    Device Tiers      User Feedback Loop
```

---

## PART 3: DESIGN — The Msaidizi Super Agent

### 3.1 Core Architecture: The Unified Cognitive Loop

The super agent is NOT a collection of separate systems. It is a **unified cognitive loop** with six integrated components:

```
┌─────────────────────────────────────────────────────────────────┐
│                    MSAIDIZI SUPER AGENT                          │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ PERCEIVE │→│  REASON   │→│   ACT    │→│  LEARN   │       │
│  │          │  │          │  │          │  │          │       │
│  │ Voice    │  │ Domain   │  │ Execute  │  │ Update   │       │
│  │ Vision   │  │ Context  │  │ Iterate  │  │ Memory   │       │
│  │ Text     │  │ Planning │  │ Verify   │  │ Adapt    │       │
│  │ Financial│  │ Safety   │  │ Retry    │  │ Evolve   │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
│       │              │              │              │             │
│       └──────────────┴──────────────┴──────────────┘             │
│                          ↕                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              UNIFIED MEMORY SYSTEM                       │   │
│  │  L1: Working Memory (current session context)           │   │
│  │  L2: Episodic Memory (past interactions, episodes)      │   │
│  │  L3: Behavioral Memory (learned patterns per user)      │   │
│  │  L4: Semantic Memory (domain knowledge, facts)          │   │
│  │  L5: Collective Memory (federated, population-level)    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          ↕                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              FLYWHEEL ENGINE                              │   │
│  │  Interaction → Trace → Pattern → Adaptation → Better     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 The Six Pillars of the Super Agent

#### PILLAR 1: Flywheel Learning Engine

**What it is:** The core mechanism that makes the agent smarter with every interaction.

**How it works:**

```
Phase 1: OBSERVE
├── User says: "Nimepata 500 ya tomatoes" (I got 500 for tomatoes)
├── Agent records transaction
├── Agent observes: user always records tomatoes, always at end of day
└── Agent observes: user's profit margin on tomatoes is 40%

Phase 2: LEARN
├── Pattern extracted: "User is a tomato vendor, records in evening"
├── Behavioral model updated: preference_evening_recording = true
├── Domain knowledge updated: user's tomato margins are healthy
└── Confidence score incremented: tomato_domain_expertise += 0.1

Phase 3: APPLY
├── Next day at 6pm, agent proactively asks: "Habari ya mauzo ya tomatoes leo?"
│   (How were today's tomato sales?)
├── Agent pre-fills transaction template with tomato category
└── Agent adds insight: "Margin yako ni 40% — ni nzuri sana!"
    (Your margin is 40% — that's very good!)

Phase 4: VALIDATE
├── User confirms or corrects
├── If confirmed: confidence += 0.1, pattern strengthened
├── If corrected: pattern adjusted, new learning captured
└── Cycle repeats, agent gets smarter
```

**Technical Implementation:**

```kotlin
// FlywheelEngine.kt — Core learning loop
class FlywheelEngine @Inject constructor(
    private val behavioralMemory: BehavioralMemoryL3,
    private val episodicMemory: EpisodicMemoryL2,
    private val semanticMemory: SemanticMemoryL4,
    private val federatedClient: FederatedLearningClient
) {
    // After every interaction
    suspend fun processInteraction(interaction: UserInteraction) {
        // 1. Extract patterns
        val patterns = extractPatterns(interaction)
        
        // 2. Update behavioral memory
        behavioralMemory.updatePatterns(interaction.userId, patterns)
        
        // 3. Store episodic memory
        episodicMemory.storeEpisode(interaction.toEpisode())
        
        // 4. Update domain knowledge if significant
        if (patterns.significance > THRESHOLD) {
            semanticMemory.updateDomainKnowledge(patterns)
        }
        
        // 5. Prepare federated learning gradient
        federatedClient.prepareGradient(interaction, patterns)
        
        // 6. Check if LoRA fine-tuning threshold reached
        if (behavioralMemory.getUpdateCount() % LORA_THRESHOLD == 0) {
            triggerLoRAFineTuning(behavioralMemory.getRecentPatterns())
        }
    }
    
    // Extract behavioral patterns from interaction
    private fun extractPatterns(interaction: UserInteraction): List<Pattern> {
        return listOf(
            TemporalPattern(interaction.timestamp), // When does user interact?
            DomainPattern(interaction.domain),       // What domains?
            LanguagePattern(interaction.language),    // What language/dialect?
            ConfidencePattern(interaction.outcome),   // Was agent correct?
            PreferencePattern(interaction.behaviors)  // User preferences
        )
    }
}
```

**The Flywheel Metrics:**
- **Learning Rate:** How many interactions before the agent adapts? (Target: <5)
- **Prediction Accuracy:** How often does the agent correctly predict user needs? (Target: >70% after 30 days)
- **Proactive Value:** How often does the agent offer unsolicited but valuable insight? (Target: 1-2x/day)
- **Confidence Calibration:** Does the agent know when it's uncertain? (Target: >90% calibration)

#### PILLAR 2: Domain Knowledge Embedding

**What it is:** Specialized knowledge about the informal economy embedded INTO the agent, not just retrieved.

**Three layers of domain knowledge:**

```
Layer 1: STRUCTURED KNOWLEDGE (Database)
├── Product categories and subcategories
├── M-Pesa transaction patterns
├── Seasonal price data (tomatoes, onions, sukuma wiki)
├── Supplier networks and typical margins
├── Loan products and terms
├── Tax obligations for informal workers
└── Cultural practices (tithe, chama, harambee)

Layer 2: BEHAVIORAL KNOWLEDGE (Learned)
├── User's specific business patterns
├── User's financial habits
├── User's risk tolerance
├── User's language preferences
├── User's time-of-day patterns
└── User's social network (chama members, suppliers)

Layer 3: COLLECTIVE KNOWLEDGE (Federated)
├── Market-level price trends (anonymized)
├── Common financial mistakes (population-level)
├── Successful business strategies (anonymized)
├── Regional economic indicators
└── Seasonal demand patterns
```

**How domain knowledge is embedded, not retrieved:**

Current approach (RAG-like):
```
User: "Should I buy tomatoes or onions?"
→ Query vector DB for relevant documents
→ Retrieve: "Tomatoes have 40% margin, onions 30%"
→ Generate response from retrieved text
```

Super agent approach (embedded):
```
User: "Should I buy tomatoes or onions?"
→ Agent KNOWS (from behavioral memory): user is a tomato vendor
→ Agent KNOWS (from collective memory): tomato prices rising this week
→ Agent KNOWS (from domain knowledge): user's location, market, suppliers
→ Agent generates: "Tomatoes — bei yako ya kawaida ni 40% margin, na bei 
  ya wiki hii ni nzuri. Onions zina margin ndogo na bei yake ni volatile."
  (Tomatoes — your usual margin is 40%, and this week's prices are good. 
  Onions have lower margin and volatile prices.)
```

The difference: The super agent doesn't retrieve knowledge — it HAS knowledge. Like a human expert who has internalized years of experience.

**Implementation:**

```kotlin
// DomainKnowledgeEmbedder.kt
class DomainKnowledgeEmbedder @Inject constructor(
    private val loraEngine: LoRAEngine,
    private val semanticMemory: SemanticMemoryL4,
    private val behavioralMemory: BehavioralMemoryL3
) {
    // Periodically embed domain knowledge into the model
    suspend fun embedDomainKnowledge() {
        // 1. Collect recent domain interactions
        val domainData = semanticMemory.getRecentDomainKnowledge()
        
        // 2. Create training examples from domain knowledge
        val trainingExamples = domainData.map { knowledge ->
            TrainingExample(
                input = knowledge.question,
                output = knowledge.expertAnswer,
                weight = knowledge.importance
            )
        }
        
        // 3. Fine-tune on-device model with domain knowledge
        loraEngine.fineTune(
            examples = trainingExamples,
            learningRate = 0.0001,
            epochs = 3
        )
        
        // 4. Verify model quality didn't degrade
        val quality = loraEngine.evaluateModel()
        if (quality < QUALITY_THRESHOLD) {
            loraEngine.rollback()
        }
    }
}
```

#### PILLAR 3: Integrated Memory System

**What it is:** Five memory layers that work as ONE system, not five separate databases.

**The problem today:** L1 (working), L2 (episodic), L3 (behavioral) are disconnected. This is like a human who can remember the current conversation but can't recall past experiences or learned patterns.

**The super agent memory:**

```
┌─────────────────────────────────────────────────────────────┐
│                    MEMORY HIERARCHY                          │
│                                                             │
│  L5: COLLECTIVE (Federated, population-level)               │
│  │  "Mama mboga in Migori typically earns 40% margin"       │
│  │  Source: Anonymized aggregation of 10,000+ users         │
│  │  Update: Weekly via federated learning                   │
│  │                                                          │
│  ├─ L4: SEMANTIC (Domain knowledge, facts)                  │
│  │  │  "Tomatoes are seasonal — prices peak Dec-Mar"        │
│  │  │  Source: Market data, research, learned patterns      │
│  │  │  Update: Monthly + on significant events              │
│  │  │                                                       │
│  │  ├─ L3: BEHAVIORAL (Learned patterns per user)           │
│  │  │  │  "This user records sales at 6pm, always tomatoes" │
│  │  │  │  Source: Interaction history, pattern extraction    │
│  │  │  │  Update: After every interaction                    │
│  │  │  │                                                     │
│  │  │  ├─ L2: EPISODIC (Past interactions)                  │
│  │  │  │  │  "On July 15, user recorded KES 500 tomato sale"│
│  │  │  │  │  Source: Raw interaction logs                    │
│  │  │  │  │  Update: Every interaction                       │
│  │  │  │  │                                                   │
│  │  │  │  └─ L1: WORKING (Current session)                  │
│  │  │  │     "User just said 'nimepata 500'"                │
│  │  │  │     Source: Current conversation                    │
│  │  │  │     Update: Real-time                               │
└─────────────────────────────────────────────────────────────┘
```

**How memories connect:**

```kotlin
// UnifiedMemorySystem.kt
class UnifiedMemorySystem @Inject constructor(
    private val l1: WorkingMemory,
    private val l2: EpisodicMemory,
    private val l3: BehavioralMemory,
    private val l4: SemanticMemory,
    private val l5: CollectiveMemory
) {
    // When processing a new interaction
    suspend fun processInteraction(interaction: Interaction) {
        // L1: Update working memory (current context)
        l1.update(interaction)
        
        // L2: Store episode
        val episode = l2.store(interaction)
        
        // L3: Check if episode matches known patterns
        val patterns = l3.matchPatterns(episode)
        if (patterns.isNotEmpty()) {
            // Pattern matched — strengthen it
            l3.reinforcePatterns(patterns)
            // Feed pattern into L1 for immediate use
            l1.injectContext(patterns.toContext())
        } else {
            // New pattern — learn it
            val newPattern = l3.learnPattern(episode)
            if (newPattern.confidence > THRESHOLD) {
                // Significant new pattern — update domain knowledge
                l4.updateFromPattern(newPattern)
            }
        }
        
        // L5: Contribute to federated learning (privacy-preserving)
        l5.prepareContribution(interaction, patterns)
    }
    
    // When generating a response, query ALL memory layers
    suspend fun getContext(query: Query): RichContext {
        return RichContext(
            working = l1.getCurrentContext(),
            relevant = l2.findRelevantEpisodes(query),
            behavioral = l3.getBehavioralHints(query),
            domain = l4.getDomainKnowledge(query),
            collective = l5.getCollectiveInsights(query)
        )
    }
}
```

#### PILLAR 4: Iterative Problem Solving

**What it is:** The agent doesn't give up. It iterates, retries, finds alternative approaches.

**Current state:** The OODA/ReAct/Reflexion loops exist in code but are untested and disconnected.

**Super agent approach:**

```
User: "Nataka kujua kama nimepata faida wiki hii"
(I want to know if I made a profit this week)

ATTEMPT 1: Query transaction database
├── Result: 5 transactions found, 2 incomplete
├── Analysis: Can't calculate profit with incomplete data
└── DON'T GIVE UP → Try alternative

ATTEMPT 2: Check M-Pesa SMS records
├── Result: Found 3 additional transactions in SMS
├── Analysis: Still missing 1 transaction
└── DON'T GIVE UP → Try another approach

ATTEMPT 3: Ask user for missing data
├── "Nimeona transactions 7 kati ya 8. Moja inakosa — 
│   je, ulikuwa na transaction nyingine ya KES 200?"
│   (I saw 7 of 8 transactions. One is missing — 
│   did you have another transaction of KES 200?)
├── User: "Ndiyo, nilinunua mafuta" (Yes, I bought cooking oil)
└── NOW CALCULATE: Complete data → Profit = KES 1,200

RESPONSE: "Wiki hii ulipata faida ya KES 1,200! 
Margin yako ni 32% — ni nzuri kuliko wiki iliyopita (28%)."
(This week you made KES 1,200 profit! 
Your margin is 32% — better than last week (28%).)
```

**Implementation:**

```kotlin
// IterativeSolver.kt
class IterativeSolver @Inject constructor(
    private val strategies: List<SolvingStrategy>,
    private val maxAttempts: Int = 5
) {
    suspend fun solve(query: Query): Solution {
        val context = SolveContext(query)
        
        for (attempt in 1..maxAttempts) {
            // Select strategy based on previous failures
            val strategy = selectStrategy(context, attempt)
            
            // Execute strategy
            val result = strategy.execute(context)
            
            when (result.status) {
                Status.SUCCESS -> return result.toSolution()
                Status.PARTIAL -> {
                    context.addPartialResult(result)
                    context.recordFailure(strategy, result.reason)
                    // Continue with next strategy
                }
                Status.FAILED -> {
                    context.recordFailure(strategy, result.reason)
                    // Continue with next strategy
                }
            }
        }
        
        // All strategies exhausted — ask user for help
        return Solution.needUserInput(context.getGaps())
    }
    
    private fun selectStrategy(context: SolveContext, attempt: Int): SolvingStrategy {
        return when (attempt) {
            1 -> DatabaseQueryStrategy()      // Try direct data first
            2 -> SmsParsingStrategy()          // Try M-Pesa SMS
            3 -> HistoricalInferenceStrategy() // Infer from patterns
            4 -> UserPromptStrategy()          // Ask user
            5 -> ApproximationStrategy()       // Best estimate with caveats
            else -> DefaultStrategy()
        }
    }
}
```

#### PILLAR 5: Progressive Autonomy

**What it is:** As trust builds, the agent gets more autonomy. Like a new employee who earns more responsibility over time.

**Current state:** Five autonomy levels are defined (Tool → Assistant → Colleague → Delegate → Autonomous) but there's no mechanism to advance.

**Super agent autonomy progression:**

```
LEVEL 1: TOOL (Day 1-7)
├── Agent only does what explicitly asked
├── "Record this transaction" → Records
├── No proactive behavior
├── No autonomous decisions
└── Trust score: 0-20

LEVEL 2: ASSISTANT (Week 2-4)
├── Agent suggests but doesn't act
├── "I notice you usually record at 6pm — want me to remind you?"
├── Offers insights when asked
├── Asks clarifying questions
└── Trust score: 21-40

LEVEL 3: COLLEAGUE (Month 2-3)
├── Agent proactively offers insights
├── "Your tomato margin dropped 10% this week — supplier changed?"
├── Suggests actions (not just information)
├── Handles routine tasks with confirmation
└── Trust score: 41-60

LEVEL 4: DELEGATE (Month 4-6)
├── Agent handles routine tasks autonomously
├── Auto-categorizes transactions based on learned patterns
├── Sends daily summary without being asked
├── Flags anomalies proactively
├── Only asks for complex decisions
└── Trust score: 61-80

LEVEL 5: AUTONOMOUS (Month 7+)
├── Agent manages routine financial tracking end-to-end
├── Negotiates with suppliers (within parameters)
├── Manages loan applications
├── Provides strategic business advice
├── Human only for major decisions
└── Trust score: 81-100
```

**Trust Score Calculation:**

```kotlin
// TrustScoreEngine.kt
class TrustScoreEngine @Inject constructor(
    private val behavioralMemory: BehavioralMemory
) {
    fun calculateTrustScore(userId: String): TrustScore {
        val metrics = behavioralMemory.getUserMetrics(userId)
        
        return TrustScore(
            // Accuracy: How often was the agent correct?
            accuracy = metrics.correctActions / metrics.totalActions,
            
            // Consistency: How reliable is the agent over time?
            consistency = metrics.streakDays / metrics.totalDays,
            
            // User satisfaction: Did user accept or reject suggestions?
            satisfaction = metrics.acceptedSuggestions / metrics.totalSuggestions,
            
            // Error recovery: How well did agent handle mistakes?
            errorRecovery = metrics.successfulRecoveries / metrics.totalErrors,
            
            // Time: How long has the agent been serving this user?
            tenure = metrics.daysSinceFirstInteraction,
            
            // Composite score
            composite = weightedAverage(
                accuracy * 0.3,
                consistency * 0.2,
                satisfaction * 0.3,
                errorRecovery * 0.1,
                tenure * 0.1
            )
        )
    }
    
    fun getAutonomyLevel(score: TrustScore): AutonomyLevel {
        return when {
            score.composite >= 0.81 -> AutonomyLevel.AUTONOMOUS
            score.composite >= 0.61 -> AutonomyLevel.DELEGATE
            score.composite >= 0.41 -> AutonomyLevel.COLLEAGUE
            score.composite >= 0.21 -> AutonomyLevel.ASSISTANT
            else -> AutonomyLevel.TOOL
        }
    }
}
```

#### PILLAR 6: Unified Multimodal Processing

**What it is:** Voice, vision (receipt OCR), and text are not separate pipelines — they're unified input channels into the same cognitive loop.

**Current state:** Voice pipeline (Sherpa-ONNX), receipt OCR (ML Kit), and text input exist as separate systems.

**Super agent multimodal:**

```
INPUT CHANNELS          COGNITIVE LOOP           OUTPUT CHANNELS
─────────────          ──────────────           ───────────────
Voice (ASR)  ─┐                                ┌─ Voice (TTS)
               │    ┌──────────────────┐       │
Receipt OCR  ─┼──→│  UNIFIED PERCEIVE  │──→──┼─ Text Display
               │    │  + CONTEXT MERGE  │       │
Text Input   ─┘    └──────────────────┘       └─ Proactive Alert
                        │
                        ↓
                  ┌──────────────┐
                  │   REASON     │
                  │   + ACT      │
                  │   + LEARN    │
                  └──────────────┘
```

**Example multimodal interaction:**

```
[User takes photo of M-Pesa receipt]
[User says:] "Hii ni receipt ya supplier wangu"
(This is my supplier's receipt)

SUPER AGENT PROCESSING:
1. PERCEIVE (multimodal):
   - Vision: OCR extracts "KES 2,500 - Payment to Kamau Supplies"
   - Voice: "supplier wangu" → category = supplier payment
   - Context: User's behavioral memory shows Kamau Supplies = tomato supplier
   
2. REASON:
   - Domain knowledge: User buys tomatoes from Kamau
   - Pattern: Last 3 payments to Kamau were KES 2,000-2,500
   - Insight: This payment is at the high end → maybe prices increased?
   
3. ACT:
   - Record transaction: KES 2,500, category = "supplier_payment", item = "tomatoes"
   - Link to M-Pesa transaction if found
   
4. LEARN:
   - Update: Kamau Supplies price trend → rising
   - Update: User's average tomato purchase = KES 2,300 (updated from 2,100)
   
5. RESPOND:
   - "Nimerekodi KES 2,500 kwa Kamau Supplies. Bei ya tomatoes imepanda — 
     wiki iliyopita ulilipa KES 2,000. Je, ulipata kilo ngapi?"
     (I've recorded KES 2,500 for Kamau Supplies. Tomato prices went up — 
     last week you paid KES 2,000. How many kilos did you get?)
```

### 3.3 The Super Agent Loop: Complete Flow

```
┌─────────────────────────────────────────────────────────────┐
│                 SUPER AGENT COGNITIVE LOOP                   │
│                                                             │
│  1. PERCEIVE (Unified Multimodal Input)                     │
│     ├── Voice → ASR → Text                                  │
│     ├── Image → OCR → Structured Data                       │
│     ├── Text → Parse → Intent                              │
│     ├── M-Pesa SMS → Extract → Transaction                  │
│     └── Context → Memory Lookup → Enriched Input            │
│                                                             │
│  2. REASON (Domain-Embedded Intelligence)                   │
│     ├── Intent Classification (code-first, 90%)             │
│     ├── Context Assembly (all 5 memory layers)              │
│     ├── Domain Knowledge Application                        │
│     ├── Safety Check (10-layer sanitization)                │
│     └── Plan Generation (what to do, how to do it)          │
│                                                             │
│  3. ACT (Iterative Execution)                               │
│     ├── Execute primary action                              │
│     ├── Verify result                                       │
│     ├── If incomplete → try alternative approach            │
│     ├── If uncertain → ask user for clarification           │
│     └── If failed → iterate (up to N attempts)              │
│                                                             │
│  4. LEARN (Flywheel Engine)                                 │
│     ├── Extract patterns from interaction                   │
│     ├── Update behavioral memory (L3)                       │
│     ├── Store episodic memory (L2)                          │
│     ├── Update domain knowledge if significant (L4)         │
│     ├── Prepare federated learning gradient (L5)            │
│     ├── Update trust score                                  │
│     └── Trigger LoRA fine-tuning if threshold reached       │
│                                                             │
│  5. RESPOND (Multimodal Output)                             │
│     ├── Voice (TTS) for voice interactions                  │
│     ├── Text for detailed information                       │
│     ├── Proactive alerts for anomalies                      │
│     └── Insights and recommendations                        │
│                                                             │
│  → LOOP BACK TO 1 (next interaction)                        │
└─────────────────────────────────────────────────────────────┘
```

---

## PART 4: IMPLEMENTATION ROADMAP

### Phase 1: Foundation (Months 1-3) — "Make It Work"

**Goal:** Fix critical bugs, build backend, wire memory together.

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| P0 | Fix voice pipeline (model downloads, TTS, STT) | 2 weeks | BLOCKING |
| P0 | Fix navigation (5 unreachable screens) | 1 week | BLOCKING |
| P0 | Build backend (auth + sync + M-Pesa) | 4 weeks | BLOCKING |
| P1 | Wire L1↔L2↔L3 memory layers | 2 weeks | HIGH |
| P1 | Fix Retrofit TLS security gap | 3 days | HIGH |
| P1 | Add analytics (PostHog) | 1 week | HIGH |
| P2 | Consolidate HTTP clients (Ktor only) | 1 week | MEDIUM |

**Deliverable:** A working app with voice, navigation, backend sync, and integrated memory.

### Phase 2: Learning Loop (Months 4-6) — "Make It Smart"

**Goal:** Implement the flywheel learning engine.

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| P0 | Implement FlywheelEngine | 3 weeks | CRITICAL |
| P0 | Connect behavioral memory to response generation | 2 weeks | CRITICAL |
| P1 | Implement trust score calculation | 1 week | HIGH |
| P1 | Wire progressive autonomy triggers | 2 weeks | HIGH |
| P1 | Implement iterative problem solver | 2 weeks | HIGH |
| P2 | Add L4 semantic memory (domain knowledge DB) | 2 weeks | MEDIUM |
| P2 | Implement user feedback loop | 1 week | MEDIUM |

**Deliverable:** An agent that learns from interactions, adapts to user behavior, and gets smarter over time.

### Phase 3: Intelligence (Months 7-9) — "Make It Expert"

**Goal:** Embed domain knowledge and enable cloud escalation.

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| P0 | Implement hybrid inference (on-device + cloud) | 3 weeks | CRITICAL |
| P0 | Build domain knowledge base (informal economy) | 4 weeks | CRITICAL |
| P1 | Implement LoRA fine-tuning from behavioral data | 3 weeks | HIGH |
| P1 | Add multimodal integration (voice + vision + text) | 2 weeks | HIGH |
| P1 | Build M-Pesa SMS deep parser (STK Push, etc.) | 2 weeks | HIGH |
| P2 | Implement explainability ("why this recommendation") | 2 weeks | MEDIUM |
| P2 | Add proactive insights engine | 2 weeks | MEDIUM |

**Deliverable:** An expert agent that understands the informal economy and provides actionable insights.

### Phase 4: Ecosystem (Months 10-12) — "Make It Connected"

**Goal:** Connect to the broader ecosystem and enable collective intelligence.

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| P0 | Implement federated learning aggregation (server-side) | 4 weeks | CRITICAL |
| P0 | Build WhatsApp Business API integration | 3 weeks | CRITICAL |
| P1 | Implement A2A protocol for external agent communication | 3 weeks | HIGH |
| P1 | Build multi-channel delivery (WhatsApp + SMS + Telegram) | 3 weeks | HIGH |
| P1 | Implement L5 collective memory from federated learning | 2 weeks | HIGH |
| P2 | Build B2B intelligence products (Soko Pulse, Alama Score) | 4 weeks | MEDIUM |
| P2 | Add multi-country support (Tanzania, Uganda, Nigeria) | 4 weeks | MEDIUM |

**Deliverable:** A connected super agent that benefits from collective intelligence and serves multiple channels.

### Phase 5: Evolution (Month 13+) — "Make It Autonomous"

**Goal:** Full super agent capabilities — self-evolving, self-healing, progressively autonomous.

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| P0 | Implement self-diagnosis and self-repair | 3 weeks | CRITICAL |
| P0 | Enable autonomous routine operations (Level 4-5) | 4 weeks | CRITICAL |
| P1 | Implement model distillation (custom 400MB model) | 4 weeks | HIGH |
| P1 | Build agent marketplace (third-party agent integration) | 6 weeks | HIGH |
| P2 | Implement cross-agent learning (agents learning from each other) | 4 weeks | MEDIUM |
| P2 | Build agent governance framework | 3 weeks | MEDIUM |

**Deliverable:** A self-evolving super agent that operates autonomously for routine tasks and learns continuously.

---

## PART 5: TECHNICAL REQUIREMENTS

### 5.1 Models Required

| Model | Purpose | Size | Where |
|-------|---------|------|-------|
| **Whisper Tiny/Base** | Speech-to-text | 10-40MB | On-device |
| **Piper TTS** | Text-to-speech (Swahili) | 63MB | On-device |
| **Qwen 3.5 0.8B** | On-device reasoning | 580MB | On-device |
| **SmolLM 3 360M** | Fallback for BASIC devices | 250MB | On-device |
| **Gemini Flash / DeepSeek V4** | Cloud escalation for complex queries | — | Cloud |
| **Nemotron 3 Super** | Agent orchestration (if using NVIDIA stack) | — | Cloud |
| **Custom LoRA adapters** | Per-user fine-tuned knowledge | 10-50MB | On-device |

### 5.2 Infrastructure Required

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Backend API** | Python + FastAPI | Auth, sync, inference proxy |
| **Database** | PostgreSQL | User data, transactions, sync state |
| **Cache** | Redis | Session cache, rate limiting |
| **Analytics** | ClickHouse (Phase 4+) | Usage patterns, aggregate queries |
| **Message Queue** | Redis Streams or Kafka | Event-driven processing |
| **Model Serving** | NVIDIA NIM or vLLM | Cloud inference for complex queries |
| **WhatsApp** | WhatsApp Business API | Multi-channel delivery |
| **SMS** | Africa's Talking API | SMS fallback |
| **M-Pesa** | Safaricom Daraja API | Transaction integration |
| **CDN** | Cloudflare R2 | Model distribution |
| **Monitoring** | Sentry + Grafana | Crash reporting, performance |

### 5.3 Data Requirements

| Data Type | Source | Volume | Purpose |
|-----------|--------|--------|---------|
| **Transaction data** | M-Pesa SMS, manual entry | Per-user, daily | Financial tracking, pattern learning |
| **Behavioral patterns** | User interactions | Per-user, continuous | Personalization, flywheel learning |
| **Market prices** | Web scraping, APIs | Regional, weekly | Domain knowledge, price alerts |
| **User feedback** | In-app feedback, corrections | Per-interaction | Model improvement, trust calibration |
| **Federated gradients** | Aggregated from users | Population-level, weekly | Collective intelligence, model improvement |

### 5.4 Security Requirements

| Requirement | Implementation | Status |
|------------|---------------|--------|
| **Data encryption at rest** | SQLCipher + AES-256-GCM | ✅ Exists |
| **Data encryption in transit** | TLS 1.3 + cert pinning | ⚠️ Retrofit gap |
| **Post-quantum crypto** | ML-KEM/ML-DSA (Bouncy Castle) | ✅ Exists |
| **Differential privacy** | ε=0.1 for federated learning | ✅ Exists |
| **Biometric auth** | Android BiometricPrompt | ✅ Exists |
| **Input sanitization** | 10-layer output sanitization | ✅ Exists |
| **Progressive autonomy safeguards** | Human-in-the-loop for Levels 1-3 | ⚠️ Needs implementation |
| **Audit trail** | Interaction logging with tamper detection | ⚠️ Needs implementation |

### 5.5 Agent Protocol Stack

| Protocol | Use Case | Priority |
|----------|----------|----------|
| **MCP (Model Context Protocol)** | Agent ↔ Tools (M-Pesa, WhatsApp, DB) | Phase 2 |
| **A2A (Agent-to-Agent)** | Agent ↔ External agents (lenders, suppliers) | Phase 4 |
| **ACP (Agent Communication Protocol)** | Agent ↔ Other Msaidizi agents | Phase 4 |
| **ANP (Agent Network Protocol)** | Agent discovery and registration | Phase 5 |

---

## PART 6: SUB-MEMBER IDENTIFICATION

### Sub-Members for Detailed Design

#### 1. Agent Architecture Analyst
**Mandate:** Design the detailed super agent architecture
**Focus areas:**
- Unified cognitive loop implementation
- Memory layer integration (L1-L5)
- Agent communication protocols (MCP, A2A)
- Safety and governance framework
- On-device vs cloud inference routing

#### 2. Learning Systems Analyst
**Mandate:** Design the flywheel learning loop
**Focus areas:**
- Pattern extraction from user interactions
- Behavioral memory update algorithms
- LoRA fine-tuning triggers and schedules
- Federated learning aggregation protocol
- Trust score calculation and autonomy progression
- Cold-start problem (how does the agent learn with no data?)

#### 3. Capability Gap Analyst
**Mandate:** Detailed current state vs super agent state analysis
**Focus areas:**
- Feature-by-feature gap analysis
- Code audit of existing but disconnected capabilities
- Identification of reusable vs replaceable components
- Risk assessment for each gap
- Dependencies between gaps (which must be fixed first)

#### 4. Implementation Strategist
**Mandate:** Create the detailed implementation roadmap
**Focus areas:**
- Phase-by-phase task breakdown with effort estimates
- Resource requirements (developers, infrastructure, data)
- Risk mitigation strategies
- Go/no-go criteria for each phase
- MVP definition: what's the minimum super agent?

---

## PART 7: KEY DESIGN DECISIONS

### Decision 1: Single Agent vs Multi-Agent

**Recommendation: Single agent with modular capabilities.**

LangChain's insight is correct: "Many agentic tasks are best handled by a single agent with well-designed tools."

Msaidizi should use a **single cognitive agent** with modular capabilities, not multiple specialized agents. Why:
- Mama mboga doesn't want to talk to 7 different agents
- A single agent with unified memory is simpler and more coherent
- Multi-agent coordination overhead isn't justified at Msaidizi's scale
- The existing 4 registered agents can become "skills" of the super agent

### Decision 2: On-Device vs Cloud

**Recommendation: Hybrid with intelligent routing.**

```
Simple queries (90%) → On-device (Qwen 0.8B) → $0, offline-capable
Complex queries (8%) → Cloud (Gemini Flash) → Near-free, better reasoning
Critical queries (2%) → Cloud (GPT-5/Claude 4) → Best quality, expensive
```

The 2026 AI price collapse makes cloud inference near-free for most queries. On-device is valuable for:
- Offline operation (critical for Africa)
- Data privacy (financial data stays on device)
- Latency (instant response for simple queries)

Cloud is valuable for:
- Complex reasoning (seasonal analysis, business strategy)
- Market intelligence (requires external data)
- Model updates (federated learning aggregation)

### Decision 3: Trust-Based Autonomy

**Recommendation: Implement trust scoring from Day 1, but start at Level 1 (Tool).**

The agent should track trust metrics from the very first interaction, but not advance autonomy levels until there's enough data (minimum 30 days, 100 interactions). This prevents premature autonomy.

### Decision 4: Federated Learning

**Recommendation: Build the client now, build the server at 10K+ users.**

The federated learning client in Msaidizi is sophisticated and ready. The server aggregation should wait until there are enough users to make the gradients meaningful. Building the server too early wastes effort on a system that can't be validated.

### Decision 5: Domain Knowledge Strategy

**Recommendation: Three-track approach.**

1. **Structured knowledge base** (immediate): Database of informal economy facts, product categories, market data
2. **Behavioral learning** (Month 4+): Learn from individual user patterns
3. **Collective intelligence** (Month 10+): Aggregate anonymized patterns from all users

---

## CONCLUSION

**The Msaidizi super agent is not a distant vision — it's a 12-month engineering program.**

The app already has 60% of the building blocks. The transformation is:
1. **Connect** what's disconnected (memory layers, agent loops)
2. **Add** what's missing (flywheel learning, backend, domain knowledge)
3. **Evolve** from static to self-improving (LoRA fine-tuning, behavioral adaptation)
4. **Expand** from single-user to collective intelligence (federated learning)

**The competitive advantage is clear:** No one else is building a self-evolving financial intelligence agent for Africa's informal economy. The data flywheel — where every interaction makes the agent smarter for every user — creates a moat that no platform feature can replicate.

**The window is 18-24 months.** After that, Safaricom will have AI features, WhatsApp will have business intelligence, and the opportunity narrows. Msaidizi must build its super agent now.

**Start with Phase 1. Fix the voice pipeline. Build the backend. Wire the memory. The flywheel begins spinning.**

---

*Super Agent Architecture Design Document*
*Compiled: 2026-07-24*
*Based on: NVIDIA Agent Toolkit, LangChain architecture patterns, Arxiv research, McKinsey AI flywheel framework, and Msaidizi codebase analysis*
*Next step: Detailed design by sub-members (Agent Architecture Analyst, Learning Systems Analyst, Capability Gap Analyst, Implementation Strategist)*
