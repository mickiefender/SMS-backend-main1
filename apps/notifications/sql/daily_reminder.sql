-- ============================================================================
-- Alara Daily Learning Reminder — raw SQL DDL (idempotent)
--
-- Adds the Daily Learning Reminder columns to the notifications_preference
-- table. This mirrors the fields declared on
-- apps.notifications.models.NotificationPreference:
--
--   daily_reminder_enabled  = models.BooleanField(default=True)
--   daily_reminder_time     = models.TimeField(null=True, blank=True)
--   last_daily_reminder_at  = models.DateTimeField(null=True, blank=True)
--
-- Handles the case where the columns already exist. Safe to run repeatedly.
-- Target: PostgreSQL (Supabase).
-- ============================================================================

-- ─── daily_reminder_enabled ─────────────────────────────────────────────────
ALTER TABLE notifications_preference
    ADD COLUMN IF NOT EXISTS daily_reminder_enabled boolean DEFAULT true NOT NULL;

-- ─── daily_reminder_time ────────────────────────────────────────────────────
ALTER TABLE notifications_preference
    ADD COLUMN IF NOT EXISTS daily_reminder_time time NULL;

-- ─── last_daily_reminder_at ─────────────────────────────────────────────────
ALTER TABLE notifications_preference
    ADD COLUMN IF NOT EXISTS last_daily_reminder_at timestamp with time zone NULL;

-- ─── Indexes for the once-per-day guard ─────────────────────────────────────
-- The scheduler filters by (user active, daily_reminder_enabled, and
-- last_daily_reminder_at) to avoid spamming. An index on the enabled flag
-- plus the last-sent timestamp keeps the daily scan cheap as the user base
-- grows.
CREATE INDEX IF NOT EXISTS idx_notifications_pref_daily_reminder
    ON notifications_preference (daily_reminder_enabled, last_daily_reminder_at);
