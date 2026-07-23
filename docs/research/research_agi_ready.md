# AGI Readiness Research: What's Available RIGHT NOW (July 2026)

**Prepared for:** Valentine Owuor / Msaidizi & Angavu
**Date:** July 24, 2026
**Researcher:** Lead AGI Readiness Specialist

---

## PART 1: What's Available in the AGI Race RIGHT NOW

### 1. OpenAI

**Current Model Lineup (as of July 2026):**

| Model | Input/MTok | Output/MTok | Context | Notes |
|-------|-----------|-------------|---------|-------|
| **gpt-5.6-sol** | $5.00 | $30.00 | Short/Long | Flagship, highest capability |
| **gpt-5.6-terra** | $2.50 | $15.00 | Short/Long | Mid-tier flagship |
| **gpt-5.6-luna** | $1.00 | $6.00 | Short/Long | Budget flagship |
| **gpt-5.5** | $5.00 | $30.00 | Short/Long | Previous gen |
| **gpt-5.5-pro** | $30.00 | $180.00 | Short/Long | Premium reasoning |
| **gpt-5.4-mini** | $0.75 | $4.50 | Standard | Budget tier |
| **gpt-5.4-nano** | $0.20 | $1.25 | Standard | Ultra-budget |

**Agent Capabilities:**
- Full function calling, tool use, code execution
- Codex agent capabilities (being integrated into ChatGPT)
- Multi-agent orchestration via Responses API
- Deep research capabilities
- Image generation (gpt-image-2), video generation (sora-2)
- Realtime voice API ($32-$64/MTok for audio)
- Web search built-in ($10/1k calls)

**Deprecations:** o3, GPT-4.5 retired (May 2026). GPT-4o still available. Atlas being deprecated (Aug 9, 2026).

**AGI Claim:** OpenAI claims GPT-5.6 approaches AGI-level reasoning. The "sol" tier represents their most capable model ever. However, "AGI" remains marketing — these are still narrow AI systems with impressive capabilities.

**Verdict for Msaidizi:** Too expensive for daily worker interactions ($5-30/MTok input). Best reserved for complex, high-value tasks.

---

### 2. Anthropic (Claude)

**Current Model Lineup (as of July 2026):**

| Model | Input/MTok | Output/MTok | Context | Notes |
|-------|-----------|-------------|---------|-------|
| **Claude Fable 5** | $10.00 | $50.00 | 1M | Most capable, next-gen intelligence |
| **Claude Mythos 5** | $10.00 | $50.00 | 1M | Limited availability (Project Glasswing) |
| **Claude Opus 4.8** | $5.00 | $25.00 | 1M | Complex agentic coding & enterprise |
| **Claude Sonnet 5** | $2.00→$3.00 | $10.00→$15.00 | 1M | Best speed/intelligence balance |
| **Claude Haiku 4.5** | $1.00 | $5.00 | 200k | Fast, near-frontier intelligence |

**Agent Capabilities:**
- Code execution tool
- MCP (Model Context Protocol) connector
- Files API
- Prompt caching (up to 1 hour)
- Computer use capabilities
- Extended thinking mode
- Multi-agent orchestration

**Constitutional AI Alignment:** Anthropic's Constitutional AI approach directly aligns with Msaidizi's values:
- Built-in safety guardrails
- Transparent decision-making
- Designed to avoid harmful outputs
- Emphasis on being helpful, harmless, and honest

**Free Tier:** No free API tier. Claude.ai offers limited free usage.

**Verdict for Msaidizi:** Claude Haiku 4.5 ($1/$5 per MTok) is the sweet spot — fast, capable, and affordable. Constitutional AI values align with building for humanity. Sonnet 5 at $2-3/MTok is excellent for complex reasoning tasks.

---

### 3. Google DeepMind (Gemini)

**Current Model Lineup (as of July 2026):**

| Model | Notes |
|-------|-------|
| **Gemini 3.6 Flash** | Latest release (July 2026), fastest |
| **Gemini 3.5 Pro** | Currently testing, next-gen |
| **Gemini 3.5 Flash-Lite** | Budget tier |
| **Gemini 3.5 Flash Cyber** | Security-focused |
| **Gemini 2.5 Pro** | Previous gen, still available |
| **Gemini 2.5 Flash** | Previous gen, still available |

**Multimodal Capabilities:**
- Native multimodal: text, image, video, audio
- 1M+ context windows
- Built-in grounding with Google Search
- Code execution
- Agent capabilities via Vertex AI

**Pricing:**
- Free tier: 1,500 grounded prompts/day for Flash models
- 10,000 grounded prompts/day for Pro models
- Paid pricing competitive with Anthropic

**AGI Claim:** Google positions Gemini as multimodal intelligence, not explicitly AGI. The rapid iteration (2.5 → 3.5 → 3.6 in months) shows aggressive development.

**Verdict for Msaidizi:** The free tier is significant — 1,500+ prompts/day for free could serve many workers. Gemini Flash models are fast and cheap. Google's Africa presence (AI Hub for Sustainable Development) could be an opportunity.

---

### 4. Meta (Llama)

**Current Model Lineup (as of July 2026):**

| Model | Total Params | Active Params | Context | License |
|-------|-------------|---------------|---------|---------|
| **Llama 4 Scout** | 109B | 17B | 10M | Llama Community |
| **Llama 4 Maverick** | 400B+ | ~17B | 1M | Llama Community |

**Key Facts:**
- Released April 2025, still current generation (no Llama 5 as of July 2026)
- Natively multimodal (text + image)
- Mixture-of-experts architecture
- "Behemoth" teacher model (~2T params) previewed but NOT released — likely shelved
- Llama Community License: free under 700M monthly active users

**Open-Weight Advantages:**
- **Cost = $0 for inference** (self-hosted)
- No per-token API bills
- No rate limits, no vendor lock-in
- Full data sovereignty
- Fine-tunable for specific domains

**Hardware Requirements:**
- Scout: Single H100 GPU (109B total, 17B active)
- Maverick: Multi-GPU setup required
- MoE architecture enables efficient inference

**Verdict for Msaidizi:** Llama 4 Scout is the best open-weight option for self-hosting. 17B active params can run on modest hardware. Free inference is critical for serving millions of informal workers. However, Llama 4 hasn't kept pace with Qwen's rapid iteration.

---

### 5. DeepSeek

**Current Model Lineup (as of July 2026):**

| Model | Input/MTok (Cache Miss) | Output/MTok | Context | Notes |
|-------|------------------------|-------------|---------|-------|
| **DeepSeek V4 Pro** | $0.435 | $0.87 | 1M | Highest capability |
| **DeepSeek V4 Flash** | $0.14 | $0.28 | 1M | Budget, fast |

**Key Facts:**
- V4 is the current generation (V3 deprecated)
- Supports both thinking and non-thinking modes
- Tool calling, JSON output, FIM completion
- 1M context window
- 384K max output

**Cost Comparison:**
- DeepSeek V4 Flash: **$0.14/MTok input** — that's 35x cheaper than GPT-5.6-sol
- DeepSeek V4 Pro: **$0.435/MTok input** — still 11x cheaper than GPT-5.6-sol
- Cache hits as low as $0.0028/MTok

**Agent Capabilities:**
- Full tool calling support
- JSON mode
- Chat prefix completion
- Anthropic API compatibility endpoint

**Verdict for Msaidizi:** DeepSeek is the **price-performance champion**. At $0.14/MTok input, a worker's daily AI usage could cost less than $0.01. The Anthropic API compatibility makes integration easy. This is the best cloud brain for Msaidizi's hybrid architecture.

---

### 6. Others

#### xAI (Grok)
- **Grok 4.5** (July 2026): $2.00/MTok input, $6.00/MTok output
- 500k context window
- Real-time X (Twitter) search integration
- Image and video generation
- Voice API ($0.05/min realtime)
- Multi-agent capabilities

#### Mistral
- **Mistral Small 4** (March 2026): 119B total, 6B active (MoE), 256k context
- Apache 2.0 license — fully open
- Unifies reasoning, multimodal, and agentic coding in one model
- 40% latency reduction, 3x throughput improvement
- **Mistral Large 3**: Enterprise flagship
- **Mistral Medium 3.5**: Mid-tier

#### Qwen (Alibaba)
- **Qwen 3.5/3.6 Plus**: Leading on coding benchmarks
- 0.8B to 397B parameter range — widest model size selection
- Apache 2.0 license
- 201 languages supported (best multilingual coverage)
- 1M context window with hybrid architecture (MoE + linear attention)
- **Qwen 3 is what Msaidizi already uses (0.8B on-device)**

#### African AI Initiatives
- **AI Hub for Sustainable Development**: African Development Bank + UNDP partnership
- **AI 10 Billion Initiative**: Launched at 2026 Nairobi AI Forum
- **Global Index on Responsible AI (GIRAI)**: Nigeria ranked #1 in Africa, Kenya in top tier
- Growing focus on AI for informal economy across the continent

---

## PART 2: What Can These Models Do for Informal Workers?

### Task-by-Task Analysis

| Worker Task | Best Model | Cost/Query | Better Than On-Device Qwen 0.8B? |
|------------|-----------|------------|----------------------------------|
| **Price lookup** (mama mboga) | On-device Qwen 0.8B | $0 (free) | No — on-device is sufficient |
| **Voice conversation** in Swahili | DeepSeek V4 Flash | ~$0.001 | Yes — better language understanding |
| **Financial record keeping** | On-device Qwen 0.8B | $0 (free) | No — simple math is fine |
| **Complex business advice** | Claude Haiku 4.5 or DeepSeek V4 Pro | $0.005-0.01 | Yes — much better reasoning |
| **Market price analysis** | Gemini Flash (free tier) | $0 | Yes — can access real-time data |
| **Document understanding** (receipts, contracts) | Claude Sonnet 5 | $0.02-0.05 | Yes — much better OCR/understanding |
| **Multi-step planning** (business expansion) | Claude Opus 4.8 or GPT-5.6 | $0.05-0.10 | Yes — far superior reasoning |
| **Translation** (local languages) | Qwen 3.5 (multilingual) or DeepSeek | $0.001-0.005 | Yes — better quality |
| **Route optimization** (boda-boda) | On-device Qwen 0.8B + maps API | $0 (free) | Depends — on-device may suffice |
| **Dispute resolution** | Claude Haiku 4.5 | $0.005 | Yes — better at nuanced reasoning |

### Key Insight: The Hybrid Sweet Spot

- **80% of daily tasks** can be handled by on-device Qwen 0.8B (free, offline, instant)
- **15% of tasks** benefit from cloud escalation (DeepSeek V4 Flash at $0.14/MTok)
- **5% of tasks** need frontier models (Claude/GPT for complex reasoning)

**Estimated cost per worker per month:** $0.50-$2.00 with smart routing

---

## PART 3: Building AGI-Ready Architecture

### 3.1 The Hybrid Approach

```
┌─────────────────────────────────────────────────────────┐
│                    USER (Voice/Text)                      │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              INTENT CLASSIFIER (On-Device)               │
│         "Can Qwen 0.8B handle this?"                     │
└──────┬────────────────────────────────────┬─────────────┘
       │ YES (80%)                          │ NO (20%)
       ▼                                    ▼
┌──────────────────┐          ┌────────────────────────────┐
│  ON-DEVICE QWEN  │          │     ROUTING LAYER          │
│     0.8B         │          │  "What level of thinking   │
│  - Quick answers │          │   does this need?"         │
│  - Translations  │          └──────┬─────────────┬───────┘
│  - Basic math    │                 │             │
│  - Local info    │          SIMPLE │      COMPLEX│
└──────────────────┘                ▼             ▼
                       ┌────────────────┐ ┌────────────────┐
                       │ DeepSeek V4    │ │ Claude Haiku    │
                       │ Flash          │ │ 4.5 / Sonnet 5 │
                       │ ($0.14/MTok)   │ │ ($1-3/MTok)    │
                       │ - Reasoning    │ │ - Complex advice│
                       │ - Translation  │ │ - Multi-step    │
                       │ - Summarize    │ │ - Planning      │
                       └────────────────┘ └────────────────┘
```

### Escalation Rules

| Signal | Action |
|--------|--------|
| User asks "what is X?" | Stay on-device |
| User asks "how should I..." | Escalate to DeepSeek |
| User provides document image | Escalate to Claude/Gemini |
| User asks multi-step question | Escalate to Claude |
| Offline / no connectivity | Force on-device (with graceful degradation) |
| User explicitly requests "smart mode" | Escalate to frontier |
| Latency > 3 seconds | Fall back to on-device |

### 3.2 AGI-as-a-Service

**Can Msaidizi use frontier models as a "brain in the cloud"?**

YES. Here's the cost analysis:

| Provider | Model | Cost/Worker/Month | Latency |
|----------|-------|-------------------|---------|
| **DeepSeek** | V4 Flash | **$0.50-$1.00** | 1-3s |
| **Google** | Gemini Flash (free tier) | **$0** (1,500 prompts/day) | 1-2s |
| **Anthropic** | Haiku 4.5 | **$1.00-$2.00** | 1-3s |
| **OpenAI** | gpt-5.4-nano | **$0.50-$1.50** | 1-2s |
| **Mistral** | Small 4 (self-hosted) | **$0** (infra cost) | <1s |

**Voice Conversation Feasibility:**
- DeepSeek V4 Flash: 1-3 second latency — acceptable for voice
- Gemini Flash: 1-2 seconds — good for voice
- On-device Qwen 0.8B: <500ms — best for voice
- **Hybrid approach**: On-device for voice, cloud for complex reasoning (accept 2-3s pause)

### 3.3 The Super Agent Evolution

**From "Smart Assistant" → "Super Agent"**

| Phase | Capabilities | Timeline |
|-------|-------------|----------|
| **Phase 1: Assistant** | Answer questions, translate, basic advice | Now (already built) |
| **Phase 2: Agent** | Take actions: book services, send messages, manage finances | Month 3-6 |
| **Phase 3: Orchestrator** | Coordinate multiple services, negotiate prices, find deals | Month 6-12 |
| **Phase 4: Super Agent** | Autonomous business management, predictive planning, network effects | Month 12-24 |

**Capabilities Needed for Super Agent:**
1. **Tool use**: Function calling to interact with APIs (M-Pesa, logistics, suppliers)
2. **Memory**: Long-term memory of user preferences, history, relationships
3. **Planning**: Multi-step reasoning for complex goals
4. **Negotiation**: Ability to compare options and make recommendations
5. **Proactive action**: Suggest actions before being asked
6. **Multi-agent coordination**: Multiple specialized agents working together

### 3.4 Responsible AGI

**How to ensure AGI serves workers, not exploits them:**

1. **Data Sovereignty**: Workers own their data. Never sell worker data to third parties.
2. **Transparency**: Always disclose when AI is making recommendations vs. facts.
3. **Opt-in Escalation**: Workers choose when to use cloud AI (with cost disclosure).
4. **Constitutional AI Principles** (from Anthropic's approach):
   - Be helpful to the worker's goals
   - Be harmless — never recommend risky financial decisions
   - Be honest — never inflate earnings or hide costs
   - Respect autonomy — the worker makes final decisions
5. **Safeguards**:
   - No addictive design patterns
   - No dark patterns to increase usage
   - Clear cost disclosure for cloud features
   - Offline-first: works without internet
   - No surveillance: don't track workers for third parties

**Alignment with Msaidizi's Values:**
- Anthropic's Constitutional AI directly maps to "AI that respects humanity"
- Open-weight models (Qwen, Llama) ensure no vendor lock-in
- On-device processing preserves privacy
- Hybrid architecture ensures accessibility (works offline)

---

## PART 4: The AGI Roadmap for Msaidizi

### MONTH 1-6: Foundation (Build NOW)

| Action | Priority | Effort |
|--------|----------|--------|
| **Integrate DeepSeek V4 Flash** as cloud brain | 🔴 Critical | 2 weeks |
| **Build intent classifier** (on-device vs. cloud routing) | 🔴 Critical | 3 weeks |
| **Implement prompt caching** for repeated queries | 🟡 High | 1 week |
| **Add Claude Haiku 4.5** as fallback for complex tasks | 🟡 High | 1 week |
| **Test Gemini free tier** for market data queries | 🟡 High | 1 week |
| **Build offline-first architecture** with graceful cloud escalation | 🔴 Critical | 4 weeks |
| **Implement cost tracking** per worker | 🟡 High | 2 weeks |
| **Add Swahili fine-tuning** to on-device Qwen 0.8B | 🟡 High | 4 weeks |

**Target:** By Month 6, Msaidizi can handle 95% of worker queries (80% on-device, 15% cheap cloud, 5% frontier) at <$1/worker/month.

### MONTH 6-12: Agent Capabilities (Build NEXT)

| Action | Priority | Effort |
|--------|----------|--------|
| **Implement function calling** (M-Pesa, logistics APIs) | 🔴 Critical | 4 weeks |
| **Build agent memory** (long-term user context) | 🔴 Critical | 3 weeks |
| **Multi-agent architecture** (specialized agents for finance, health, etc.) | 🟡 High | 6 weeks |
| **Voice conversation** with cloud escalation | 🟡 High | 4 weeks |
| **Document understanding** (receipts, contracts via camera) | 🟡 High | 3 weeks |
| **Proactive suggestions** ("Your stock is low, reorder?") | 🟢 Medium | 2 weeks |
| **Evaluate Mistral Small 4** for self-hosted inference | 🟢 Medium | 2 weeks |

**Target:** By Month 12, Msaidizi is a true agent — it can take actions, remember context, and proactively help workers.

### MONTH 12-24: Scale & Intelligence (Build TOWARD)

| Action | Priority | Effort |
|--------|----------|--------|
| **Self-hosted inference** (Mistral Small 4 or Qwen 3.5 on local GPU) | 🔴 Critical | 8 weeks |
| **Network effects** (worker-to-worker recommendations) | 🟡 High | 6 weeks |
| **Predictive analytics** (demand forecasting, price trends) | 🟡 High | 6 weeks |
| **Multi-modal agent** (voice + image + text in one conversation) | 🟡 High | 4 weeks |
| **Negotiation agent** (compare suppliers, find best prices) | 🟢 Medium | 4 weeks |
| **Cross-border support** (East Africa → pan-African) | 🟢 Medium | 8 weeks |
| **Evaluate frontier AGI models** as they release | 🟢 Ongoing | Continuous |

**Target:** By Month 24, Msaidizi is the most intelligent AI assistant for informal workers in Africa, with self-hosted capabilities reducing cloud costs to near-zero.

### 24+ MONTHS: Watch & Adapt

| Signal | Action |
|--------|--------|
| **AGI models released** (true multi-domain reasoning) | Evaluate and integrate if cost-effective |
| **On-device AGI** (models that run locally with AGI-like capabilities) | Replace cloud dependency |
| **AI regulation in Kenya/Africa** | Ensure compliance, lead on responsible AI |
| **Open-weight AGI** (if any lab releases AGI-class open models) | Self-host immediately |
| **Hardware advances** (cheaper GPUs, AI chips) | Enable more on-device processing |
| **African AI ecosystem** (local models, local infrastructure) | Partner and integrate |

---

## EXECUTIVE SUMMARY

### The Biggest Opportunity Right Now

1. **DeepSeek V4 Flash at $0.14/MTok** is the game-changer — 35x cheaper than OpenAI's flagship, with 1M context and full agent capabilities. This makes cloud AI affordable for informal workers.

2. **Google Gemini's free tier** (1,500 prompts/day) can serve many workers at zero cost.

3. **Qwen 3.5/3.6** is the best open-weight model for multilingual use (201 languages, Apache 2.0). Upgrade from Qwen 0.8B to a larger Qwen model when hardware allows.

4. **Mistral Small 4** under Apache 2.0 is the best self-hosted option — 119B params but only 6B active, runs on a single GPU.

### The Recommended Stack

```
ON-DEVICE:    Qwen 0.8B (free, offline, instant)
CLOUD TIER 1: DeepSeek V4 Flash ($0.14/MTok, 90% of cloud queries)
CLOUD TIER 2: Claude Haiku 4.5 ($1/MTok, complex reasoning)
CLOUD TIER 3: Gemini Flash (free tier, market data)
FUTURE:       Self-hosted Mistral Small 4 (zero marginal cost)
```

### Cost Projection

| Scale | Monthly Cost | Per Worker |
|-------|-------------|------------|
| 1,000 workers | $500-$1,000 | $0.50-$1.00 |
| 10,000 workers | $3,000-$5,000 | $0.30-$0.50 |
| 100,000 workers | $15,000-$25,000 | $0.15-$0.25 |
| 1,000,000 workers | $50,000-$100,000 | $0.05-$0.10 |

**At scale, with self-hosted inference:** <$0.01/worker/month

### The AGI Readiness Checklist

- [x] On-device AI model (Qwen 0.8B) — DONE
- [ ] Cloud escalation layer (DeepSeek V4 Flash)
- [ ] Intent classifier / routing logic
- [ ] Offline-first architecture
- [ ] Cost tracking and optimization
- [ ] Agent capabilities (function calling)
- [ ] Long-term memory
- [ ] Multi-agent architecture
- [ ] Self-hosted inference capability
- [ ] Responsible AI framework
- [ ] Regulatory compliance framework

**The window is NOW.** Open-weight models are closing the gap with frontier models. The cost of cloud AI has dropped 35x in 18 months. Msaidizi has the on-device foundation. The next 6 months of integration will determine whether Msaidizi leads or follows in the AGI era.

---

*Research compiled July 24, 2026. Sources: OpenAI API pricing, Anthropic Claude docs, Google Gemini changelog, DeepSeek API docs, xAI docs, Mistral news, Digital Applied research, Tech Insider analysis, African Development Bank reports.*
