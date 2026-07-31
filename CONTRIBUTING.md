# Contributing to Angavu Intelligence Backend

Thank you for your interest in contributing to the Angavu Intelligence Backend. This document outlines the process and standards for contributing.

## 🚀 Getting Started

### Prerequisites

- **Rust 1.75+** (with `rustup`)
- **Docker 24+** and Docker Compose v2
- **PostgreSQL 16+** (or use Docker)
- **Redis 7+** (or use Docker)
- **Python 3.12+** (for LLM inference module)

### Setup

```bash
# Clone the repository
git clone https://github.com/ovalentine964/angavu-intelligence-backend.git
cd angavu-intelligence-backend

# Copy environment template
cp .env.example .env
# Edit .env with your local values

# Start infrastructure
docker compose up -d postgres redis clickhouse

# Build and run
cargo run

# Or run tests
cargo test
```

## 📋 Development Workflow

### 1. Branch Naming

```
feature/description     — New features
fix/description         — Bug fixes
refactor/description    — Code refactoring
docs/description        — Documentation
test/description        — Test additions
```

### 2. Code Standards

#### Rust

- Follow [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/)
- Use `cargo fmt` for formatting
- Use `cargo clippy` with zero warnings
- All public APIs must have doc comments
- Use `#[must_use]` where appropriate
- Prefer `Result<T, E>` over panics

#### Error Handling

```rust
// Good: Use unified ErrorResponse for all API responses
use crate::gateway::error::ErrorResponse;

// Convenience constructors:
ErrorResponse::bad_request("Missing field: cohort_hash")
ErrorResponse::unauthorized("Invalid token")
ErrorResponse::k_anonymity_violation(7, 10)  // actual_size, minimum_size
ErrorResponse::not_implemented("Feature — Coming Soon")
ErrorResponse::rate_limited(30)  // retry_after_seconds

// Bad: Generic unwrap or ad-hoc error JSON
let value = something.unwrap();
```

#### Async Code

- Use Tokio runtime consistently
- Avoid blocking calls in async contexts
- Use `tokio::spawn` for independent tasks
- Use `tokio::select!` for concurrent operations

### 3. Testing

```bash
# All tests
cargo test

# Specific module
cargo test intelligence::credit_score

# Integration tests (requires Docker)
docker compose up -d
cargo test --test integration

# With logging
RUST_LOG=debug cargo test -- --nocapture
```

**Test requirements for PRs:**
- All existing tests must pass
- New features require unit tests
- API changes require integration tests
- Use `cargo clippy -- -D warnings` (zero warnings)
- Use `cargo audit` for dependency vulnerabilities

### 4. Commit Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add credit scoring engine
fix: race condition in sync handler
perf: optimize ClickHouse query for heat maps
refactor: extract crypto module
docs: add API endpoint documentation
test: add integration tests for market research
chore: update dependencies
```

### 5. Pull Request Process

1. **Create branch** from `main`
2. **Make changes** following code standards
3. **Write tests** for new functionality
4. **Update docs** if API changes
5. **Run full check**:
   ```bash
   cargo fmt --check
   cargo clippy -- -D warnings
   cargo test
   cargo audit
   ```
6. **Open PR** with description of changes
7. **Address review** feedback
8. **Merge** after approval

## 🏗️ Architecture Guidelines

### Module Structure

The backend is organized into these key modules:

```
rust-api/src/
├── gateway/        — API routing, auth, rate limiting, error handling, audit, CORS
│   ├── mod.rs          — Gateway router builder
│   ├── error.rs        — Unified ErrorResponse struct
│   ├── tools_impl.rs   — Implemented tool endpoints
│   ├── human_approval.rs — Approval workflow
│   ├── graph_sync.rs   — Device↔server graph sync
│   └── audit.rs        — Persistent audit logging
├── graph/          — Knowledge graph (in-memory, PostgreSQL, unified)
│   ├── unified_graph.rs — UnifiedKnowledgeLayer bridging 3 graphs
│   ├── pg_knowledge_graph.rs — PostgreSQL-backed graph
│   └── algorithms.rs   — PageRank, community detection, betweenness, k-core, shortest path
├── loops/          — OODA loop implementations (fast/medium/slow/deep)
│   ├── ooda_loop.rs    — Full DB-backed OODA with OTel spans
│   └── circuit_breaker.rs — Canonical circuit breaker (single source of truth)
├── credit/         — Credit scoring, federated learning, seasonality
├── statistical/    — Differential privacy (Laplace mechanism)
├── observability/  — SLO tracking, metrics
├── llm/            — LLM inference (uses canonical CircuitBreaker via async wrapper)
├── health/         — Insurance, occupation hazards
├── orchestrator/   — OODA orchestrator, economic analyzer
├── webhook/        — M-Pesa, market, generic webhook handlers
└── routes/         — Trace analysis, additional routes
```

### Adding a New Revenue Engine

1. Create module in `src/intelligence/`:
   ```rust
   // src/intelligence/new_engine.rs
   pub struct NewEngine { /* ... */ }
   
   impl NewEngine {
       pub async fn analyze(&self, params: Params) -> Result<Analysis> {
           // Implementation
       }
   }
   ```

2. Register in `src/intelligence/mod.rs`
3. Add API route in `src/api/v1/intelligence.rs`
4. Add tests in `tests/intelligence/`
5. Update API documentation

### Adding a New API Endpoint

1. Define route in `src/api/v1/`
2. Add request/response models in `src/models/`
3. Implement handler with proper error handling
4. Add authentication middleware if needed
5. Add rate limiting configuration
6. Write integration tests

### Database Migrations

```bash
# Create migration
sqlx migrate add description

# Run migrations
sqlx migrate run

# Revert
sqlx migrate revert
```

## 🐛 Bug Reports

Use the [Issue Tracker](../../issues/new) with:

1. **Description** — Clear description of the bug
2. **Steps to reproduce** — Numbered steps
3. **Expected behavior** — What should happen
4. **Actual behavior** — What happens instead
5. **Environment** — OS, Rust version, Docker version
6. **Logs** — Relevant error messages

## 💡 Feature Requests

1. **Problem** — What problem does this solve?
2. **Proposed solution** — Your idea
3. **Alternatives** — Other approaches
4. **Impact** — Who benefits?

## 📜 Code of Conduct

Please follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## 📄 License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).

## 🙏 Thank You

Your contributions help build intelligence infrastructure for Africa's informal economy. Thank you for being part of this mission.
