# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | ✅ Active support  |
| < 1.0   | ❌ No longer supported |

## Reporting a Vulnerability

We take security extremely seriously given the sensitive financial and economic data this platform processes.

### How to Report

**DO NOT** open a public GitHub issue for security vulnerabilities.

Instead, please email: **[INSERT SECURITY EMAIL]**

Include:

1. **Description** — Clear description of the vulnerability
2. **Impact** — Potential data exposure or system compromise
3. **Reproduction** — Step-by-step reproduction steps
4. **Affected components** — Which services/modules are affected
5. **Suggested fix** — If you have one (optional)

### Response Timeline

- **Acknowledgment**: Within 24 hours
- **Initial assessment**: Within 48 hours
- **Fix deployment**:
  - 🔴 Critical (data breach, RCE): Within 24 hours
  - 🟠 High (auth bypass, data leak): Within 72 hours
  - 🟡 Medium (information disclosure): Within 1 week
  - 🟢 Low (minor issues): Next release cycle

## Scope

### In Scope

- **Authentication & Authorization** — JWT bypass, privilege escalation
- **Cryptography** — AES-256-GCM, ML-KEM-768, Ed25519 implementation flaws
- **Database** — SQL injection, data leakage, encryption bypass
- **API Security** — Injection attacks, rate limiting bypass, data exposure
- **Privacy** — k-anonymity violations, differential privacy failures, PII exposure
- **Infrastructure** — Container escape, supply chain attacks
- **WebSocket** — Authentication bypass, message injection

### Out of Scope

- Denial of service (rate limiting is expected behavior)
- Social engineering
- Physical access to servers
- Third-party services (DeepSeek, Qwen APIs)

## Security Architecture

### Defense in Depth

1. **Network** — Nginx with TLS 1.2/1.3, rate limiting
2. **Application** — Axum middleware, input validation
3. **Authentication** — JWT with RS256, short-lived tokens
4. **Encryption** — AES-256-GCM at rest, TLS in transit
5. **Privacy** — k-anonymity (k≥10), differential privacy (ε=0.1)
6. **PQC** — Post-quantum ready (ML-KEM-768)

### Data Protection

- **PII is never stored** — All personal data is anonymized before storage
- **Encryption at rest** — AES-256-GCM for all sensitive data
- **Encryption in transit** — TLS 1.2/1.3 for all connections
- **Key management** — Keys stored in environment variables, never in code
- **Audit logging** — All data access is logged

## Safe Harbor

We support responsible disclosure and will not take legal action against researchers who:

- Make a good faith effort to avoid privacy violations and data destruction
- Only interact with their own test accounts
- Do not exploit vulnerabilities beyond what is necessary to confirm them
- Report vulnerabilities promptly
- Do not publicly disclose vulnerabilities before a fix is available

## Security Best Practices for Contributors

- Never commit secrets, API keys, or credentials
- Use parameterized queries (sqlx) — never raw SQL
- Validate all inputs at API boundaries
- Use `cargo audit` to check for dependency vulnerabilities
- Follow the principle of least privilege
- Use `secrecy` crate for sensitive values in memory
- Test with `RUST_LOG=debug` to verify no sensitive data is logged

## Acknowledgments

We thank security researchers who help protect the financial data and privacy of millions of informal economy participants across Africa.
