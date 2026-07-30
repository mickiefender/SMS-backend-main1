-- =============================================================================
-- Notification System Database Migration
-- Creates the tables for the centralized notification system.
-- 
-- Tables:
--   notifications_type              — lookup table of notification categories
--   notifications_device            — FCM token registry (multi-device)
--   notifications_preference        — per-user notification preferences
--   notifications_notification       — stored in-app notification records
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. notifications_type  (lookup table)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifications_type (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,
    slug            VARCHAR(100) NOT NULL UNIQUE,
    description     TEXT NOT NULL DEFAULT '',
    is_enabled_by_default BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_type_sort
    ON notifications_type (sort_order, name);

-- Seed notification types
INSERT INTO notifications_type (name, slug, description, sort_order) VALUES
    ('Feed', 'feed', 'New lessons from followed teachers and feed activity', 1),
    ('School Announcements', 'school_announcement', 'School-wide announcements and notices', 2),
    ('Assignments', 'assignment', 'New assignments posted', 3),
    ('Assignment Reminders', 'assignment_reminder', 'Reminders about upcoming assignment due dates', 4),
    ('Grades', 'grade', 'Grades and results published', 5),
    ('Attendance', 'attendance', 'Attendance marked for the day', 6),
    ('Fee Reminders', 'fee_reminder', 'Fee payment reminders and confirmations', 7),
    ('Messages', 'message', 'Direct messages from teachers and admins', 8),
    ('Live Classes', 'live_class', 'Live class session notifications', 9),
    ('Upload Status', 'upload_status', 'Video upload processing status updates', 10),
    ('Comments & Replies', 'comment', 'Comments and replies on your posts', 11),
    ('Likes', 'like', 'Likes on your lessons and comments', 12),
    ('Daily Reminders', 'daily_reminder', 'Daily learning reminders', 13),
    ('App Updates', 'app_update', 'Application updates and maintenance notices', 14)
ON CONFLICT (slug) DO NOTHING;


-- ---------------------------------------------------------------------------
-- 2. notifications_device  (FCM token registry)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifications_device (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    fcm_token       VARCHAR(500) NOT NULL UNIQUE,
    platform        VARCHAR(20) NOT NULL DEFAULT 'android'
                        CHECK (platform IN ('ios', 'android', 'web')),
    device_name     VARCHAR(255) NOT NULL DEFAULT '',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_seen_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_device_user_active
    ON notifications_device (user_id, is_active);

CREATE INDEX IF NOT EXISTS idx_notifications_device_token
    ON notifications_device (fcm_token);


-- ---------------------------------------------------------------------------
-- 3. notifications_preference  (per-user notification settings)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifications_preference (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL UNIQUE REFERENCES users_user(id) ON DELETE CASCADE,
    preferences     JSONB NOT NULL DEFAULT '{}'::jsonb,
    push_enabled    BOOLEAN NOT NULL DEFAULT TRUE,
    email_enabled   BOOLEAN NOT NULL DEFAULT TRUE,
    quiet_hours_start TIME WITHOUT TIME ZONE,
    quiet_hours_end   TIME WITHOUT TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Auto-create preference row for every user
CREATE OR REPLACE FUNCTION notifications_auto_create_preferences()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO notifications_preference (user_id)
    VALUES (NEW.id)
    ON CONFLICT (user_id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_auto_create_notification_prefs'
    ) THEN
        CREATE TRIGGER trg_auto_create_notification_prefs
        AFTER INSERT ON users_user
        FOR EACH ROW
        EXECUTE FUNCTION notifications_auto_create_preferences();
    END IF;
END;
$$;


-- ---------------------------------------------------------------------------
-- 4. notifications_notification  (stored in-app notifications)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifications_notification (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_id        INTEGER NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    notification_type   VARCHAR(50) NOT NULL,
    category            VARCHAR(50) NOT NULL DEFAULT 'feed'
                            CHECK (category IN (
                                'feed', 'school_announcement', 'assignment',
                                'assignment_reminder', 'grade', 'attendance',
                                'fee_reminder', 'message', 'live_class',
                                'upload_status', 'comment', 'like',
                                'daily_reminder', 'app_update'
                            )),
    title               VARCHAR(255) NOT NULL,
    message             TEXT NOT NULL,
    image_url           VARCHAR(1000) NOT NULL DEFAULT '',
    target_screen       VARCHAR(255) NOT NULL DEFAULT '',
    target_id           VARCHAR(50) NOT NULL DEFAULT '',
    priority            VARCHAR(20) NOT NULL DEFAULT 'normal'
                            CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    is_read             BOOLEAN NOT NULL DEFAULT FALSE,
    is_pinned           BOOLEAN NOT NULL DEFAULT FALSE,
    read_at             TIMESTAMP WITH TIME ZONE,
    dedup_hash          VARCHAR(64) NOT NULL DEFAULT '',
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_notification_recipient_created
    ON notifications_notification (recipient_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notifications_notification_recipient_unread
    ON notifications_notification (recipient_id, is_read)
    WHERE is_read = FALSE;

CREATE INDEX IF NOT EXISTS idx_notifications_notification_category
    ON notifications_notification (category);

CREATE INDEX IF NOT EXISTS idx_notifications_notification_dedup
    ON notifications_notification (dedup_hash);

-- ---------------------------------------------------------------
-- Automatically clean up old notifications (keep 90 days)
-- ---------------------------------------------------------------
CREATE OR REPLACE FUNCTION notifications_cleanup_old()
RETURNS void AS $$
BEGIN
    DELETE FROM notifications_notification
    WHERE created_at < NOW() - INTERVAL '90 days';
END;
$$ LANGUAGE plpgsql;


-- ---------------------------------------------------------------
-- Function: get_or_create_preferences (used by application code)
-- ---------------------------------------------------------------
CREATE OR REPLACE FUNCTION notifications_ensure_preferences(p_user_id INTEGER)
RETURNS SETOF notifications_preference AS $$
BEGIN
    RETURN QUERY
    INSERT INTO notifications_preference (user_id)
    VALUES (p_user_id)
    ON CONFLICT (user_id) DO NOTHING
    RETURNING *;
    
    IF NOT FOUND THEN
        RETURN QUERY
        SELECT * FROM notifications_preference WHERE user_id = p_user_id;
    END IF;
END;
$$ LANGUAGE plpgsql;


-- ---------------------------------------------------------------
-- Verify all tables were created
-- ---------------------------------------------------------------
DO $$
DECLARE
    tbl_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO tbl_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name IN (
        'notifications_type',
        'notifications_device',
        'notifications_preference',
        'notifications_notification'
      );
    
    IF tbl_count < 4 THEN
        RAISE WARNING 'Only % of 4 notification tables were created', tbl_count;
    ELSE
        RAISE NOTICE 'All 4 notification tables created successfully';
    END IF;
END;
$$;
