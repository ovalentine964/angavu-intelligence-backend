# Changelog

All notable changes to Biashara Intelligence Backend will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-02

### Added
- **15 Intelligence Products** — Soko Pulse, Biashara Pulse, Alama Score, Jamii Insights, Tax Base, Distribution Gap, GDP Estimator, Inflation Tracker, Employment Monitor, Insurance Risk, Market Entry, SDG Tracker, Gender Intelligence, Supply Chain, Research Data
- **Multi-Agent Runtime** — Agent lifecycle management, health monitoring, orchestration
- **Event Bus** — Pub/sub message passing between agents with dead letter queue
- **Agent Observability** — Metrics, tracing, and health checks for all 33 agents
- **FMCG Intelligence Service** — Informal channel tracking for Pwani Oil pilot
- **Loan Intelligence Service** — Loan tracking and credit readiness scoring
- **Giving Insights Service** — Tithe and charitable giving analytics
- **Data Center Roadmap** — 4-phase infrastructure scaling based on worker value
- **Worker Value Metrics** — Track data value generated per worker
- **Outcome-Based Pricing** — Pay-for-results intelligence product pricing
- **Formal Reports** — Bank, government, insurance presentable reports
- **Phase 1 Intelligence APIs** — GDP, inflation, employment endpoints
- **Federated Learning** — Privacy-preserving model aggregation
- **ClickHouse Integration** — OLAP queries on 600M+ records
- **Polars Data Processing** — High-performance DataFrame operations

### Fixed
- **Path traversal vulnerability** — Secured file access endpoints
- **Async I/O** — Proper async handling for all database operations
- **Input validation** — Comprehensive validation on all API endpoints

### Changed
- **Tech stack upgrade** — Added Polars for data processing, ClickHouse for analytics
- **Version set to 0.1.0** — Consistent across all repos until real users

### Technical
- Python 3.12 + FastAPI
- PostgreSQL 15 (production) / SQLite (development)
- Redis for caching, rate limiting, session management
- Celery for background task processing
- Docker + Docker Compose deployment
- Nginx reverse proxy with SSL termination
- structlog for structured logging
- Sentry for error tracking

## [Unreleased]

### Added
- WhatsApp integration (OpenWA)
- Voice transcription via Whisper STT
- Worker report system (daily, weekly, monthly, 6-month, yearly)
- Buyer report system (12 segments, all frequencies)
- Degree integration mapping (42 units)
- Statistical foundation (EWMA, ARIMA, VAR, cointegration)
- Non-parametric methods (KDE, bootstrap, LOESS)
- Training loop infrastructure
- NVIDIA NIM client for cloud LLM endpoints
- Self-evolution infrastructure
- Scalability Tier 1→2 (connection pooling, Redis cache, task queue)

### Fixed
- Docker-compose configuration
- WhatsApp integration issues
