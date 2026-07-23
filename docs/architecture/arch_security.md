# Msaidizi Super Agent — Security, Privacy & Governance Architecture

**Author:** Chief Security Architect  
**Date:** 2026-07-24  
**Version:** 1.0  
**Classification:** INTERNAL — Architecture Document  
**Regulatory Scope:** Kenya Data Protection Act 2019, GDPR Art. 22, White House EO 14412

---

## Table of Contents

1. [Current State Analysis](#1-current-state-analysis)
2. [Access Control Design](#2-access-control-design)
3. [Sandboxing Architecture](#3-sandboxing-architecture)
4. [Post-Quantum Security](#4-post-quantum-security)
5. [Privacy Architecture](#5-privacy-architecture)
6. [Responsible AI Framework](#6-responsible-ai-framework)
7. [Implementation Roadmap](#7-implementation-roadmap)
8. [Threat Model](#8-threat-model)

---

## 1. Current State Analysis

### 1.1 What Exists (Backend — `angavu-intelligence-backend`)

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **ML-KEM (FIPS 203)** | `app/security/pqc/ml_kem.py` | ✅ Production-ready | Real liboqs implementation, ML-KEM-512/768/1024 |
| **ML-DSA (FIPS 204)** | `app/security/pqc/ml_dsa.py` | ✅ Production-ready | Real liboqs implementation, ML-DSA-44/65/87 |
| **Hybrid Key Exchange** | `app/security/pqc/hybrid_key_exchange.py` | ✅ Production-ready | X25519 + ML-KEM-768 via HKDF-SHA256 |
| **FL Gradient Encryption** | `app/security/pqc/fl_encryption.py` | ✅ Production-ready | ML-KEM + AES-256-GCM + ML-DSA per-update |
| **Crypto Provider Interface** | `app/security/pqc/crypto_provider.py` | ✅ Complete | Algorithm-agnostic abstraction layer |
| **PQC Migration Config** | `app/security/pqc/config.py` | ✅ Complete | 4-phase migration (Classical → Hybrid → PQC-preferred → PQC-only) |
| **TLS 1.3 + PQC Config** | `app/security/pqc/tls_config.py` | ✅ Complete | Dual-signed certs, certificate pinning |
| **Crypto Audit Logger** | `app/security/pqc/audit.py` | ✅ Complete | Structured JSONL audit trail for all crypto ops |
| **Capability Tokens** | `app/security/capability_tokens.py` | ✅ Production-ready | ML-DSA-65 signed, Zanzibar-inspired model |
| **Prompt Injection Guard** | `app/security/prompt_guard.py` | ✅ Production-ready | 20+ regex patterns + heuristic + base64 decode |
| **Security Middleware** | `app/security/security_middleware.py` | ✅ Production-ready | CORS, headers, input validation, audit logging |
| **Rate Limiter** | `app/security/rate_limiter.py` | ✅ Production-ready | Sliding window, per-endpoint, trusted proxy |
| **Privacy Agent** | `app/agents/governance/privacy.py` | ✅ Production-ready | Kenya DPA 2019, DSAR, PII detection, k-anonymity |
| **Ethics Agent** | `app/agents/governance/ethics.py` | ✅ Production-ready | Bias detection, EEOC 4/5ths rule, anti-shame design |
| **Audit Agent** | `app/agents/governance/audit.py` | ✅ Production-ready | Decision trail, explainability scoring |
| **Circuit Breaker Governance** | `app/agents/circuit_breaker_governance.py` | ✅ Production-ready | Auto-pause, escalation, compliance events |
| **Execution Harness** | `app/agents/harness/execution.py` | ✅ Production-ready | Timeout, retry, circuit breaker, cost tracking |

### 1.2 What Exists (Frontend — `angavu-intelligence` / `msaidizi-language-pipeline`)

| Component | Location | Status | Notes |
|-----------|----------|--------|-------|
| **Differential Privacy** | `msaidizi-language-pipeline/federated_learning/` | ✅ Tested | ε=0.1 default, gradient clipping, Gaussian noise |
| **Privacy Policy** | `privacy-policy.html` | ✅ Published | User-facing |
| **Security Matrix CI** | `.github/workflows/security-matrix.yml` | ✅ Active | Automated security checks |
| **Security.txt** | `.well-known/security.txt` | ✅ Published | Vulnerability disclosure |

### 1.3 What's Missing — Gap Analysis

| Gap | Priority | Impact | Section |
|-----|----------|--------|---------|
| **Super Agent Tool Sandboxing** | 🔴 CRITICAL | Agent can execute arbitrary tools without isolation | §3 |
| **Worker Confirmation for Financial Ops** | 🔴 CRITICAL | No human-in-the-loop for M-Pesa/banking actions | §2 |
| **Progressive Autonomy System** | 🟡 HIGH | No trust-score-based permission escalation | §2 |
| **Network Allowlisting for Agent** | 🔴 CRITICAL | Agent tools have unrestricted network access | §3 |
| **Resource Limits (CPU/Memory)** | 🟡 HIGH | No cgroup/ulimit enforcement for tool execution | §3 |
| **On-Device Key Storage** | 🟡 HIGH | PQC keys not protected by Android Keystore / Secure Enclave | §4 |
| **Consent Management UI** | 🟡 HIGH | Consent registry exists but no worker-facing flow | §5 |
| **Right to be Forgotten Pipeline** | 🟡 HIGH | Deletion logic exists but no automated cascade | §5 |
| **Constitutional AI Principles** | 🔴 CRITICAL | No formal behavioral constraints for super agent | §6 |
| **Bias Monitoring Dashboard** | 🟢 MEDIUM | Detection exists but no operational dashboard | §6 |
| **Differential Privacy ε Budget Tracking** | 🟡 HIGH | ε=0.1 defined but no cumulative budget enforcement | §5 |

---

## 2. Access Control Design

### 2.1 Capability-Based Permission Model

The super agent operates under a **capability-based access control (CBAC)** model built on the existing `capability_tokens.py` infrastructure. Each tool/action is a capability that must be explicitly granted.

```
┌─────────────────────────────────────────────────────┐
│                  GOVERNANCE AGENT                     │
│         (Issues & signs all capability tokens)        │
│              ML-DSA-65 signed tokens                  │
└──────────────────────┬──────────────────────────────┘
                       │ issues tokens
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │  SUPER   │ │  SUPER   │ │  SUPER   │
   │  AGENT   │ │  AGENT   │ │  AGENT   │
   │  (Tier 1)│ │  (Tier 2)│ │  (Tier 3)│
   │  Novice  │ │  Trusted │ │  Veteran │
   └──────────┘ └──────────┘ └──────────┘
```

### 2.2 Tool Permission Tiers

#### Tier 0 — Auto-Execute (No Confirmation)

These tools are safe, read-only, or low-risk. The agent executes them autonomously.

```python
AUTO_EXECUTE_TOOLS = {
    # Information retrieval
    "web_search",              # Search the web
    "knowledge_query",         # Query internal knowledge base
    "market_data_read",        # Read market prices, trends
    "weather_check",           # Weather for agricultural planning
    "translate",               # Language translation
    "calendar_read",           # Read worker's calendar
    "notification_read",       # Read notifications
    
    # Analysis
    "transaction_analyze",     # Analyze spending patterns (read-only)
    "business_health_score",   # Compute Alama Score (read-only)
    "market_opportunity_scan", # Identify market gaps
    
    # Communication (drafts only)
    "draft_message",           # Draft a message (doesn't send)
    "draft_report",            # Draft a report (doesn't publish)
    
    # Internal
    "memory_read",             # Read agent memory
    "context_load",            # Load conversation context
    "skill_lookup",            # Look up available skills
}
```

#### Tier 1 — Worker Confirmation Required

These tools affect the worker's data, finances, or external communications. Each requires explicit worker approval via a confirmation prompt.

```python
WORKER_CONFIRM_TOOLS = {
    # Financial operations (CRITICAL)
    "mpesa_send",              # Send M-Pesa payment
    "mpesa_request",           # Request M-Pesa payment
    "bank_transfer",           # Initiate bank transfer
    "invoice_create",          # Create a payable invoice
    "expense_record",          # Record an expense (affects tax)
    "loan_apply",              # Apply for a loan
    "credit_accept",           # Accept a credit offer
    
    # External communications
    "send_message",            # Send a message to a person
    "send_broadcast",          # Send to multiple people
    "post_social",             # Post to social media
    "reply_customer",          # Reply to a customer inquiry
    
    # Data modification
    "transaction_create",      # Create a transaction record
    "transaction_modify",      # Modify existing transaction
    "inventory_update",        # Update inventory counts
    "price_set",               # Set product prices
    "customer_record_modify",  # Modify customer data
    
    # Business operations
    "supplier_order",          # Place an order with a supplier
    "schedule_meeting",        # Schedule a meeting
    "contract_sign",           # Sign a digital contract
}
```

#### Tier 2 — Elevated Confirmation (Financial Threshold)

For financial operations above a threshold, require **enhanced confirmation** — a second factor (PIN or biometric).

```python
ELEVATED_FINANCIAL_TOOLS = {
    # These trigger Tier 2 when amount > threshold
    "mpesa_send": {
        "threshold_kes": 5000,      # > 5,000 KES requires PIN
        "daily_limit_kes": 50000,   # Daily cap
        "confirmation_type": "biometric_or_pin",
    },
    "bank_transfer": {
        "threshold_kes": 10000,
        "daily_limit_kes": 200000,
        "confirmation_type": "biometric_and_pin",
    },
    "loan_apply": {
        "threshold_kes": 0,         # Always requires elevated
        "confirmation_type": "biometric_and_pin",
        "cooldown_hours": 24,       # 24h cooling-off period
    },
}
```

#### Tier 3 — Emergency Override (Locked)

These actions are **never** auto-executed, even with confirmation. They require human admin intervention.

```python
LOCKED_TOOLS = {
    "account_delete",          # Delete worker's account
    "data_export_all",         # Export all worker data
    "permission_grant",        # Grant permissions to third party
    "agent_self_modify",       # Agent modifying its own instructions
    "security_policy_change",  # Change security settings
    "federated_contribute",    # Contribute to federated learning
}
```

### 2.3 Progressive Autonomy System

Workers earn trust over time. More trust = fewer confirmations.

```python
@dataclass
class WorkerTrustProfile:
    worker_id: str
    trust_score: float          # 0.0 to 1.0
    account_age_days: int
    successful_transactions: int
    disputed_transactions: int
    agent_corrections: int      # Times worker corrected the agent
    total_interactions: int
    
    # Autonomy level derived from trust_score
    @property
    def autonomy_level(self) -> AutonomyLevel:
        if self.trust_score >= 0.9 and self.account_age_days >= 180:
            return AutonomyLevel.VETERAN    # Fewer confirmations
        elif self.trust_score >= 0.7 and self.account_age_days >= 90:
            return AutonomyLevel.TRUSTED    # Standard confirmations
        elif self.trust_score >= 0.4 and self.account_age_days >= 30:
            return AutonomyLevel.ESTABLISHED # More confirmations
        else:
            return AutonomyLevel.NOVICE      # Maximum confirmations

class AutonomyLevel(Enum):
    NOVICE = "novice"           # Confirm everything except Tier 0
    ESTABLISHED = "established" # Confirm Tier 1+ only for amounts > 1000 KES
    TRUSTED = "trusted"         # Confirm Tier 1+ only for amounts > 5000 KES
    VETERAN = "veteran"         # Confirm Tier 2+ only (financial thresholds)
```

**Trust Score Calculation:**
```python
def calculate_trust_score(profile: WorkerTrustProfile) -> float:
    """Trust score = weighted combination of signals."""
    base = 0.3  # Everyone starts at 0.3
    
    # Positive signals
    transaction_factor = min(0.3, profile.successful_transactions * 0.001)
    age_factor = min(0.2, profile.account_age_days * 0.001)
    interaction_factor = min(0.1, profile.total_interactions * 0.0005)
    
    # Negative signals
    dispute_penalty = profile.disputed_transactions * 0.05
    correction_penalty = profile.agent_corrections * 0.02
    
    score = base + transaction_factor + age_factor + interaction_factor
    score -= dispute_penalty + correction_penalty
    
    return max(0.0, min(1.0, score))
```

### 2.4 Confirmation UX Flow

```
Worker asks: "Send 3,000 KES to Mama Njeri for tomatoes"

Agent prepares:
┌──────────────────────────────────────────┐
│  🤖 I'd like to send this payment:       │
│                                          │
│  Amount:    KES 3,000                    │
│  Recipient: Mama Njeri (+254 7XX XXX)    │
│  Purpose:   Supplier payment (tomatoes)  │
│  From:      M-Pesa Business Account      │
│                                          │
│  [✅ Confirm]   [❌ Cancel]   [✏️ Edit]  │
└──────────────────────────────────────────┘

Worker taps Confirm → Agent executes mpesa_send
Worker taps Edit → Agent modifies and re-confirms
Worker taps Cancel → Agent logs cancellation, does nothing
```

---

## 3. Sandboxing Architecture

### 3.1 Tool Execution Isolation

Every tool the super agent invokes runs inside a **sandboxed execution context** with strict boundaries.

```
┌─────────────────────────────────────────────────────────────┐
│                    SUPER AGENT RUNTIME                        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              TOOL EXECUTION SANDBOX                    │   │
│  │                                                       │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐ │   │
│  │  │ Tool Process │  │ Tool Process │  │  Tool Process │ │   │
│  │  │ (isolated)   │  │ (isolated)   │  │  (isolated)   │ │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘ │   │
│  │         │                │                 │          │   │
│  │  ┌──────▼────────────────▼─────────────────▼───────┐ │   │
│  │  │           RESOURCE CONTROLLER                    │ │   │
│  │  │  CPU: max 500ms per call                         │ │   │
│  │  │  Memory: max 256MB per tool                      │ │   │
│  │  │  Storage: max 10MB temp per tool                 │ │   │
│  │  │  Network: allowlist only                         │ │   │
│  │  │  Filesystem: workspace only                      │ │   │
│  │  └─────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              AUDIT LOGGER                             │   │
│  │  Every tool call, args, result, duration, resource    │   │
│  │  usage → append-only JSONL audit trail                │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Network Access Control (Allowlist)

The agent's tools can ONLY access pre-approved network destinations.

```python
NETWORK_ALLOWLIST = {
    # M-Pesa API (Safaricom)
    "api.safaricom.co.ke": {
        "ports": [443],
        "protocol": "HTTPS",
        "tools": ["mpesa_send", "mpesa_request", "mpesa_query"],
        "rate_limit": "10/min",
    },
    
    # Internal backend
    "api.angavu.co.ke": {
        "ports": [443],
        "protocol": "HTTPS",
        "tools": ["*"],  # All tools can reach backend
        "rate_limit": "100/min",
    },
    
    # Market data (read-only)
    "nse.co.ke": {
        "ports": [443],
        "protocol": "HTTPS",
        "tools": ["market_data_read"],
        "rate_limit": "30/min",
    },
    
    # Weather API
    "api.openweathermap.org": {
        "ports": [443],
        "protocol": "HTTPS",
        "tools": ["weather_check"],
        "rate_limit": "60/min",
    },
    
    # Translation service (self-hosted LibreTranslate)
    "translate.angavu.co.ke": {
        "ports": [443],
        "protocol": "HTTPS",
        "tools": ["translate"],
        "rate_limit": "30/min",
    },
}

# DEFAULT: DENY ALL — tools must be explicitly listed
NETWORK_DEFAULT_POLICY = "DENY"
```

### 3.3 Resource Limits

```python
TOOL_RESOURCE_LIMITS = {
    "default": {
        "cpu_time_ms": 500,           # Max CPU time per invocation
        "memory_mb": 256,             # Max memory
        "storage_mb": 10,             # Max temp storage
        "wall_time_ms": 5000,         # Max wall-clock time
        "max_concurrent": 3,          # Max concurrent tool calls
        "max_calls_per_minute": 30,   # Rate limit
        "max_calls_per_hour": 200,    # Hourly cap
    },
    "heavy": {  # For compute-intensive tools
        "cpu_time_ms": 2000,
        "memory_mb": 512,
        "storage_mb": 50,
        "wall_time_ms": 15000,
        "max_concurrent": 1,
        "max_calls_per_minute": 5,
        "max_calls_per_hour": 30,
    },
    "financial": {  # For financial tools
        "cpu_time_ms": 1000,
        "memory_mb": 128,
        "storage_mb": 1,              # Minimal storage
        "wall_time_ms": 10000,
        "max_concurrent": 1,          # Serial execution only
        "max_calls_per_minute": 5,
        "max_calls_per_hour": 20,
    },
}
```

### 3.4 Audit Logging for All Agent Actions

Every agent action produces an immutable audit record.

```python
@dataclass
class AgentAuditRecord:
    """Immutable audit record for every agent action."""
    record_id: str                    # UUID
    timestamp: str                    # ISO 8601
    worker_id: str                    # Anonymized worker identifier
    agent_id: str                     # Agent instance ID
    tool_name: str                    # Tool invoked
    tool_args_hash: str              # SHA-256 of arguments (not raw args for privacy)
    result_status: str               # success / failure / denied / cancelled
    result_summary: str              # Brief outcome description
    duration_ms: int                 # Execution time
    resource_usage: dict             # CPU, memory, storage consumed
    network_calls: list[str]         # Domains accessed
    confirmation_type: str           # auto / worker_confirm / elevated / locked
    trust_level: str                 # novice / established / trusted / veteran
    capability_token_id: str         # Token used for authorization
    pqc_signature: str               # ML-DSA-65 signature of this record
    chain_hash: str                  # Hash of previous record (blockchain-style)
```

**Audit storage:** Append-only JSONL files, rotated daily, with ML-DSA-65 signatures on each file header. Minimum 7-year retention per Kenya DPA.

---

## 4. Post-Quantum Security

### 4.1 Current PQC Infrastructure

The codebase already has production-grade PQC:

| Algorithm | Standard | Implementation | Use Case |
|-----------|----------|----------------|----------|
| ML-KEM-768 | NIST FIPS 203 | liboqs (real) | Key encapsulation, TLS key exchange |
| ML-DSA-65 | NIST FIPS 204 | liboqs (real) | Digital signatures, token signing |
| X25519+ML-KEM-768 | IETF draft | Hybrid | TLS 1.3 key exchange |
| AES-256-GCM | NIST FIPS 197 | cryptography lib | Symmetric encryption (quantum-safe at 256-bit) |
| HKDF-SHA256 | RFC 5869 | cryptography lib | Key derivation |

### 4.2 Super Agent PQC Integration

```
┌─────────────────────────────────────────────────────────────┐
│                 PQC PROTECTION LAYERS                        │
│                                                              │
│  Layer 1: Transport                                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  TLS 1.3 + X25519MLKEM768 hybrid key exchange       │    │
│  │  Dual-signed certificates (ECDSA + ML-DSA-65)       │    │
│  │  Certificate pinning with PQC public keys           │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Layer 2: Application                                        │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Capability tokens signed with ML-DSA-65             │    │
│  │  Agent messages signed with ML-DSA-65                │    │
│  │  Audit records signed with ML-DSA-65                 │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Layer 3: Data at Rest                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  ML-KEM-768 per-session key encapsulation            │    │
│  │  AES-256-GCM for data encryption                     │    │
│  │  Per-update ephemeral keys (forward secrecy)         │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Layer 4: Federated Learning                                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  FL gradients: ML-KEM encapsulate → AES-256-GCM     │    │
│  │  Gradient authenticity: ML-DSA-65 sign/verify        │    │
│  │  Differential privacy noise before encryption        │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 On-Device Key Management

Worker devices must protect PQC keys using hardware-backed storage.

```python
class OnDeviceKeyManager:
    """
    Manages PQC keys on worker devices.
    
    Key hierarchy:
    1. Device Root Key (hardware-backed, non-exportable)
       - Android: Android Keystore (StrongBox if available)
       - iOS: Secure Enclave
    2. Application Key (derived from root key)
       - Used to encrypt PQC private keys at rest
    3. PQC Keys (ML-KEM, ML-DSA)
       - Encrypted with Application Key
       - Stored in app private storage
    
    Key rotation:
    - ML-DSA signing keys: rotate every 90 days
    - ML-KEM key pairs: ephemeral per-session (forward secrecy)
    - Device root key: never rotated (hardware-bound)
    """
    
    def __init__(self, platform: str):
        self.platform = platform  # "android" or "ios"
    
    def generate_device_root_key(self) -> str:
        """Generate hardware-backed root key. Returns key alias."""
        if self.platform == "android":
            # Use Android KeyStore with StrongBox
            # Key cannot be exported — operations happen inside TEE
            return self._android_keystore_generate()
        elif self.platform == "ios":
            # Use Secure Enclave
            return self._ios_secure_enclave_generate()
    
    def derive_pqc_signing_key(self, root_alias: str) -> CryptoKeyPair:
        """
        Generate ML-DSA-65 signing key pair.
        Private key encrypted with device root key.
        Public key returned for registration with backend.
        """
        ml_dsa = MlDsaProvider(MlDsaParameterSet.ML_DSA_65)
        key_pair = ml_dsa.generate_key_pair()
        
        # Encrypt private key with device root key
        encrypted_privkey = self._encrypt_with_root(root_alias, key_pair.private_key)
        self._store_encrypted_key("ml_dsa_65_signing", encrypted_privkey)
        
        return key_pair  # Public key for registration
    
    def get_signing_key(self, root_alias: str) -> bytes:
        """Retrieve and decrypt ML-DSA private key for signing."""
        encrypted = self._load_encrypted_key("ml_dsa_65_signing")
        return self._decrypt_with_root(root_alias, encrypted)
```

### 4.4 PQC Migration Strategy (4 Phases)

| Phase | Timeline | Description | Rollback |
|-------|----------|-------------|----------|
| **Phase 1** (Current) | Now — Dec 2026 | Hybrid mode: X25519+ML-KEM-768 for TLS, ML-DSA-65 for tokens | Classical fallback available |
| **Phase 2** | Jan 2027 — Jun 2027 | PQC-preferred: PQC algorithms default, classical fallback | Classical still works |
| **Phase 3** | Jul 2027 — Dec 2027 | PQC-only for new connections, classical deprecated | Only for legacy clients |
| **Phase 4** | Jan 2028+ | PQC-only: classical algorithms removed | No rollback |

**Environment control:**
```bash
ANGAVU_PQC_PHASE=1              # Current migration phase
ANGAVU_PQC_HYBRID_KEX=true      # Enable hybrid key exchange
ANGAVU_PQC_SIGNING=true         # Enable PQC signing
ANGAVU_PQC_AUDIT=true           # Log all PQC operations
```

---

## 5. Privacy Architecture

### 5.1 Kenya Data Protection Act 2019 Compliance Matrix

| DPA Section | Requirement | Implementation | Status |
|-------------|-------------|----------------|--------|
| **S25** | Lawful processing | Consent registry + purpose limitation checks | ✅ |
| **S26** | Sensitive data | PII field detection, SENSITIVE_CATEGORIES enum | ✅ |
| **S28** | Data quality | Input validation middleware | ✅ |
| **S30** | Data retention | Auto-expire (365 days max), retention policies | ✅ |
| **S35** | Right of access | DSAR handler (30-day response) | ✅ |
| **S36** | Right to erasure | Deletion handler (partial — see §5.4) | ⚠️ Gap |
| **S38** | Data portability | JSON export handler | ✅ |
| **S41** | Cross-border transfer | Not implemented | ❌ Gap |
| **S18** | Data Protection Officer | Not designated | ❌ Gap |

### 5.2 Differential Privacy for Federated Learning

The existing `DifferentialPrivacy` class uses **ε=0.1** (strong privacy) by default. This is excellent — it provides meaningful privacy guarantees.

```python
# Existing implementation (msaidizi-language-pipeline/federated_learning/)
class DifferentialPrivacy:
    def __init__(self, epsilon=0.1, delta=1e-5, clip_norm=1.0):
        self.epsilon = epsilon    # Privacy budget
        self.delta = delta        # Failure probability
        self.clip_norm = clip_norm # Gradient clipping bound
    
    # Noise scale: σ = clip_norm * sqrt(2 * ln(1.25/δ)) / ε
    # With ε=0.1, δ=1e-5: σ ≈ 48.45 * clip_norm
```

**Enhancement: Cumulative Privacy Budget Tracking**

```python
class PrivacyBudgetTracker:
    """
    Tracks cumulative privacy expenditure across all FL rounds.
    
    Uses Rényi Differential Privacy (RDP) composition for tight bounds.
    
    Rule: If cumulative ε > ε_max, STOP federated learning until budget resets.
    Budget resets daily.
    """
    
    def __init__(self, epsilon_max: float = 1.0, delta: float = 1e-5):
        self.epsilon_max = epsilon_max  # Daily budget cap
        self.delta = delta
        self.rounds: list[dict] = []
        self._cumulative_epsilon = 0.0
    
    def record_round(self, epsilon_used: float, num_participants: int, sample_rate: float):
        """Record a federated learning round's privacy cost."""
        # RDP composition: ε_composed = ε_1 + ε_2 + ... (simplified)
        # In practice, use advanced composition theorem for tighter bounds
        self._cumulative_epsilon += epsilon_used
        self.rounds.append({
            "epsilon": epsilon_used,
            "cumulative": self._cumulative_epsilon,
            "participants": num_participants,
            "sample_rate": sample_rate,
            "timestamp": datetime.now(UTC).isoformat(),
        })
    
    def can_continue(self) -> bool:
        """Check if we have remaining privacy budget."""
        return self._cumulative_epsilon < self.epsilon_max
    
    def remaining_budget(self) -> float:
        """Return remaining privacy budget for today."""
        return max(0.0, self.epsilon_max - self._cumulative_epsilon)
```

### 5.3 Data Minimization — What Leaves the Device

```python
DATA_MINIMIZATION_RULES = {
    "federated_learning_upload": {
        "allowed": ["gradient_updates", "language_code", "model_version", "timestamp"],
        "forbidden": ["raw_text", "phone_number", "location_gps", "transaction_details", "name"],
        "description": "Only gradient updates and metadata leave the device",
    },
    "intelligence_request": {
        "allowed": ["query_text", "business_type", "location_county"],  # County only, not GPS
        "forbidden": ["phone_number", "national_id", "mpesa_account", "exact_location"],
        "description": "Queries are anonymized — no PII in intelligence requests",
    },
    "transaction_sync": {
        "allowed": ["amount", "category", "timestamp", "direction"],
        "forbidden": ["recipient_name", "recipient_phone", "mpesa_receipt", "account_number"],
        "description": "Transaction metadata only — names and account numbers stay on device",
    },
    "analytics": {
        "allowed": ["event_name", "screen_name", "app_version", "device_type"],
        "forbidden": ["user_id", "phone", "location", "session_data"],
        "description": "Fully anonymized analytics — no user identifiers",
    },
}
```

### 5.4 Right to Be Forgotten — Automated Cascade

```python
class RightToBeForgottenPipeline:
    """
    Automated data deletion pipeline for Kenya DPA Section 36.
    
    Cascade:
    1. Worker requests deletion (via agent or support)
    2. Agent confirms identity (biometric + OTP)
    3. Pipeline executes in order:
       a. Delete PII from primary database
       b. Delete transaction history (keep aggregated anonymized stats)
       c. Delete intelligence reports
       d. Delete credit scores
       e. Delete agent memory/conversation history
       f. Delete federated learning contributions (if identifiable)
       g. Revoke all capability tokens
       h. Send confirmation to worker
    4. 30-day grace period (worker can cancel)
    5. After grace period: permanent deletion + audit log
    
    Retained (anonymized):
    - Aggregated market statistics (no individual attribution)
    - Model training contributions (after differential privacy noise)
    - Audit logs (legal obligation, 7-year retention)
    """
    
    RETENTION_AFTER_DELETION = {
        "aggregated_stats": "indefinite (anonymized)",
        "audit_logs": "7 years (legal requirement)",
        "model_contributions": "anonymized via DP, cannot be traced back",
    }
    
    async def execute_deletion(self, worker_id: str, confirmed: bool = True) -> DeletionReport:
        if not confirmed:
            raise SecurityException("Deletion requires biometric + OTP confirmation")
        
        steps = [
            self._delete_pii(worker_id),
            self._delete_transactions(worker_id),
            self._delete_intelligence(worker_id),
            self._delete_credit_scores(worker_id),
            self._delete_agent_memory(worker_id),
            self._anonymize_fl_contributions(worker_id),
            self._revoke_tokens(worker_id),
            self._send_confirmation(worker_id),
        ]
        
        results = []
        for step in steps:
            result = await step
            results.append(result)
        
        return DeletionReport(worker_id=worker_id, steps=results, grace_period_days=30)
```

### 5.5 Consent Management

```python
class ConsentManager:
    """
    Manages worker consent per Kenya DPA 2019.
    
    Consent types:
    - ESSENTIAL: Required for service (cannot opt out)
    - ANALYTICS: Anonymized usage analytics
    - FEDERATED: Contribution to federated learning
    - MARKETING: Promotional communications
    - THIRD_PARTY: Data sharing with partners
    
    Each consent:
    - Has a clear purpose (purpose limitation)
    - Can be withdrawn at any time
    - Is recorded with timestamp and method
    - Expires after 365 days (must be renewed)
    """
    
    CONSENT_TYPES = {
        "essential": {
            "description": "Core service functionality",
            "required": True,
            "can_opt_out": False,
        },
        "analytics": {
            "description": "Anonymous usage analytics to improve the app",
            "required": False,
            "can_opt_out": True,
        },
        "federated": {
            "description": "Contribute anonymized learning data to improve AI",
            "required": False,
            "can_opt_out": True,
            "privacy_guarantee": "Differential privacy (ε=0.1) + on-device processing",
        },
        "marketing": {
            "description": "Business tips and promotional offers",
            "required": False,
            "can_opt_out": True,
        },
    }
    
    def request_consent(self, worker_id: str, consent_type: str) -> ConsentRequest:
        """Generate a consent request with full transparency."""
        return ConsentRequest(
            worker_id=worker_id,
            type=consent_type,
            description=self.CONSENT_TYPES[consent_type]["description"],
            data_collected=self._get_data_collected(consent_type),
            purpose=self._get_purpose(consent_type),
            retention_days=365,
            can_withdraw=True,
            language=worker_id,  # Will resolve to worker's preferred language
        )
```

---

## 6. Responsible AI Framework

### 6.1 Constitutional AI Principles for the Super Agent

The super agent operates under these **non-negotiable principles**, enforced at runtime:

```python
CONSTITUTIONAL_PRINCIPLES = [
    # ═══════════════════════════════════════════════════════
    # PRINCIPLE 1: Worker Welfare First
    # ═══════════════════════════════════════════════════════
    {
        "id": "W1",
        "principle": "The agent MUST never recommend actions that could harm the worker's livelihood.",
        "enforcement": "pre_action_check",
        "examples": {
            "violate": "Recommending a loan with >30% APR without explicit warning",
            "comply": "Warning about high-interest loans and offering alternatives",
        },
    },
    {
        "id": "W2",
        "principle": "The agent MUST never pressure workers into financial decisions.",
        "enforcement": "tone_analysis",
        "examples": {
            "violate": "'You MUST take this loan now or lose the opportunity'",
            "comply": "'This loan offer is available if you'd like to consider it'",
        },
    },
    {
        "id": "W3",
        "principle": "The agent MUST never shame workers for their financial situation.",
        "enforcement": "content_filter",
        "examples": {
            "violate": "'Your business is performing poorly compared to peers'",
            "comply": "'Your business grew 5% this month — here's how to keep momentum'",
        },
    },
    
    # ═══════════════════════════════════════════════════════
    # PRINCIPLE 2: Transparency
    # ═══════════════════════════════════════════════════════
    {
        "id": "T1",
        "principle": "The agent MUST explain why it recommends any action.",
        "enforcement": "explainability_check",
        "examples": {
            "violate": "'Switch to supplier X' (no reason given)",
            "comply": "'Supplier X offers 15% lower prices based on your order history'",
        },
    },
    {
        "id": "T2",
        "principle": "The agent MUST disclose when it's uncertain or lacks information.",
        "enforcement": "confidence_threshold",
        "examples": {
            "violate": "Presenting a low-confidence prediction as fact",
            "comply": "'Based on limited data, I estimate... (confidence: 60%)'",
        },
    },
    {
        "id": "T3",
        "principle": "The agent MUST never hide its AI nature.",
        "enforcement": "identity_check",
        "examples": {
            "violate": "Implying it's a human advisor",
            "comply": "'I'm your AI business assistant. Here's what I found...'",
        },
    },
    
    # ═══════════════════════════════════════════════════════
    # PRINCIPLE 3: Fairness
    # ═══════════════════════════════════════════════════════
    {
        "id": "F1",
        "principle": "The agent MUST NOT discriminate based on gender, ethnicity, religion, or location.",
        "enforcement": "bias_detection",
        "examples": {
            "violate": "Offering lower credit limits to rural workers",
            "comply": "Credit limits based solely on transaction history and business health",
        },
    },
    {
        "id": "F2",
        "principle": "The agent MUST provide equal quality of service regardless of business size.",
        "enforcement": "service_quality_monitor",
        "examples": {
            "violate": "Prioritizing large businesses for market intelligence",
            "comply": "All businesses receive proportional intelligence for their sector",
        },
    },
    
    # ═══════════════════════════════════════════════════════
    # PRINCIPLE 4: Autonomy
    # ═══════════════════════════════════════════════════════
    {
        "id": "A1",
        "principle": "The agent MUST always defer to the worker's explicit choice.",
        "enforcement": "override_check",
        "examples": {
            "violate": "Executing an action the worker previously rejected",
            "comply": "Respecting 'no' and offering to revisit later if asked",
        },
    },
    {
        "id": "A2",
        "principle": "The agent MUST NOT manipulate workers through urgency or fear.",
        "enforcement": "urgency_analysis",
        "examples": {
            "violate": "'Act NOW or you'll lose everything!'",
            "comply": "'This opportunity is available until Friday. Would you like details?'",
        },
    },
    
    # ═══════════════════════════════════════════════════════
    # PRINCIPLE 5: Data Sovereignty
    # ═══════════════════════════════════════════════════════
    {
        "id": "D1",
        "principle": "Worker data belongs to the worker. The agent is a steward, not an owner.",
        "enforcement": "data_access_check",
        "examples": {
            "violate": "Sharing worker data with third parties without consent",
            "comply": "Data stays on device unless explicitly shared by worker",
        },
    },
    {
        "id": "D2",
        "principle": "The agent MUST minimize data collection to what's strictly necessary.",
        "enforcement": "data_minimization_check",
        "examples": {
            "violate": "Collecting GPS location when county-level data suffices",
            "comply": "Requesting only the minimum data needed for the task",
        },
    },
]
```

### 6.2 Runtime Enforcement

```python
class ConstitutionalEnforcer:
    """
    Enforces constitutional principles at runtime.
    
    Runs BEFORE every agent action as a pre-flight check.
    If any principle is violated, the action is blocked and
    the worker is notified.
    """
    
    def __init__(self, principles: list[dict]):
        self.principles = principles
        self._violation_log: list[dict] = []
    
    async def pre_flight_check(self, action: AgentAction, context: dict) -> CheckResult:
        """
        Check an action against all constitutional principles.
        
        Returns:
            CheckResult with:
            - approved: bool
            - violations: list of violated principles
            - explanation: human-readable explanation
            - suggested_alternative: if action is blocked
        """
        violations = []
        
        for principle in self.principles:
            check_fn = self._get_check_function(principle["enforcement"])
            result = await check_fn(action, context, principle)
            if result.violated:
                violations.append(result)
        
        if violations:
            return CheckResult(
                approved=False,
                violations=violations,
                explanation=self._generate_explanation(violations),
                suggested_alternative=self._suggest_alternative(action, violations),
            )
        
        return CheckResult(approved=True)
    
    def _get_check_function(self, enforcement_type: str) -> Callable:
        """Map enforcement type to check function."""
        checks = {
            "pre_action_check": self._check_pre_action,
            "tone_analysis": self._check_tone,
            "content_filter": self._check_content,
            "explainability_check": self._check_explainability,
            "confidence_threshold": self._check_confidence,
            "identity_check": self._check_identity,
            "bias_detection": self._check_bias,
            "override_check": self._check_override,
            "urgency_analysis": self._check_urgency,
            "data_access_check": self._check_data_access,
            "data_minimization_check": self._check_data_minimization,
            "service_quality_monitor": self._check_service_quality,
        }
        return checks.get(enforcement_type, self._check_default)
```

### 6.3 Bias Detection and Mitigation

```python
class BiasMonitor:
    """
    Monitors agent outputs for bias across protected attributes.
    
    Runs on EVERY agent output (not just credit scores).
    
    Detection methods:
    1. Statistical parity: equal outcomes across groups
    2. Equalized odds: equal TPR/FPR across groups
    3. Disparate impact: 4/5ths rule (EEOC)
    4. Language bias: gendered/shaming language detection
    
    Reporting:
    - Daily bias reports to governance dashboard
    - Alerts when bias exceeds threshold
    - Weekly fairness audit summary
    """
    
    PROTECTED_ATTRIBUTES = [
        "gender", "ethnicity", "religion", "disability",
        "age_group", "location_type", "economic_tier",
    ]
    
    BIAS_THRESHOLDS = {
        "disparate_impact_ratio": 0.8,   # 4/5ths rule
        "max_demographic_skew": 0.3,     # 30% deviation
        "max_outcome_disparity": 0.15,   # 15% outcome difference
        "min_group_size": 10,            # Statistical validity
    }
    
    # Language patterns that indicate bias
    SHAMING_PATTERNS = [
        r"(?i)(poor|bad|terrible|failing|struggling)\s+(performance|business|results)",
        r"(?i)(below|under|worse\s+than)\s+(average|normal|expected|peers)",
        r"(?i)(you\s+should\s+be\s+(ashamed|embarrassed|worried))",
        r"(?i)(competitors?\s+(are|is)\s+(doing|performing)\s+better)",
    ]
    
    POSITIVE_FRAMING_REPLACEMENTS = {
        "poor performance": "room for growth",
        "below average": "on a learning journey",
        "failing business": "business in transition",
        "you're struggling": "you're building resilience",
    }
```

### 6.4 Transparency and Explainability

Every agent decision must be explainable. The worker should always be able to ask "why?" and get a clear answer.

```python
class ExplainabilityEngine:
    """
    Generates human-readable explanations for agent decisions.
    
    Explanation levels:
    1. SUMMARY: One-sentence explanation (default)
    2. DETAILED: Step-by-step reasoning
    3. TECHNICAL: Full decision tree with data sources
    
    All explanations are available in the worker's preferred language.
    """
    
    EXPLANATION_TEMPLATES = {
        "credit_score": {
            "summary": "Your Alama Score is {score} based on your transaction history and business health.",
            "detailed": (
                "Your Alama Score of {score} was calculated from:\n"
                "• Transaction consistency: {transaction_score}/30\n"
                "• Business growth: {growth_score}/25\n"
                "• Customer retention: {retention_score}/20\n"
                "• Supplier relationships: {supplier_score}/15\n"
                "• Digital adoption: {digital_score}/10"
            ),
        },
        "price_recommendation": {
            "summary": "Based on market data, {product} sells for {price_range} in your area.",
            "detailed": (
                "Price analysis for {product}:\n"
                "• Average market price: KES {avg_price}\n"
                "• Your current price: KES {current_price}\n"
                "• Suggested range: KES {low} — KES {high}\n"
                "• Based on: {data_sources}\n"
                "• Confidence: {confidence}%"
            ),
        },
        "supplier_recommendation": {
            "summary": "Supplier {name} offers the best value for your needs.",
            "detailed": (
                "Why I recommend {name}:\n"
                "• Price: {price_comparison}\n"
                "• Delivery reliability: {reliability_score}\n"
                "• Quality rating: {quality_score}\n"
                "• Distance: {distance}\n"
                "• Other options considered: {alternatives_count}"
            ),
        },
    }
```

---

## 7. Implementation Roadmap

### Phase 1: Foundation (Weeks 1–4)

| Task | Owner | Priority |
|------|-------|----------|
| Implement tool permission tiers (§2.2) | Agent Team | 🔴 CRITICAL |
| Add worker confirmation UX for financial ops (§2.4) | Frontend + Agent | 🔴 CRITICAL |
| Implement network allowlisting (§3.2) | Backend | 🔴 CRITICAL |
| Add resource limits to tool execution (§3.3) | Backend | 🟡 HIGH |
| Implement constitutional pre-flight checks (§6.2) | Agent Team | 🔴 CRITICAL |

### Phase 2: Hardening (Weeks 5–8)

| Task | Owner | Priority |
|------|-------|----------|
| On-device key management with hardware backing (§4.3) | Mobile Team | 🟡 HIGH |
| Progressive autonomy system (§2.3) | Agent + Data | 🟡 HIGH |
| Automated right-to-be-forgotten pipeline (§5.4) | Backend | 🟡 HIGH |
| Consent management UI (§5.5) | Frontend | 🟡 HIGH |
| Cumulative privacy budget tracking (§5.2) | FL Team | 🟡 HIGH |

### Phase 3: Monitoring (Weeks 9–12)

| Task | Owner | Priority |
|------|-------|----------|
| Bias monitoring dashboard (§6.3) | Data + Frontend | 🟢 MEDIUM |
| Explainability engine for all decision types (§6.4) | Agent Team | 🟢 MEDIUM |
| Cross-border data transfer controls (DPA S41) | Backend | 🟢 MEDIUM |
| Designate Data Protection Officer (DPA S18) | Legal | 🟢 MEDIUM |
| PQC Phase 2 migration (PQC-preferred) | Security | 🟢 MEDIUM |

---

## 8. Threat Model

### 8.1 STRIDE Analysis for Super Agent

| Threat | Category | Risk | Mitigation |
|--------|----------|------|------------|
| **Prompt injection via user input** | Tampering | HIGH | PromptGuard (20+ patterns), input sanitization |
| **Prompt injection via agent messages** | Tampering | HIGH | SecureMessageHandler (signature + capability + scan) |
| **Agent impersonation** | Spoofing | HIGH | ML-DSA-65 signed capability tokens |
| **Replay attacks on agent messages** | Replay | MEDIUM | Token expiry (1h), use counters, timestamp validation |
| **Data exfiltration via agent** | Information Disclosure | HIGH | Network allowlist, data minimization rules |
| **Worker financial loss via agent** | Tampering | CRITICAL | Worker confirmation, financial thresholds, daily limits |
| **Bias in credit scoring** | Elevation of Privilege | HIGH | EthicsAgent, EEOC 4/5ths rule, fairness constraints |
| **Quantum attack on stored data** | Information Disclosure | FUTURE | ML-KEM + AES-256-GCM (quantum-safe) |
| **Denial of service via tool abuse** | Denial of Service | MEDIUM | Rate limiter, resource limits, circuit breaker |
| **Privacy violation via federated learning** | Information Disclosure | HIGH | Differential privacy (ε=0.1), gradient clipping, on-device processing |
| **Agent self-modification** | Elevation of Privilege | CRITICAL | LOCKED_TOOLS, constitutional principles, governance agent oversight |
| **Supply chain attack (liboqs)** | Tampering | MEDIUM | Pinned versions, integrity checks, fallback to AES-256-GCM |

### 8.2 Attack Surface Minimization

```
ATTACK SURFACE REDUCTION STRATEGY:

1. Network: Allowlist-only (5 approved domains)
2. Filesystem: Workspace-only access, no /tmp, no ~/
3. CPU/Memory: Hard limits per tool invocation
4. Tool access: Default-deny, explicit capability grants only
5. Agent communication: Signed + capability-checked + prompt-scanned
6. Financial operations: Always require human confirmation
7. Data: On-device-first, minimize what leaves the device
8. Crypto: PQC for all new operations, classical fallback only for legacy
```

---

## Appendix A: Security Configuration Reference

```bash
# ═══════════════════════════════════════════════════════
# SECURITY ENVIRONMENT VARIABLES
# ═══════════════════════════════════════════════════════

# PQC Configuration
ANGAVU_PQC_PHASE=1                          # Migration phase (0-3)
ANGAVU_PQC_HYBRID_KEX=true                  # Hybrid key exchange
ANGAVU_PQC_SIGNING=true                     # PQC signing
ANGAVU_PQC_AUDIT=true                       # Crypto audit logging

# Capability Tokens
ANGAVU_CAPABILITY_TOKENS_ENABLED=true       # Enable capability tokens
ANGAVU_CAPABILITY_SWARM_INTELLIGENCE=true   # Per-swarm flags

# Prompt Guard
ANGAVU_PROMPT_GUARD_ENABLED=true            # Enable prompt injection detection
ANGAVU_PROMPT_GUARD_STRICT=true             # Strict mode (block all detections)

# Rate Limiting
ANGAVU_TRUSTED_PROXIES=10.0.0.0/8          # Trusted proxy CIDRs

# Privacy
ANGAVU_DP_EPSILON=0.1                       # Differential privacy epsilon
ANGAVU_DP_DELTA=1e-5                        # Differential privacy delta
ANGAVU_RETENTION_DAYS=365                   # Data retention limit

# Financial Controls
ANGAVU_MPESA_CONFIRM_THRESHOLD=5000         # KES threshold for elevated confirmation
ANGAVU_DAILY_LIMIT_MPESA=50000              # Daily M-Pesa limit
ANGAVU_DAILY_LIMIT_BANK=200000              # Daily bank transfer limit
```

## Appendix B: Audit Record Chain

Each audit record includes a `chain_hash` linking it to the previous record, creating a tamper-evident chain:

```python
def compute_chain_hash(record: AgentAuditRecord, previous_hash: str) -> str:
    """
    Compute chain hash for tamper-evident audit trail.
    
    chain_hash = SHA-256(previous_hash || record_hash)
    
    Where record_hash = SHA-256(serialized record without chain_hash field)
    """
    record_dict = record.to_dict()
    del record_dict["chain_hash"]
    record_bytes = json.dumps(record_dict, sort_keys=True).encode()
    record_hash = hashlib.sha256(record_bytes).digest()
    
    chain_input = bytes.fromhex(previous_hash) + record_hash
    return hashlib.sha256(chain_input).hexdigest()
```

---

*This document is a living architecture. Review quarterly. Update with each PQC migration phase.*
