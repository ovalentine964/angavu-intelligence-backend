-- Webhook Events Table Migration
-- Stores all incoming webhook events for audit trail, replay, and debugging.

CREATE TABLE IF NOT EXISTS webhook_events (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(64) UNIQUE NOT NULL,
    source VARCHAR(32) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    validated BOOLEAN NOT NULL DEFAULT FALSE,
    processed BOOLEAN NOT NULL DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_source ON webhook_events(source);
CREATE INDEX IF NOT EXISTS idx_webhook_events_type ON webhook_events(event_type);
CREATE INDEX IF NOT EXISTS idx_webhook_events_received ON webhook_events(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_webhook_events_processed ON webhook_events(processed) WHERE NOT processed;

-- M-Pesa Transaction Reconciliation Table
-- Tracks matched/unmatched M-Pesa payments against business records.
CREATE TABLE IF NOT EXISTS mpesa_reconciliation (
    id BIGSERIAL PRIMARY KEY,
    webhook_event_id VARCHAR(64) REFERENCES webhook_events(event_id),
    mpesa_receipt VARCHAR(32) UNIQUE NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    phone VARCHAR(20),
    counterparty_name VARCHAR(128),
    transaction_type VARCHAR(32) NOT NULL,
    business_record_type VARCHAR(32),  -- 'sale', 'expense', 'debt_payment', NULL
    business_record_id BIGINT,
    matched_at TIMESTAMPTZ,
    confidence DECIMAL(3,2) DEFAULT 0.0,
    status VARCHAR(16) DEFAULT 'unmatched',  -- 'matched', 'unmatched', 'manual_review'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mpesa_recon_receipt ON mpesa_reconciliation(mpesa_receipt);
CREATE INDEX IF NOT EXISTS idx_mpesa_recon_status ON mpesa_reconciliation(status);
CREATE INDEX IF NOT EXISTS idx_mpesa_recon_phone ON mpesa_reconciliation(phone);

COMMENT ON TABLE webhook_events IS 'Audit trail of all incoming webhook events from M-Pesa, market feeds, and external integrations';
COMMENT ON TABLE mpesa_reconciliation IS 'Auto-reconciliation of M-Pesa SMS/callbacks with business records (sales, expenses, debt payments)';
