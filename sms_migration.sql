-- Alara multi-tenant SMS schema
-- PostgreSQL / Supabase
--
-- Run this script against the same database used by Django.
-- It creates the SMS tables without requiring a Django migration.
--
-- Expected existing tables:
--   schools_school
--   users_user

BEGIN;

CREATE TABLE IF NOT EXISTS messaging_smsconfiguration (
    id BIGSERIAL PRIMARY KEY,
    sender_id VARCHAR(11) NOT NULL DEFAULT '',
    sender_id_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    rejection_reason TEXT NOT NULL DEFAULT '',
    is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    school_id BIGINT NOT NULL UNIQUE
        REFERENCES schools_school(id) ON DELETE CASCADE,
    CONSTRAINT messaging_smsconfiguration_status_check
        CHECK (sender_id_status IN ('pending', 'approved', 'rejected', 'disabled'))
);

CREATE TABLE IF NOT EXISTS messaging_smsbalance (
    id BIGSERIAL PRIMARY KEY,
    credits INTEGER NOT NULL DEFAULT 0 CHECK (credits >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    school_id BIGINT NOT NULL UNIQUE
        REFERENCES schools_school(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messaging_smstemplate (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    message TEXT NOT NULL,
    category VARCHAR(30) NOT NULL DEFAULT 'custom',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    school_id BIGINT NOT NULL
        REFERENCES schools_school(id) ON DELETE CASCADE,
    created_by_id BIGINT
        REFERENCES users_user(id) ON DELETE SET NULL,
    CONSTRAINT messaging_smstemplate_category_check
        CHECK (category IN (
            'attendance', 'fees', 'results', 'announcement',
            'meeting', 'emergency', 'custom'
        )),
    CONSTRAINT messaging_unique_sms_template_name
        UNIQUE (school_id, name)
);

CREATE TABLE IF NOT EXISTS messaging_smsjob (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key VARCHAR(128),
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    recipient_count INTEGER NOT NULL DEFAULT 0 CHECK (recipient_count >= 0),
    credits_reserved INTEGER NOT NULL DEFAULT 0 CHECK (credits_reserved >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    school_id BIGINT NOT NULL
        REFERENCES schools_school(id) ON DELETE CASCADE,
    requested_by_id BIGINT
        REFERENCES users_user(id) ON DELETE SET NULL,
    CONSTRAINT messaging_smsjob_status_check
        CHECK (status IN (
            'queued', 'processing', 'completed',
            'partially_failed', 'failed'
        )),
    CONSTRAINT messaging_unique_sms_job_idempotency
        UNIQUE (school_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS messaging_smsmessage (
    id BIGSERIAL PRIMARY KEY,
    sender_id VARCHAR(11) NOT NULL,
    recipient VARCHAR(30) NOT NULL,
    message TEXT NOT NULL,
    category VARCHAR(30) NOT NULL DEFAULT 'custom',
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    provider_message_id VARCHAR(255) NOT NULL DEFAULT '',
    provider_response JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT NOT NULL DEFAULT '',
    message_parts INTEGER NOT NULL DEFAULT 1 CHECK (message_parts > 0),
    credits_used INTEGER NOT NULL DEFAULT 1 CHECK (credits_used >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at TIMESTAMPTZ,
    school_id BIGINT NOT NULL
        REFERENCES schools_school(id) ON DELETE CASCADE,
    sent_by_id BIGINT
        REFERENCES users_user(id) ON DELETE SET NULL,
    job_id BIGINT
        REFERENCES messaging_smsjob(id) ON DELETE CASCADE,
    CONSTRAINT messaging_smsmessage_status_check
        CHECK (status IN ('queued', 'sent', 'delivered', 'failed'))
);

CREATE TABLE IF NOT EXISTS messaging_smscreditledger (
    id BIGSERIAL PRIMARY KEY,
    amount INTEGER NOT NULL,
    balance_after INTEGER NOT NULL CHECK (balance_after >= 0),
    reason VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    school_id BIGINT NOT NULL
        REFERENCES schools_school(id) ON DELETE CASCADE,
    actor_id BIGINT
        REFERENCES users_user(id) ON DELETE SET NULL,
    job_id BIGINT
        REFERENCES messaging_smsjob(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS messaging_smsconfiguration_school_idx
    ON messaging_smsconfiguration (school_id);

CREATE INDEX IF NOT EXISTS messaging_smsbalance_school_idx
    ON messaging_smsbalance (school_id);

CREATE INDEX IF NOT EXISTS messaging_smstemplate_school_updated_idx
    ON messaging_smstemplate (school_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS messaging_smsjob_school_created_idx
    ON messaging_smsjob (school_id, created_at DESC);

CREATE INDEX IF NOT EXISTS messaging_smsmessage_school_created_idx
    ON messaging_smsmessage (school_id, created_at DESC);

CREATE INDEX IF NOT EXISTS messaging_smsmessage_school_status_idx
    ON messaging_smsmessage (school_id, status);

CREATE INDEX IF NOT EXISTS messaging_smsmessage_provider_id_idx
    ON messaging_smsmessage (provider_message_id);

CREATE INDEX IF NOT EXISTS messaging_smscreditledger_school_created_idx
    ON messaging_smscreditledger (school_id, created_at DESC);

-- Keep updated_at current for rows changed directly in SQL.
CREATE OR REPLACE FUNCTION messaging_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS messaging_smsconfiguration_updated_at
    ON messaging_smsconfiguration;
CREATE TRIGGER messaging_smsconfiguration_updated_at
BEFORE UPDATE ON messaging_smsconfiguration
FOR EACH ROW EXECUTE FUNCTION messaging_set_updated_at();

DROP TRIGGER IF EXISTS messaging_smsbalance_updated_at
    ON messaging_smsbalance;
CREATE TRIGGER messaging_smsbalance_updated_at
BEFORE UPDATE ON messaging_smsbalance
FOR EACH ROW EXECUTE FUNCTION messaging_set_updated_at();

DROP TRIGGER IF EXISTS messaging_smstemplate_updated_at
    ON messaging_smstemplate;
CREATE TRIGGER messaging_smstemplate_updated_at
BEFORE UPDATE ON messaging_smstemplate
FOR EACH ROW EXECUTE FUNCTION messaging_set_updated_at();

COMMIT;
