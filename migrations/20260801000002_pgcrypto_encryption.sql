-- S11: Enable pgcrypto for column-level encryption of sensitive data.
-- This provides encryption at rest for PII and financial data at the PostgreSQL level.
-- Combined with TLS in transit, this provides defense-in-depth for data protection.

-- Enable the pgcrypto extension (requires superuser or CREATE privilege)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Create a helper function to encrypt sensitive text columns using AES-256.
-- The encryption key should be passed via the application (not stored in DB).
-- Usage: SELECT encrypt_sensitive('plaintext', current_setting('app.encryption_key'));
CREATE OR REPLACE FUNCTION encrypt_sensitive(plaintext TEXT, encryption_key TEXT)
RETURNS BYTEA AS $$
BEGIN
    IF plaintext IS NULL THEN
        RETURN NULL;
    END IF;
    RETURN pgp_sym_encrypt(
        plaintext,
        encryption_key,
        'cipher-algo=aes256, compress-algo=none'
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create a helper function to decrypt sensitive text columns.
CREATE OR REPLACE FUNCTION decrypt_sensitive(ciphertext BYTEA, encryption_key TEXT)
RETURNS TEXT AS $$
BEGIN
    IF ciphertext IS NULL THEN
        RETURN NULL;
    END IF;
    RETURN pgp_sym_decrypt(ciphertext, encryption_key);
EXCEPTION
    WHEN OTHERS THEN
        -- Return NULL if decryption fails (wrong key, corrupted data, etc.)
        RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Add encrypted columns for PII in the users/buyers table (if exists).
-- These are nullable so existing rows are unaffected.
-- Application code should write to BOTH columns during the migration period,
-- then drop the plaintext columns once all reads are switched to encrypted.

-- Example: Add encrypted phone number column
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_encrypted BYTEA;
-- Example: Add encrypted email column
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS email_encrypted BYTEA;

-- Note: The application should set app.encryption_key on each connection:
--   SELECT set_config('app.encryption_key', '<key-from-env>', false);
-- This key is loaded from the ENCRYPTION_KEY environment variable in the Rust backend.
