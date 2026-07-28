-- =============================================================================
-- Staging Seed Data — Test users, sample transactions, credit scores
-- =============================================================================

-- Test users (passwords are all 'staging123' hashed with Argon2)
INSERT INTO users (id, email, phone, password_hash, role, created_at, updated_at) VALUES
    ('00000000-0000-0000-0000-000000000001', 'admin@angavu.test', '+254700000001', '$argon2id$v=19$m=4096,t=3,p=1$c2FsdHNhbHRzYWx0$placeholder', 'admin', NOW(), NOW()),
    ('00000000-0000-0000-0000-000000000002', 'merchant@angavu.test', '+254700000002', '$argon2id$v=19$m=4096,t=3,p=1$c2FsdHNhbHRzYWx0$placeholder', 'merchant', NOW(), NOW()),
    ('00000000-0000-0000-0000-000000000003', 'worker@angavu.test', '+254700000003', '$argon2id$v=19$m=4096,t=3,p=1$c2FsdHNhbHRzYWx0$placeholder', 'worker', NOW(), NOW()),
    ('00000000-0000-0000-0000-000000000004', 'analyst@angavu.test', '+254700000004', '$argon2id$v=19$m=4096,t=3,p=1$c2FsdHNhbHRzYWx0$placeholder', 'analyst', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

-- Sample worker profiles
INSERT INTO worker_profiles (id, user_id, worker_type, occupation, region, created_at) VALUES
    ('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000003', 'boda_boda', 'Motorcycle taxi', 'Nairobi', NOW()),
    ('10000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000002', 'mama_mboga', 'Greengrocer', 'Mombasa', NOW())
ON CONFLICT (id) DO NOTHING;

-- Sample M-Pesa transactions (last 90 days)
INSERT INTO mpesa_transactions (id, worker_id, amount, transaction_type, timestamp, created_at)
SELECT
    gen_random_uuid(),
    '10000000-0000-0000-0000-000000000001',
    (random() * 5000 + 100)::numeric(12,2),
    CASE WHEN random() > 0.3 THEN 'receive' ELSE 'send' END,
    NOW() - (random() * interval '90 days'),
    NOW()
FROM generate_series(1, 200);

INSERT INTO mpesa_transactions (id, worker_id, amount, transaction_type, timestamp, created_at)
SELECT
    gen_random_uuid(),
    '10000000-0000-0000-0000-000000000002',
    (random() * 3000 + 50)::numeric(12,2),
    CASE WHEN random() > 0.4 THEN 'receive' ELSE 'send' END,
    NOW() - (random() * interval '90 days'),
    NOW()
FROM generate_series(1, 150);

-- Sample credit scores
INSERT INTO credit_scores (id, worker_id, alama_score, probability_default, confidence, model_version, created_at) VALUES
    ('20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 680, 0.12, 0.85, 'v1.0-staging', NOW()),
    ('20000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 720, 0.08, 0.90, 'v1.0-staging', NOW())
ON CONFLICT (id) DO NOTHING;

-- Staging marker
INSERT INTO system_config (key, value, created_at) VALUES
    ('environment', '"staging"', NOW()),
    ('seed_version', '"1.0.0"', NOW()),
    ('seeded_at', to_jsonb(NOW()::text), NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, created_at = NOW();
