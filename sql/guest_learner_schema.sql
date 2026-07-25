-- =============================================================================
-- Guest Learner Schema
-- =============================================================================
-- Persists guest (unauthenticated) learner profiles so their preferences,
-- likes, and activity survive across sessions instead of being lost on
-- Redis cache expiry.
--
-- Run this on your Supabase / PostgreSQL database.
-- Compatible with the Django model in feed/models.py (table name matches).
-- =============================================================================

-- 1. Main guest learner table
CREATE TABLE IF NOT EXISTS feed_guestlearner (
    device_id         UUID PRIMARY KEY,
    name              VARCHAR(255) NOT NULL,
    level_id          INTEGER REFERENCES feed_feedacademiclevel(id) ON DELETE SET NULL,
    class_obj_id      INTEGER REFERENCES feed_feedacademicclass(id) ON DELETE SET NULL,
    subject_ids       JSONB NOT NULL DEFAULT '[]'::jsonb,
    liked_lesson_ids  JSONB NOT NULL DEFAULT '[]'::jsonb,
    onboarding_completed_at  TIMESTAMP WITH TIME ZONE,
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  feed_guestlearner IS 'Guest (unauthenticated) learner profiles keyed by client-generated device UUID';
COMMENT ON COLUMN feed_guestlearner.device_id IS 'UUID v4 generated client-side, stored in FlutterSecureStorage';

-- 2. Many-to-many junction table: guest ↔ subjects
CREATE TABLE IF NOT EXISTS feed_guestlearner_subjects (
    id                SERIAL PRIMARY KEY,
    guestlearner_id   UUID NOT NULL REFERENCES feed_guestlearner(device_id) ON DELETE CASCADE,
    feedsubject_id    INTEGER NOT NULL REFERENCES feed_feedsubject(id) ON DELETE CASCADE,
    UNIQUE (guestlearner_id, feedsubject_id)
);

CREATE INDEX IF NOT EXISTS idx_guestlearner_subjects_guest ON feed_guestlearner_subjects(guestlearner_id);
CREATE INDEX IF NOT EXISTS idx_guestlearner_subjects_subject ON feed_guestlearner_subjects(feedsubject_id);

-- 3. Guest likes: tracks which lessons a guest has liked
CREATE TABLE IF NOT EXISTS feed_guestlike (
    id                SERIAL PRIMARY KEY,
    device_id         UUID NOT NULL REFERENCES feed_guestlearner(device_id) ON DELETE CASCADE,
    lesson_id         INTEGER NOT NULL REFERENCES feed_feedlesson(id) ON DELETE CASCADE,
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (device_id, lesson_id)
);

CREATE INDEX IF NOT EXISTS idx_guestlike_device   ON feed_guestlike(device_id);
CREATE INDEX IF NOT EXISTS idx_guestlike_lesson   ON feed_guestlike(lesson_id);

-- 4. Trigger: auto-update updated_at on feed_guestlearner
CREATE OR REPLACE FUNCTION update_guestlearner_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_guestlearner_updated_at ON feed_guestlearner;
CREATE TRIGGER trg_guestlearner_updated_at
    BEFORE UPDATE ON feed_guestlearner
    FOR EACH ROW
    EXECUTE FUNCTION update_guestlearner_timestamp();

-- 5. Trigger: sync liked_lesson_ids JSONB from feed_guestlike table
CREATE OR REPLACE FUNCTION sync_guest_liked_lesson_ids()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE feed_guestlearner
        SET liked_lesson_ids = (
            SELECT COALESCE(jsonb_agg(lesson_id ORDER BY created_at DESC), '[]'::jsonb)
            FROM feed_guestlike
            WHERE device_id = NEW.device_id
        )
        WHERE device_id = NEW.device_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE feed_guestlearner
        SET liked_lesson_ids = (
            SELECT COALESCE(jsonb_agg(lesson_id ORDER BY created_at DESC), '[]'::jsonb)
            FROM feed_guestlike
            WHERE device_id = OLD.device_id
        )
        WHERE device_id = OLD.device_id;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_guest_likes_insert ON feed_guestlike;
CREATE TRIGGER trg_sync_guest_likes_insert
    AFTER INSERT ON feed_guestlike
    FOR EACH ROW
    EXECUTE FUNCTION sync_guest_liked_lesson_ids();

DROP TRIGGER IF EXISTS trg_sync_guest_likes_delete ON feed_guestlike;
CREATE TRIGGER trg_sync_guest_likes_delete
    AFTER DELETE ON feed_guestlike
    FOR EACH ROW
    EXECUTE FUNCTION sync_guest_liked_lesson_ids();
