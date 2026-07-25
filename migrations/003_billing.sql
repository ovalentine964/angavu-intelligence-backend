-- Billing schema for Angavu Intelligence
-- Run: psql -d angavu -f migrations/003_billing.sql

-- Invoice number sequence
CREATE SEQUENCE IF NOT EXISTS invoice_number_seq START 1;

-- ── Subscriptions ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS subscriptions (
    id                  UUID PRIMARY KEY,
    org_id              UUID NOT NULL,
    tier                TEXT NOT NULL DEFAULT 'free'
                            CHECK (tier IN ('free', 'starter', 'pro', 'enterprise')),
    status              TEXT NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'trialing', 'past_due', 'canceled', 'paused')),
    current_period_start TIMESTAMPTZ NOT NULL,
    current_period_end   TIMESTAMPTZ NOT NULL,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT false,
    trial_end           TIMESTAMPTZ,
    custom_price_cents  BIGINT,
    custom_query_limit  BIGINT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_subscriptions_org ON subscriptions(org_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);

-- ── API Keys ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS api_keys (
    id                UUID PRIMARY KEY,
    org_id            UUID NOT NULL,
    subscription_id   UUID NOT NULL REFERENCES subscriptions(id),
    key_prefix        TEXT NOT NULL UNIQUE,
    key_hash          TEXT NOT NULL,
    name              TEXT NOT NULL,
    scopes            TEXT[] NOT NULL DEFAULT '{}',
    is_active         BOOLEAN NOT NULL DEFAULT true,
    last_used_at      TIMESTAMPTZ,
    expires_at        TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_api_keys_org ON api_keys(org_id);
CREATE INDEX idx_api_keys_prefix ON api_keys(key_prefix);
CREATE INDEX idx_api_keys_subscription ON api_keys(subscription_id);

-- ── Usage Records ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS usage_records (
    id                    UUID PRIMARY KEY,
    org_id                UUID NOT NULL,
    subscription_id       UUID NOT NULL REFERENCES subscriptions(id),
    api_key_id            UUID REFERENCES api_keys(id),
    metric                TEXT NOT NULL
                              CHECK (metric IN ('query', 'report', 'data_export', 'streaming_minute', 'credit_score')),
    quantity              BIGINT NOT NULL DEFAULT 1,
    unit_cost_cents       BIGINT NOT NULL DEFAULT 0,
    total_cost_cents      BIGINT NOT NULL DEFAULT 0,
    endpoint              TEXT,
    metadata              JSONB NOT NULL DEFAULT '{}',
    recorded_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    billing_period_start  TIMESTAMPTZ NOT NULL,
    billing_period_end    TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_usage_org_metric ON usage_records(org_id, metric);
CREATE INDEX idx_usage_period ON usage_records(billing_period_start, billing_period_end);
CREATE INDEX idx_usage_subscription ON usage_records(subscription_id);

-- ── Invoices ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS invoices (
    id                  UUID PRIMARY KEY,
    org_id              UUID NOT NULL,
    subscription_id     UUID NOT NULL REFERENCES subscriptions(id),
    invoice_number      TEXT NOT NULL UNIQUE,
    status              TEXT NOT NULL DEFAULT 'draft'
                            CHECK (status IN ('draft', 'finalized', 'paid', 'void', 'overdue')),
    currency            TEXT NOT NULL DEFAULT 'USD',
    subtotal_cents      BIGINT NOT NULL DEFAULT 0,
    tax_cents           BIGINT NOT NULL DEFAULT 0,
    total_cents         BIGINT NOT NULL DEFAULT 0,
    period_start        TIMESTAMPTZ NOT NULL,
    period_end          TIMESTAMPTZ NOT NULL,
    due_date            TIMESTAMPTZ NOT NULL,
    paid_at             TIMESTAMPTZ,
    line_items          JSONB NOT NULL DEFAULT '[]',
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_invoices_org ON invoices(org_id);
CREATE INDEX idx_invoices_subscription ON invoices(subscription_id);
CREATE INDEX idx_invoices_status ON invoices(status);
CREATE UNIQUE INDEX idx_invoices_number ON invoices(invoice_number);

-- ── Seed a free-tier subscription for existing orgs (optional) ─────────
-- INSERT INTO subscriptions (id, org_id, tier, status, current_period_start, current_period_end)
-- SELECT gen_random_uuid(), id, 'free', 'active', now(), now() + interval '30 days'
-- FROM organizations
-- WHERE id NOT IN (SELECT org_id FROM subscriptions);
