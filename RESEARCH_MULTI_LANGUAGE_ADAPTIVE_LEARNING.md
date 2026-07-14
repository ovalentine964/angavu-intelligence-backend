# Research: Multi-Language Adaptive Learning for Angavu Intelligence Backend

**Date:** 2026-07-14  
**Scope:** Current state analysis + 2026 AI tools research + recommendations

---

## 1. CURRENT LANGUAGE SUPPORT — Audit

### 1.1 How the Backend Handles Multiple Languages

**Status: BASIC — Hardcoded bilingual (Swahili/English), no dynamic language pipeline.**

The backend currently supports **3 languages** at the model level:
- `sw` — Swahili (default)
- `en` — English
- `sh` — Sheng (urban slang, stored but barely used)

**User model** (`app/models/user.py`):
```python
language = Column(
    Enum("sw", "en", "sh", name="language_enum"),
    default="sw",
    doc="Preferred language: sw=Swahili, en=English, sh=Sheng",
)
```

**Where language is used:**

| Component | Language Handling | Quality |
|-----------|------------------|---------|
| `WhatsAppBot` | `if language == "sw"` / `else` branching | ⚠️ Binary — Sheng falls to English |
| `ReportGenerator` | `if lang == "sw"` / `elif lang == "sh"` / `else` | ⚠️ Only 3 options, Sheng support minimal |
| `DialectAdapter` (onboarding) | 10 dialect adapters defined | ✅ Good design, but adapters aren't connected to reports |
| `WhatsAppAdapter._detect_language()` | Simple keyword heuristic | ⚠️ Very basic — defaults to "sw" |
| `LearningAgent` | Has Swahili sentiment keywords (nzuri, mbaya, etc.) | ✅ Some multilingual awareness |

### 1.2 Language Detection Service

**Status: NO dedicated language detection service.**

- `WhatsAppAdapter._detect_language()` — Simple heuristic checking for English words ("the", "and", "is"). Returns "en" if ≥2 English words found, else "sw". **No Sheng detection.**
- `DialectAdapter.detect_and_select()` — Good design for onboarding (10 dialects), but it's only used during registration, not for ongoing message processing.
- **No integration with any real language detection library** (no langdetect, fasttext, or similar).

### 1.3 WhatsApp Bot Language Responses

**Status: HARDCODED — if/else branching per language.**

Every response in `WhatsAppBot` and `ReportGenerator` uses pattern:
```python
if language == "sw":
    return "Swahili text..."
else:
    return "English text..."
```

**Problems:**
- Sheng (`"sh"`) falls through to English in most places
- No dynamic translation — every string is manually written
- Adding a new language requires touching every method
- No fallback chain (Sheng → Swahili → English)

### 1.4 Intelligence Reports in Worker's Language

**Status: PARTIALLY — Reports respect `user.language` but content is pre-written.**

- `ReportGenerator` generates reports in the user's language via `profile.language`
- The report templates are manually written per language (not translated)
- `AudienceReport` system (`app/services/report_templates/audience_reports.py`) supports audience-aware formatting (worker/bank/government/NGO) but NOT language-aware content generation
- Intelligence pipeline agents (`intelligence_pipeline.py`) generate raw data — language is applied at the formatting layer only

**Key Gap:** The LLM integration (`llm_integration.py`) has a `language` parameter in the Reflexion critique prompt (`Expected language: {language}`) but doesn't actually generate content in that language — it just critiques.

---

## 2. ADAPTIVE LEARNING — Audit

### 2.1 Does the Backend Learn from Worker Interactions?

**Status: SCAFFOLD EXISTS — Not connected to real learning loops.**

- `SelfEvolutionService` (`app/services/self_evolution.py`) — **Well-designed feedback flywheel** with:
  - Feedback collection and classification (8 types)
  - Sentiment scoring (keyword-based)
  - Urgency scoring
  - Feature clustering (keyword overlap, not semantic)
  - Feature spec generation
  - Adoption tracking
  
  **BUT:** All in-memory stores, clustering uses simple word overlap, no actual ML.

- `LearningAgent` (`app/agents/utility/learning_agent.py`) — **Stateless utility agent** with:
  - Keyword-based sentiment analysis (includes Swahili words)
  - Topic extraction
  - Feedback clustering by theme
  
  **BUT:** No persistent learning, no model updates, no personalization.

- `Federated Learning` — Two implementations exist (`federated_learning.py`, `federated_learning_v2.py`) with privacy-preserving aggregation. **This is the most advanced learning component.**

### 2.2 Does It Adapt Report Formats Based on Worker Type?

**Status: YES — Worker classification drives domain-specific agents.**

- `WorkerClassifier` (`app/services/worker_classifier.py`) — Classifies workers into 6 types (transport, trader, agriculture, service, digital, manufacturing) using keyword matching + transaction patterns + category matching + amount patterns (40/30/20/10 weight split).
- Domain agents exist for each type (`app/agents/domain/`): agriculture, retail, transport, service, digital, manufacturing.
- `IntelligencePipeline` has domain-specific planners: MarketAnalysis, CreditScoring, Distribution, Competitor.

**BUT:** Report *format* doesn't adapt — only the *data* fed into reports changes. A mama mboga and a boda boda rider get the same report template with different numbers.

### 2.3 Does It Personalize Responses?

**Status: MINIMAL — Name + language, no behavioral personalization.**

- Reports use `profile.name` and `profile.language`
- `UserProfile` has `business_type`, `location`, `preferred_report_time`
- Daily tips are generated based on sales patterns (data-driven)
- Weekly insights are generated based on best/worst days

**Missing:**
- No learning from which tips a worker acts on
- No adaptation of report length/detail based on engagement
- No preference learning (which reports are read vs ignored)
- No A/B testing of report formats

---

## 3. RESEARCH: Current AI Tools (2026 State)

### 3.1 Multilingual LLMs for African Languages

**Top Models (2026):**

| Model | Languages | African Language Support | Open Source | Best For |
|-------|-----------|------------------------|-------------|----------|
| **Qwen3** (Alibaba) | 119 languages/dialects | Swahili confirmed, broad multilingual | ✅ Yes | General purpose, reasoning |
| **Qwen3.5** (Alibaba) | 119+ | Enhanced multilingual | ✅ Yes | Multimodal agents |
| **Cohere Aya Expanse** | 101 languages | Strong African focus (Amharic to Zulu) | ✅ Yes | Multilingual generation |
| **Cohere Tiny Aya** (3.35B) | 70 languages | Specifically optimized for African + West Asian | ✅ Yes | Edge deployment, low resource |
| **Gemini 3.5** | 70+ speech languages | Live Translate for real-time speech | ❌ Proprietary | Real-time translation |
| **NLLB-200** (Meta) | 200 languages | Strong African MT | ✅ Yes | Translation specifically |
| **AfriNLLB** | African-focused | Pruned NLLB for efficiency | ✅ Yes | Efficient African translation |

**Key Finding:** Qwen3 (the model currently used by Angavu) supports 119 languages including Swahili. Qwen3.5 (Feb 2026) adds native multimodal capabilities. **The foundation model already supports the target languages — the issue is prompt engineering and pipeline integration, not model capability.**

### 3.2 Qwen + Swahili Performance

- Qwen3 supports Swahili as part of its 119-language coverage
- Qwen3Guard (safety model) tested on multilingual benchmarks including African languages
- The current Angavu setup uses `qwen2.5-7b-q4_k_m` locally — **upgrading to Qwen3 would immediately improve multilingual quality**
- For best Swahili quality, Qwen3 + targeted prompting (system prompt in Swahili, few-shot examples) would outperform generic English prompting

### 3.3 Adaptive AI Personalization (2026)

**Current State of the Art:**
- **Meta's Adaptive Ranking Model** (March 2026) — Bends inference scaling for personalization
- **LearnMate 2** (June 2026) — LLM-powered personalized learning system
- **Facebook Reels RecSys** (Jan 2026) — User feedback-driven adaptation

**Pattern:** The industry is moving toward:
1. **Feedback loops** — explicit (ratings) + implicit (engagement metrics)
2. **User embeddings** — vector representations of user behavior
3. **Contextual bandits** — balancing exploration vs exploitation of content
4. **LLM-as-judge** — using LLMs to evaluate personalization quality

### 3.4 Translation APIs & Tools

**Free/Open Source:**

| Tool | Languages | Cost | Quality | Latency |
|------|-----------|------|---------|---------|
| **Opus-MT** (Helsinki) | 50+ language pairs including Swahili | Free (self-hosted) | Good | ~100ms |
| **NLLB-200** (Meta) | 200 languages | Free (self-hosted) | Very Good | ~200ms |
| **AfriNLLB** | African-focused | Free (self-hosted) | Best for African | ~150ms |
| **Google Translate API** | 130+ languages | $20/1M chars | Excellent | ~50ms |
| **Cohere Command-A-Translate** | Many languages | API pricing | Very Good | ~100ms |
| **Gemini Live Translate** | 70+ speech | API pricing | Excellent | Real-time |

**Recommendation:** Self-host **AfriNLLB** or **Opus-MT** for cost-free translation, with Cohere API as quality fallback.

### 3.5 Code-Switching & Sheng

**Sheng is a code-switching language** — it mixes Swahili, English, and local languages dynamically. This is the hardest challenge.

**Research (2026):**
- AfricaNLP 2026 workshop at EACL has papers on code-switching
- Most models still struggle with Sheng because it's informal and evolving
- **Approach:** Don't try to generate Sheng with an LLM — instead:
  1. Detect Sheng input → translate to Swahili for processing
  2. Generate response in Swahili
  3. Post-process: selectively inject Sheng slang for informal contexts
  4. Maintain a **Sheng dictionary** (slang terms mapped to Swahili/English)

---

## 4. GitHub / Open Source Resources

### 4.1 Key Repos to Integrate

1. **[AfriNLLB](https://aclanthology.org/2026.africanlp-main.30.pdf)** — Pruned NLLB models optimized for African languages. Efficient, smaller model size.

2. **[Cohere Tiny Aya](https://cohere.com/blog/cohere-labs-tiny-aya)** — 3.35B multilingual model, specifically strong for African + West Asian languages. Can run on modest hardware.

3. **[Opus-MT](https://github.com/Helsinki-NLP/Opus-MT)** — Pre-trained translation models. Swahili pairs: `sw-en`, `en-sw`, `sw-fr`, etc.

4. **[fastText Language Detection](https://fasttext.cc/docs/en/language-identification.html)** — Lightweight language identification, supports 176 languages. Can detect Swahili vs English vs Sheng-like input.

5. **[Qwen3](https://github.com/QwenLM/Qwen3)** — Upgrade from Qwen2.5 to Qwen3 for better multilingual support. The 8B model would be a drop-in replacement.

### 4.2 HuggingFace Models for African Languages

- `facebook/nllb-200-distilled-600M` — Efficient translation
- `Helsinki-NLP/opus-mt-sw-en` — Swahili to English
- `Helsinki-NLP/opus-mt-en-sw` — English to Swahili
- `CohereForAI/aya-23-8B` — Multilingual generation
- `CohereForAI/tiny-aya-24` — Lightweight multilingual (3.35B)
- `Davlan/afro-xlmr-base` — African language pretrained model

---

## 5. WHAT TO LEVERAGE

### 5.1 Best Qwen Models for Swahili

- **Qwen3-8B** — Best balance of quality and resource requirements. Supports 119 languages. Drop-in replacement for current Qwen2.5-7B.
- **Qwen3-72B** — If API access is available, this is the quality ceiling for multilingual tasks.
- **Current Qwen2.5-7B** — Already supports Swahili, but Qwen3 has significantly better multilingual training.

**Action:** Upgrade to Qwen3-8B. The config already points to a local llama.cpp server — just swap the model file.

### 5.2 Free & Reliable Translation APIs

1. **Self-hosted Opus-MT** — Zero cost, ~100ms latency, good quality for Swahili↔English
2. **Self-hosted NLLB-200-distilled-600M** — Better quality, slightly more resources
3. **Cohere API** (free tier) — Command-A-Translate for high-quality translation
4. **Google Cloud Translation** ($20/1M chars) — Best quality, pay-per-use

### 5.3 Report Generation in Local Languages

**Approach: LLM-powered generation with language-specific system prompts**

Instead of hardcoded `if/else` strings, use the LLM to generate reports:

```python
SYSTEM_PROMPT_SW = """Wewe ni msaidizi wa biashara ya mfanyabiashara mdogo Kenya.
Unda ripoti kwa Kiswahili rahisi, kutumia lugha ya kila siku.
Tumia nambari za KES. Weka ujumbe mfupi na wa moja kwa moja."""

SYSTEM_PROMPT_SHENG = """Wewe ni msaidizi wa biashara. Andika kwa Sheng —
mchanganyiko wa Kiswahili na Kiingereza unaotumika Nairobi.
Mfano: "Sales zako zimepanda!" si "Mauzo yako yameongezeka!\""""
```

This approach:
- Eliminates hardcoded strings
- Handles Sheng naturally (model generates code-switched text)
- Can adapt tone (formal for bank reports, informal for worker reports)
- Works for any language the LLM supports

### 5.4 Handling Sheng in Intelligence Reports

**Strategy: Layered approach**

1. **Input layer:** Detect Sheng → normalize to Swahili for data processing
2. **Processing layer:** All analysis in English/Swahili (structured)
3. **Output layer:** LLM generates in target language with style guide
4. **Sheng dictionary:** Maintain a living dictionary of Sheng terms for the LLM's reference

**Sheng handling rules:**
- Formal reports (bank, government) → **NEVER use Sheng**
- Worker daily reports → **Optional Sheng, default Swahili**
- Alerts/notifications → **Match user's language preference**
- Tips/advice → **Sheng OK for urban youth workers**

---

## 6. RECOMMENDATIONS

### 6.1 Fastest Path to Multi-Language Backend

**Phase 1 (1-2 weeks) — Immediate wins:**
1. **Upgrade Qwen2.5 → Qwen3** — Better multilingual, same deployment
2. **Replace hardcoded strings with LLM-generated text** — Use system prompts per language
3. **Add fastText language detection** — Replace the current keyword heuristic
4. **Connect DialectAdapter to WhatsApp pipeline** — Currently only used in onboarding

**Phase 2 (2-4 weeks) — Translation layer:**
1. **Deploy Opus-MT or NLLB** as internal translation service
2. **Create language routing middleware** — detect → normalize → process → generate → format
3. **Build Sheng dictionary** — Start with 200 common terms
4. **Add language preference to all response paths**

**Phase 3 (1-2 months) — Adaptive personalization:**
1. **Track report engagement** — Which reports are opened/read
2. **Feedback collection** — Simple 👍/👎 on reports
3. **Language preference learning** — Auto-detect from usage patterns
4. **Report format adaptation** — Shorter for low-engagement users, detailed for power users

### 6.2 What Can Be Implemented Immediately

| Item | Effort | Impact | Dependencies |
|------|--------|--------|-------------|
| Upgrade to Qwen3-8B | Low | High | Model download |
| LLM-powered report generation | Medium | High | System prompts |
| fastText language detection | Low | Medium | pip install |
| Connect DialectAdapter to WhatsApp | Low | Medium | None |
| Sheng fallback chain (sh→sw→en) | Low | Medium | None |
| Language-aware system prompts | Low | High | None |

### 6.3 Top 5 Tools/Repos to Integrate

1. **Qwen3-8B** (GGUF) — Drop-in model upgrade for better multilingual
2. **fastText** (`pip install fasttext`) — Language detection (176 languages, <1MB model)
3. **Opus-MT / Helsinki-NLP** — Self-hosted translation for Swahili↔English
4. **Cohere Tiny Aya** — Lightweight multilingual model for edge cases
5. **NLLB-200-distilled-600M** — High-quality African language translation

### 6.4 How to Make Reports Natural in Swahili/English/Sheng

**Architecture change: Template-based → LLM-generated**

Current:
```python
# Hardcoded per-language templates
if lang == "sw":
    text = f"💰 Mauzo: KES {sales:,.0f} ({count} mauzo)"
else:
    text = f"💰 Sales: KES {sales:,.0f} ({count} txns)"
```

Proposed:
```python
# LLM generates from structured data + language style guide
response = await llm.generate(
    system=STYLE_GUIDES[user.language],
    data=report_data,  # Structured JSON
    format="whatsapp",
    max_length=500,
)
```

**Style guides per language:**
- **Swahili:** Simple, direct, uses local business terms (biashara, faida, mauzo)
- **English:** Professional but accessible, Kenyan English style
- **Sheng:** Urban, youthful, code-switched ("Sales zako zimepanda boss!")
- **Dholuo/Kikuyu/etc:** Basic support via translation layer

**Benefits:**
- Natural, human-sounding reports
- Handles code-switching gracefully
- Easy to add new languages (just add style guide)
- Reports can adapt tone based on context (celebratory for good days, encouraging for bad days)

---

## 7. SUMMARY — Readiness Assessment

| Dimension | Current State | Readiness | Gap |
|-----------|--------------|-----------|-----|
| **Language detection** | Keyword heuristic | 🔴 Low | Need fastText or similar |
| **Multi-language support** | 3 languages, hardcoded | 🟡 Medium | Need LLM generation |
| **Swahili report quality** | Manual templates | 🟡 Medium | Need LLM-powered generation |
| **Sheng support** | Stored but unused | 🔴 Low | Need Sheng dictionary + LLM |
| **Dialect adaptation** | 10 adapters defined, unused | 🟡 Medium | Need to wire into pipeline |
| **Worker type adaptation** | Classification works | 🟢 High | Need format adaptation |
| **Feedback learning** | Scaffold exists | 🟡 Medium | Need to wire to DB + LLM |
| **Personalization** | Minimal (name + lang) | 🔴 Low | Need engagement tracking |
| **LLM multilingual capability** | Qwen2.5 supports Swahili | 🟢 High | Upgrade to Qwen3 for better quality |
| **Translation infrastructure** | None | 🔴 Low | Need Opus-MT or NLLB |

**Bottom line:** The backend has a **strong architectural foundation** (dialect adapters, worker classification, feedback flywheel, LLM integration points) but **minimal multilingual implementation**. The good news: Qwen3 already supports 119 languages, so the gap is in **pipeline integration and prompting**, not in model capability. The fastest path is upgrading to Qwen3 + replacing hardcoded strings with LLM-generated text using language-specific system prompts.
