-- =============================================================================
-- Alara Learning Feed — Recommendation Engine Schema
-- =============================================================================
-- Tables for interaction tracking, interest scoring, and the blended
-- recommendation algorithm.
--
-- Run: psql -f feed_recommendation_schema.sql
-- Or:  \i backend/sql/feed_recommendation_schema.sql
-- =============================================================================

-- 1. User Interaction Log
--    Every meaningful action on a lesson, for both authenticated and guest users.
CREATE TABLE IF NOT EXISTS feed_userinteraction (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users_user(id) ON DELETE CASCADE,
    guest_device_id VARCHAR(255) NOT NULL DEFAULT '',
    lesson_id BIGINT NOT NULL REFERENCES feed_feedlesson(id) ON DELETE CASCADE,
    interaction_type VARCHAR(30) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feed_userinteraction_user_created
    ON feed_userinteraction(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feed_userinteraction_guest_device
    ON feed_userinteraction(guest_device_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feed_userinteraction_lesson_type
    ON feed_userinteraction(lesson_id, interaction_type);
CREATE INDEX IF NOT EXISTS idx_feed_userinteraction_created
    ON feed_userinteraction(created_at DESC);

COMMENT ON TABLE feed_userinteraction IS 'Raw user interaction log used by the interest scoring engine';
COMMENT ON COLUMN feed_userinteraction.guest_device_id IS 'UUID for unauthenticated guest users';
COMMENT ON COLUMN feed_userinteraction.metadata IS 'Additional context (watch_seconds, completion_pct, etc.)';


-- 2. User Interest Scores
--    Weighted cumulative scores per user per domain entity (subject, level, etc.)
CREATE TABLE IF NOT EXISTS feed_userinterestscore (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users_user(id) ON DELETE CASCADE,
    guest_device_id VARCHAR(255) NOT NULL DEFAULT '',
    interest_domain VARCHAR(20) NOT NULL,
    interest_id INTEGER NOT NULL,
    score NUMERIC(8, 2) NOT NULL DEFAULT 0
        CHECK (score >= -100 AND score <= 100),
    positive_interactions INTEGER NOT NULL DEFAULT 0,
    negative_interactions INTEGER NOT NULL DEFAULT 0,
    is_onboarding_preference BOOLEAN NOT NULL DEFAULT FALSE,
    last_interaction_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Unique constraint: one score per (user, domain, entity)
    CONSTRAINT uq_feed_userinterestscore_user
        UNIQUE (user_id, interest_domain, interest_id),
    CONSTRAINT uq_feed_userinterestscore_guest
        UNIQUE (guest_device_id, interest_domain, interest_id)
);

CREATE INDEX IF NOT EXISTS idx_feed_userinterestscore_user_domain_score
    ON feed_userinterestscore(user_id, interest_domain, score DESC);
CREATE INDEX IF NOT EXISTS idx_feed_userinterestscore_guest_domain_score
    ON feed_userinterestscore(guest_device_id, interest_domain, score DESC);

COMMENT ON TABLE feed_userinterestscore IS 'Cumulative weighted interest scores per user per domain entity';
COMMENT ON COLUMN feed_userinterestscore.interest_domain IS 'One of: subject, level, class_obj, tag, teacher';
COMMENT ON COLUMN feed_userinterestscore.interest_id IS 'FK ID of the entity (subject_id, level_id, tag_id, teacher_id, class_obj_id)';
COMMENT ON COLUMN feed_userinterestscore.is_onboarding_preference IS 'True if seeded from onboarding (decays slower)';


-- 3. Guest Interaction Log
--    Lightweight interaction records for guest users.
CREATE TABLE IF NOT EXISTS feed_guestinteraction (
    id BIGSERIAL PRIMARY KEY,
    device_id UUID NOT NULL,
    lesson_id BIGINT NOT NULL REFERENCES feed_feedlesson(id) ON DELETE CASCADE,
    interaction_type VARCHAR(30) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feed_guestinteraction_device_created
    ON feed_guestinteraction(device_id, created_at DESC);

COMMENT ON TABLE feed_guestinteraction IS 'Interaction records for unauthenticated guest users';


-- 4. Auto-update updated_at trigger for feed_userinterestscore
CREATE OR REPLACE FUNCTION update_feed_userinterestscore_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_feed_userinterestscore_updated_at
    ON feed_userinterestscore;
CREATE TRIGGER trg_feed_userinterestscore_updated_at
    BEFORE UPDATE ON feed_userinterestscore
    FOR EACH ROW
    EXECUTE FUNCTION update_feed_userinterestscore_timestamp();
