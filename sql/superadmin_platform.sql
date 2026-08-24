-- ============================================================
-- SUPER ADMIN PLATFORM SCHEMA
-- Tables backing the 18 super-admin modules:
--   RBAC roles, audit logs, impersonation, support tickets,
--   feature flags, system settings, notification campaigns,
--   API keys/webhooks, security events/sessions, storage quotas,
--   moderation reports, coupons/invoices/refunds, monitoring.
--
-- Run in Supabase SQL Editor (or psql). Idempotent (IF NOT EXISTS).
-- ============================================================

-- ------------------------------------------------------------
-- 1. ROLES & PERMISSIONS (configurable internal platform roles)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS platform_role (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(50) NOT NULL UNIQUE,   -- super_admin | support_staff | finance_staff | sales_staff | moderator | technical_staff | custom...
    display_name    VARCHAR(100) NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    permissions     JSONB NOT NULL DEFAULT '[]',   -- list of permission codes
    is_system       BOOLEAN NOT NULL DEFAULT FALSE, -- system roles cannot be deleted
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO platform_role (name, display_name, description, permissions, is_system)
VALUES
  ('super_admin',     'Super Admin',     'Full platform access',        '["*"]', TRUE),
  ('support_staff',   'Support Staff',   'Support center + impersonation', '["support.manage","users.view","schools.view","impersonate.use","audit.view"]', TRUE),
  ('finance_staff',   'Finance Staff',   'Payments and subscriptions',  '["payments.manage","subscriptions.manage","reports.finance","audit.view"]', TRUE),
  ('sales_staff',     'Sales Staff',     'Schools and plans',           '["schools.manage","plans.manage","reports.sales","audit.view"]', TRUE),
  ('moderator',       'Moderator',       'Content moderation',          '["moderation.manage","users.suspend","audit.view"]', TRUE),
  ('technical_staff', 'Technical Staff', 'Monitoring and integrations', '["monitoring.view","integrations.manage","flags.manage","settings.manage","audit.view"]', TRUE)
ON CONFLICT (name) DO NOTHING;

-- Assignment of a platform role to a user (users_user.id)
CREATE TABLE IF NOT EXISTS platform_user_role (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    role_id         BIGINT NOT NULL REFERENCES platform_role(id) ON DELETE CASCADE,
    assigned_by_id  BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_platform_user_role UNIQUE (user_id, role_id)
);

-- ------------------------------------------------------------
-- 2. AUDIT LOGS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    actor_id        BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    actor_name      VARCHAR(150) NOT NULL DEFAULT '',
    action          VARCHAR(100) NOT NULL,          -- e.g. school.suspend, user.role_change, auth.login
    target_type     VARCHAR(100) NOT NULL DEFAULT '',
    target_id       VARCHAR(100) NOT NULL DEFAULT '',
    target_label    VARCHAR(255) NOT NULL DEFAULT '',
    changes         JSONB NOT NULL DEFAULT '{}',    -- {field: {before, after}}
    ip_address      VARCHAR(64) NOT NULL DEFAULT '',
    user_agent      TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON audit_log(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_target ON audit_log(target_type, target_id);

-- ------------------------------------------------------------
-- 3. IMPERSONATION SESSIONS (super admin acts as a school admin)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS impersonation_session (
    id                  BIGSERIAL PRIMARY KEY,
    super_admin_id      BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    target_user_id      BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    reason              TEXT NOT NULL DEFAULT '',
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at            TIMESTAMPTZ DEFAULT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    ip_address          VARCHAR(64) NOT NULL DEFAULT '',
    user_agent          TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_impersonation_active ON impersonation_session(is_active);

-- ------------------------------------------------------------
-- 4. SUPPORT CENTER
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS support_ticket (
    id              BIGSERIAL PRIMARY KEY,
    reference       VARCHAR(20) NOT NULL UNIQUE,     -- e.g. TCK-000123
    requester_id    BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    requester_name  VARCHAR(150) NOT NULL DEFAULT '',
    school_id       BIGINT DEFAULT NULL REFERENCES schools_school(id) ON DELETE SET NULL,
    kind            VARCHAR(30) NOT NULL DEFAULT 'bug', -- bug | feature_request | question | feedback
    subject         VARCHAR(255) NOT NULL,
    body            TEXT NOT NULL DEFAULT '',
    status          VARCHAR(20) NOT NULL DEFAULT 'open',   -- open | in_progress | waiting | resolved | closed
    priority        VARCHAR(10) NOT NULL DEFAULT 'medium', -- low | medium | high | urgent
    assignee_id     BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    internal_notes  TEXT NOT NULL DEFAULT '',
    resolved_at     TIMESTAMPTZ DEFAULT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_support_ticket_status ON support_ticket(status, priority);

CREATE TABLE IF NOT EXISTS support_ticket_comment (
    id              BIGSERIAL PRIMARY KEY,
    ticket_id       BIGINT NOT NULL REFERENCES support_ticket(id) ON DELETE CASCADE,
    author_id       BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    author_name     VARCHAR(150) NOT NULL DEFAULT '',
    body            TEXT NOT NULL,
    is_internal     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_support_comment_ticket ON support_ticket_comment(ticket_id);

-- ------------------------------------------------------------
-- 5. FEATURE FLAGS (global / per school / per plan)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feature_flag (
    id              BIGSERIAL PRIMARY KEY,
    key             VARCHAR(100) NOT NULL,           -- ai_assistant | feed | online_classes | cbt_exams | library | hostel | attendance | messaging ...
    name            VARCHAR(150) NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    scope           VARCHAR(10) NOT NULL DEFAULT 'global', -- global | school | plan
    school_id       BIGINT DEFAULT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    plan_name       VARCHAR(50) DEFAULT NULL,        -- matches schools_plan.name when scope=plan
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    rollout_percent INTEGER NOT NULL DEFAULT 100 CHECK (rollout_percent BETWEEN 0 AND 100),
    updated_by_id   BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_feature_flag_scope UNIQUE (key, scope, school_id, plan_name)
);

-- ------------------------------------------------------------
-- 6. SYSTEM SETTINGS (sensitive values flagged; never serialized back)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_setting (
    id              BIGSERIAL PRIMARY KEY,
    key             VARCHAR(100) NOT NULL UNIQUE,    -- branding.logo_url | email.smtp_host | sms.provider | payments.paystack_secret ...
    category        VARCHAR(50) NOT NULL DEFAULT 'general', -- branding | email | sms | push | payments | storage | ai | security | general
    value           JSONB NOT NULL DEFAULT '{}',
    is_secret       BOOLEAN NOT NULL DEFAULT FALSE,  -- write-only: API returns "••••••••"
    description     VARCHAR(255) NOT NULL DEFAULT '',
    updated_by_id   BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 7. NOTIFICATION CAMPAIGNS (push / email / SMS blasts)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notification_campaign (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    channels        JSONB NOT NULL DEFAULT '[]',     -- ["push","email","sms"]
    audience_type   VARCHAR(20) NOT NULL DEFAULT 'all', -- all | school | role | users | plan
    audience_filter JSONB NOT NULL DEFAULT '{}',     -- {school_ids:[], roles:[], user_ids:[], plan:"professional"}
    title           VARCHAR(255) NOT NULL,
    body            TEXT NOT NULL DEFAULT '',
    status          VARCHAR(15) NOT NULL DEFAULT 'draft', -- draft | scheduled | sending | sent | failed
    scheduled_at    TIMESTAMPTZ DEFAULT NULL,
    sent_at         TIMESTAMPTZ DEFAULT NULL,
    recipient_count INTEGER NOT NULL DEFAULT 0,
    delivered_count INTEGER NOT NULL DEFAULT 0,
    failed_count    INTEGER NOT NULL DEFAULT 0,
    created_by_id   BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_campaign_status ON notification_campaign(status, scheduled_at);

-- ------------------------------------------------------------
-- 8. API KEYS & WEBHOOKS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_key (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(150) NOT NULL,
    prefix          VARCHAR(12) NOT NULL,            -- visible identifier e.g. ala_live_ab12
    hashed_key      VARCHAR(255) NOT NULL,           -- sha256 of full key; raw shown once at creation
    scopes          JSONB NOT NULL DEFAULT '[]',
    rate_limit_per_min INTEGER NOT NULL DEFAULT 60,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_used_at    TIMESTAMPTZ DEFAULT NULL,
    expires_at      TIMESTAMPTZ DEFAULT NULL,
    created_by_id   BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS webhook (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(150) NOT NULL,
    url             TEXT NOT NULL,
    events          JSONB NOT NULL DEFAULT '[]',     -- ["school.created","subscription.renewed",...]
    secret          VARCHAR(255) NOT NULL DEFAULT '',-- HMAC signing secret
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_status     INTEGER DEFAULT NULL,
    last_delivery_at TIMESTAMPTZ DEFAULT NULL,
    failure_count   INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_usage_log (
    id              BIGSERIAL PRIMARY KEY,
    api_key_id      BIGINT DEFAULT NULL REFERENCES api_key(id) ON DELETE CASCADE,
    method          VARCHAR(10) NOT NULL DEFAULT '',
    path            TEXT NOT NULL DEFAULT '',
    status_code     INTEGER NOT NULL DEFAULT 0,
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    ip_address      VARCHAR(64) NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_api_usage_created ON api_usage_log(created_at DESC);

-- ------------------------------------------------------------
-- 9. SECURITY CENTER
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS security_event (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    event_type      VARCHAR(50) NOT NULL,            -- login_success | login_failed | password_changed | lockout | suspicious_login | 2fa_enabled ...
    ip_address      VARCHAR(64) NOT NULL DEFAULT '',
    user_agent      TEXT NOT NULL DEFAULT '',
    details         JSONB NOT NULL DEFAULT '{}',
    severity        VARCHAR(10) NOT NULL DEFAULT 'info', -- info | warning | critical
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_security_event_user ON security_event(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_event_type ON security_event(event_type);

CREATE TABLE IF NOT EXISTS user_session (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    session_key     VARCHAR(128) NOT NULL UNIQUE,
    device          VARCHAR(255) NOT NULL DEFAULT '',
    browser         VARCHAR(100) NOT NULL DEFAULT '',
    os              VARCHAR(100) NOT NULL DEFAULT '',
    ip_address      VARCHAR(64) NOT NULL DEFAULT '',
    location        VARCHAR(150) NOT NULL DEFAULT '',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_activity   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_user_session_user ON user_session(user_id, is_active);

-- Account lockout state (separate from User.is_active so admins can unlock)
CREATE TABLE IF NOT EXISTS account_lockout (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    locked_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    locked_until    TIMESTAMPTZ DEFAULT NULL,
    reason          VARCHAR(255) NOT NULL DEFAULT '',
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    released_by_id  BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    released_at     TIMESTAMPTZ DEFAULT NULL,
    is_locked       BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_account_lockout_user ON account_lockout(user_id, is_locked);

-- ------------------------------------------------------------
-- 10. STORAGE MANAGEMENT
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS storage_quota (
    id              BIGSERIAL PRIMARY KEY,
    school_id       BIGINT NOT NULL UNIQUE REFERENCES schools_school(id) ON DELETE CASCADE,
    quota_mb        BIGINT NOT NULL DEFAULT 5120,    -- default 5 GB
    used_mb         BIGINT NOT NULL DEFAULT 0,
    videos_mb       BIGINT NOT NULL DEFAULT 0,
    images_mb       BIGINT NOT NULL DEFAULT 0,
    documents_mb    BIGINT NOT NULL DEFAULT 0,
    backups_mb      BIGINT NOT NULL DEFAULT 0,
    computed_at     TIMESTAMPTZ DEFAULT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 11. CONTENT MODERATION
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS moderation_report (
    id              BIGSERIAL PRIMARY KEY,
    reporter_id     BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    content_type    VARCHAR(50) NOT NULL,            -- video | image | document | post | comment
    content_id      BIGINT NOT NULL DEFAULT 0,
    content_url     TEXT NOT NULL DEFAULT '',
    content_preview TEXT NOT NULL DEFAULT '',
    uploader_id     BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    school_id       BIGINT DEFAULT NULL REFERENCES schools_school(id) ON DELETE SET NULL,
    reason          VARCHAR(50) NOT NULL DEFAULT 'inappropriate', -- inappropriate | copyright | spam | violence | other
    details         TEXT NOT NULL DEFAULT '',
    status          VARCHAR(15) NOT NULL DEFAULT 'pending', -- pending | reviewing | actioned | dismissed
    action_taken    VARCHAR(50) NOT NULL DEFAULT '', -- removed | uploader_suspended | warning_issued | none
    reviewed_by_id  BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    reviewed_at     TIMESTAMPTZ DEFAULT NULL,
    review_notes    TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_moderation_status ON moderation_report(status, created_at DESC);

-- ------------------------------------------------------------
-- 12. COUPONS / INVOICES / REFUNDS (finance extensions)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS coupon (
    id              BIGSERIAL PRIMARY KEY,
    code            VARCHAR(40) NOT NULL UNIQUE,
    description     VARCHAR(255) NOT NULL DEFAULT '',
    discount_type   VARCHAR(10) NOT NULL DEFAULT 'percent', -- percent | fixed
    discount_value  NUMERIC(10,2) NOT NULL DEFAULT 0,
    max_redemptions INTEGER NOT NULL DEFAULT 0,      -- 0 = unlimited
    redemption_count INTEGER NOT NULL DEFAULT 0,
    applies_to_plan VARCHAR(50) DEFAULT NULL,
    valid_from      TIMESTAMPTZ DEFAULT NULL,
    valid_until     TIMESTAMPTZ DEFAULT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS invoice (
    id              BIGSERIAL PRIMARY KEY,
    number          VARCHAR(30) NOT NULL UNIQUE,     -- INV-2026-000001
    school_id       BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    subscription_id BIGINT DEFAULT NULL,             -- no hard FK to allow history retention
    amount_due      NUMERIC(12,2) NOT NULL DEFAULT 0,
    amount_paid     NUMERIC(12,2) NOT NULL DEFAULT 0,
    currency        VARCHAR(8) NOT NULL DEFAULT 'GHS',
    status          VARCHAR(15) NOT NULL DEFAULT 'open', -- open | paid | void | refunded
    period_start    DATE DEFAULT NULL,
    period_end      DATE DEFAULT NULL,
    due_date        DATE DEFAULT NULL,
    line_items      JSONB NOT NULL DEFAULT '[]',
    pdf_url         TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_invoice_school ON invoice(school_id, status);

CREATE TABLE IF NOT EXISTS refund (
    id              BIGSERIAL PRIMARY KEY,
    transaction_ref VARCHAR(100) NOT NULL DEFAULT '',
    invoice_id      BIGINT DEFAULT NULL REFERENCES invoice(id) ON DELETE SET NULL,
    school_id       BIGINT DEFAULT NULL REFERENCES schools_school(id) ON DELETE SET NULL,
    amount          NUMERIC(12,2) NOT NULL DEFAULT 0,
    currency        VARCHAR(8) NOT NULL DEFAULT 'GHS',
    reason          TEXT NOT NULL DEFAULT '',
    status          VARCHAR(15) NOT NULL DEFAULT 'pending', -- pending | processed | rejected
    processed_by_id BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    processed_at    TIMESTAMPTZ DEFAULT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 13. SYSTEM MONITORING SNAPSHOTS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monitoring_snapshot (
    id              BIGSERIAL PRIMARY KEY,
    component       VARCHAR(50) NOT NULL,            -- api | database | celery | email | push | storage
    status          VARCHAR(15) NOT NULL DEFAULT 'healthy', -- healthy | degraded | down
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    error_rate      NUMERIC(5,2) NOT NULL DEFAULT 0,
    details         JSONB NOT NULL DEFAULT '{}',
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_monitoring_recorded ON monitoring_snapshot(recorded_at DESC);

-- ------------------------------------------------------------
-- 14. updated_at triggers
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_platform_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_platform_role_updated ON platform_role;
CREATE TRIGGER trg_platform_role_updated BEFORE UPDATE ON platform_role
FOR EACH ROW EXECUTE FUNCTION update_platform_updated_at();

DROP TRIGGER IF EXISTS trg_support_ticket_updated ON support_ticket;
CREATE TRIGGER trg_support_ticket_updated BEFORE UPDATE ON support_ticket
FOR EACH ROW EXECUTE FUNCTION update_platform_updated_at();

DROP TRIGGER IF EXISTS trg_feature_flag_updated ON feature_flag;
CREATE TRIGGER trg_feature_flag_updated BEFORE UPDATE ON feature_flag
FOR EACH ROW EXECUTE FUNCTION update_platform_updated_at();

DROP TRIGGER IF EXISTS trg_notification_campaign_updated ON notification_campaign;
CREATE TRIGGER trg_notification_campaign_updated BEFORE UPDATE ON notification_campaign
FOR EACH ROW EXECUTE FUNCTION update_platform_updated_at();

DROP TRIGGER IF EXISTS trg_invoice_updated ON invoice;
CREATE TRIGGER trg_invoice_updated BEFORE UPDATE ON invoice
FOR EACH ROW EXECUTE FUNCTION update_platform_updated_at();

DROP TRIGGER IF EXISTS trg_storage_quota_updated ON storage_quota;
CREATE TRIGGER trg_storage_quota_updated BEFORE UPDATE ON storage_quota
FOR EACH ROW EXECUTE FUNCTION update_platform_updated_at();
