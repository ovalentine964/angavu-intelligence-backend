# Data Protection Impact Assessment (DPIA)
## Angavu Intelligence Platform
### Kenya Data Protection Act, 2019 Compliance

**Document Version:** 1.0
**Date:** 2026-08-01
**Status:** Initial Assessment
**Next Review:** 2027-02-01 (6 months)

---

## 1. Introduction

### 1.1 Purpose
This Data Protection Impact Assessment (DPIA) is conducted under Section 31 of the Kenya Data Protection Act, 2019 (DPA) to evaluate the data processing activities of the Angavu Intelligence Platform and ensure compliance with the Act's requirements.

### 1.2 Scope
This DPIA covers:
- Collection and processing of financial transaction data (M-Pesa, bank statements)
- Credit scoring and risk assessment algorithms
- Knowledge graph construction from business transaction data
- Federated learning and privacy-preserving analytics
- Human-in-the-loop approval workflows
- Webhook processing of third-party data feeds

### 1.3 Legal Basis
Under Section 30 of the Kenya DPA, this DPIA is required because the platform:
- Processes sensitive personal data (financial transactions)
- Uses automated decision-making (credit scoring)
- Processes data on a large scale (projected 100K+ users)
- Combines datasets from multiple sources

---

## 2. Data Processing Description

### 2.1 Data Categories

| Category | Examples | Sensitivity | Retention |
|----------|----------|-------------|-----------|
| Transaction Data | M-Pesa receipts, amounts, timestamps | High | 7 years (KRA) |
| Business Data | Sales, inventory, expenses | Medium | 5 years |
| Location Data | GPS coordinates for delivery/rides | High | 90 days |
| Device Data | Phone model, OS version | Low | 1 year |
| Conversation Data | Agent interactions, voice inputs | Medium | 2 years |
| Credit Data | Scores, risk assessments | High | 5 years |

### 2.2 Data Subjects
- MSME owners and operators (primary)
- Customers of MSMEs (secondary, anonymized)
- M-Pesa agents and boda boda riders
- Chama (savings group) members

### 2.3 Processing Activities
1. **Data Collection:** Via M-Pesa SMS parsing, manual input, API integrations
2. **Storage:** Encrypted PostgreSQL (pgcrypto), SQLCipher on device
3. **Analysis:** Credit scoring, demand forecasting, anomaly detection
4. **Sharing:** Anonymized aggregates via k-anonymity (k≥10)
5. **AI Processing:** LLM-based business advice, federated learning

---

## 3. Risk Assessment

### 3.1 Identified Risks

| Risk ID | Risk Description | Likelihood | Impact | Mitigation |
|---------|-----------------|------------|--------|------------|
| R1 | Unauthorized access to financial data | Medium | Critical | JWT auth, TLS 1.3, AES-256-GCM |
| R2 | Re-identification from anonymized data | Low | High | k-anonymity (k≥10), cohort merging |
| R3 | M-Pesa transaction data exposure | Medium | Critical | Encrypted at rest, audit logging |
| R4 | Credit scoring bias/discrimination | Medium | High | Regular bias audits, human review |
| R5 | Data breach affecting MSMEs | Low | Critical | Encryption, rate limiting, monitoring |
| R6 | Unauthorized webhook data injection | Medium | Medium | API key auth, HMAC validation |
| R7 | Cross-border data transfer | Low | High | Data residency in Kenya (Oracle Cloud) |
| R8 | AI hallucination causing financial harm | Medium | High | Human-in-the-loop approval, audit trail |

### 3.2 Privacy Risks to Data Subjects

| Risk | Affected Groups | Severity | Current Controls |
|------|----------------|----------|-----------------|
| Financial profiling without consent | All users | High | Consent screen, purpose limitation |
| Location tracking beyond service need | Boda/ride users | High | 90-day retention, GPS only during trips |
| Credit discrimination | Loan applicants | High | Bias monitoring, human review for rejections |
| Data shared with third parties | All users | Medium | No PII sharing, only anonymized aggregates |
| Inability to access/delete data | All users | Medium | Data export API (planned), deletion requests |

---

## 4. Safeguards and Controls

### 4.1 Technical Measures

| Control | Implementation | Status |
|---------|---------------|--------|
| **Encryption at rest** | AES-256-GCM (Android Keystore), pgcrypto (PostgreSQL) | ✅ Implemented |
| **Encryption in transit** | TLS 1.2/1.3, certificate pinning | ✅ Implemented |
| **Authentication** | JWT with short-lived tokens, biometric auth | ✅ Implemented |
| **Authorization** | Role-based access, buyer tiers | ✅ Implemented |
| **Rate limiting** | Per-IP (webhooks), per-key (API), token bucket | ✅ Implemented |
| **Input validation** | garde crate validation on all endpoints | ✅ Implemented |
| **Audit logging** | All data access logged with timestamps | ✅ Implemented |
| **k-Anonymity** | k≥10 for all aggregate queries | ✅ Implemented |
| **Differential Privacy** | Laplace mechanism, ε=0.1 | ✅ Implemented |
| **Data minimization** | Only necessary fields collected | ✅ Implemented |
| **Certificate pinning** | SPKI hash pinning for API connections | ✅ Implemented |
| **Secrets management** | Environment variables, no hardcoded secrets | ✅ Implemented |

### 4.2 Organizational Measures

| Control | Implementation | Status |
|---------|---------------|--------|
| **Privacy policy** | Published on website and in-app | 📋 Planned |
| **Consent management** | Granular consent screen in app | ✅ Implemented |
| **Data breach response** | 72-hour notification to ODPC | 📋 Planned |
| **Staff training** | Privacy awareness for all team members | 📋 Planned |
| **DPO appointment** | Data Protection Officer designated | 📋 Required |
| **Vendor agreements** | DPAs with all third-party processors | 📋 Planned |

---

## 5. Compliance Mapping

### 5.1 Kenya DPA Requirements

| DPA Section | Requirement | Implementation |
|-------------|-------------|----------------|
| **S25** | Lawful processing | Consent + legitimate interest (credit scoring) |
| **S26** | Purpose limitation | Data used only for stated business purposes |
| **S27** | Data minimization | Only essential fields collected |
| **S28** | Accuracy | User can correct data via app |
| **S29** | Storage limitation | Retention periods defined per category |
| **S30** | Security | Technical controls listed in §4.1 |
| **S31** | DPIA | This document |
| **S32** | Data portability | Export API (planned) |
| **S33** | Right to erasure | Deletion request workflow (planned) |
| **S34** | Data breach notification | 72-hour notification to ODPC |
| **S35** | Cross-border transfer | Data residency in Kenya |

### 5.2 Registration with ODPC
- [ ] Register as data controller with the Office of the Data Protection Commissioner
- [ ] Appoint Data Protection Officer (DPO)
- [ ] Submit DPIA to ODPC for review (if processing sensitive data at scale)

---

## 6. Recommendations

### 6.1 Immediate Actions (P0)
1. **Appoint DPO** — Required under S34 of DPA for organizations processing sensitive data
2. **Register with ODPC** — Data controller registration
3. **Publish privacy policy** — Clear, accessible, in English and Swahili
4. **Implement data subject access requests** — API for users to access their data

### 6.2 Short-term Actions (P1, within 3 months)
1. **Implement right to erasure** — Workflow for data deletion requests
2. **Implement data portability** — Export user data in machine-readable format
3. **Bias audit framework** — Regular audits of credit scoring for discrimination
4. **Vendor DPAs** — Data Processing Agreements with Safaricom, LLM providers

### 6.3 Long-term Actions (P2, within 12 months)
1. **Automated breach detection** — Real-time monitoring for data exfiltration
2. **Privacy-preserving ML** — Expand federated learning to reduce data centralization
3. **Consent management platform** — Granular, auditable consent tracking
4. **Annual DPIA review** — Re-assess risks as platform scales

---

## 7. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Data Protection Officer | [TBD] | | |
| CTO | [TBD] | | |
| Legal Counsel | [TBD] | | |
| CEO | [TBD] | | |

---

## Appendix A: Data Flow Diagram

```
User Device (Android)
    │
    ├── M-Pesa SMS → Local Parse → SQLCipher DB → Sync API ──┐
    ├── Manual Input → Room DB → Sync API ────────────────────┤
    └── Voice Input → On-device ASR → Agent → Sync API ───────┘
                                                             │
                                                    ┌────────▼────────┐
                                                    │  Angavu API     │
                                                    │  (Rust/Axum)    │
                                                    │  TLS 1.3        │
                                                    │  JWT Auth       │
                                                    └────────┬────────┘
                                                             │
                              ┌──────────────────────────────┼──────────────┐
                              │                              │              │
                     ┌────────▼────────┐          ┌─────────▼──────┐  ┌───▼───┐
                     │  PostgreSQL     │          │  Redis Cache   │  │Click  │
                     │  (Encrypted)    │          │  (Rate Limits) │  │House  │
                     │  pgcrypto       │          │                │  │(OLAP) │
                     └─────────────────┘          └────────────────┘  └───────┘
```

## Appendix B: Third-Party Data Processors

| Processor | Purpose | Data Shared | DPA Status |
|-----------|---------|-------------|------------|
| Safaricom | M-Pesa payments | Transaction callbacks | 📋 Required |
| DeepSeek/Qwen | LLM inference | Anonymized business context | 📋 Required |
| Oracle Cloud | Infrastructure | All data (encrypted) | 📋 Required |
| Grafana Labs | Monitoring | Aggregated metrics only | ✅ No PII |

---

*This DPIA was prepared in accordance with Section 31 of the Kenya Data Protection Act, 2019 and the Data Protection (General) Regulations, 2021.*
