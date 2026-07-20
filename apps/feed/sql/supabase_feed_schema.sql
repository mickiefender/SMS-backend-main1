-- ============================================================================
-- Alara Learning Feed - Supabase PostgreSQL Schema
-- ============================================================================
-- Purpose: Complete database setup for the Alara Learning Feed backend.
--          Includes tables, constraints, indexes, triggers, full-text search,
--          materialized views, storage buckets, RLS policies, and seed data.
--
-- Notes:
--   - Run this script inside a Supabase SQL Editor (or psql) after the core
--     Django migrations have created users_user, schools_school, etc.
--   - This script uses `IF NOT EXISTS` guards so it can be re-run safely.
--   - Generated columns (search_vector) are maintained by PostgreSQL triggers.
--     Django models expose these fields as read-only (editable=False).
--   - The `users_user.supabase_uid` column is added here for RLS comparisons
--     with auth.uid(). It is expected to be populated by your auth/webhook layer.
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 1. Compatibility column for Supabase Auth UUID mapping
-- ============================================================================
ALTER TABLE users_user
    ADD COLUMN IF NOT EXISTS supabase_uid UUID;

CREATE INDEX IF NOT EXISTS idx_users_user_supabase_uid
    ON users_user (supabase_uid);

-- ============================================================================
-- 2. Reference / lookup tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS feed_feedacademiclevel (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    "order" INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feed_feedacademicclass (
    id BIGSERIAL PRIMARY KEY,
    level_id BIGINT NOT NULL REFERENCES feed_feedacademiclevel(id) ON DELETE RESTRICT,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL,
    "order" INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (level_id, slug)
);

CREATE TABLE IF NOT EXISTS feed_feedsubject (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    slug VARCHAR(255) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feed_feedtag (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    usage_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedtag_name_trgm
    ON feed_feedtag USING gin (name gin_trgm_ops);

-- ============================================================================
-- 3. Student learning profile
-- ============================================================================

CREATE TABLE IF NOT EXISTS feed_learningprofile (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    preferred_level_id BIGINT REFERENCES feed_feedacademiclevel(id) ON DELETE SET NULL,
    preferred_class_id BIGINT REFERENCES feed_feedacademicclass(id) ON DELETE SET NULL,
    preferred_subject_ids JSONB NOT NULL DEFAULT '[]',
    preferences JSONB NOT NULL DEFAULT '{}',
    learning_streak_days INTEGER NOT NULL DEFAULT 0,
    last_learning_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id)
);

CREATE TABLE IF NOT EXISTS feed_learningprofile_subjects (
    id BIGSERIAL PRIMARY KEY,
    learningprofile_id BIGINT NOT NULL REFERENCES feed_learningprofile(id) ON DELETE CASCADE,
    feedsubject_id BIGINT NOT NULL REFERENCES feed_feedsubject(id) ON DELETE CASCADE,
    UNIQUE (learningprofile_id, feedsubject_id)
);

CREATE INDEX IF NOT EXISTS idx_learningprofile_user
    ON feed_learningprofile (user_id);
CREATE INDEX IF NOT EXISTS idx_learningprofile_level_class
    ON feed_learningprofile (preferred_level_id, preferred_class_id);

-- ============================================================================
-- 4. Feed lessons & resources
-- ============================================================================

CREATE TABLE IF NOT EXISTS feed_feedlesson (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    topic VARCHAR(255),

    teacher_id BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    school_id BIGINT REFERENCES schools_school(id) ON DELETE SET NULL,

    level_id BIGINT REFERENCES feed_feedacademiclevel(id) ON DELETE SET NULL,
    class_id BIGINT REFERENCES feed_feedacademicclass(id) ON DELETE SET NULL,
    subject_id BIGINT REFERENCES feed_feedsubject(id) ON DELETE SET NULL,

    visibility VARCHAR(20) NOT NULL DEFAULT 'public'
        CHECK (visibility IN ('draft', 'pending_review', 'public', 'school_only', 'hidden', 'suspended')),
    status VARCHAR(20) NOT NULL DEFAULT 'pending_review'
        CHECK (status IN ('pending_review', 'approved', 'rejected', 'suspended')),
    verification_status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (verification_status IN ('pending', 'verified', 'rejected')),

    duration_seconds INTEGER NOT NULL DEFAULT 0,
    thumbnail_url TEXT,
    poster_url TEXT,
    extra_metadata JSONB NOT NULL DEFAULT '{}',

    view_count BIGINT NOT NULL DEFAULT 0,
    unique_view_count BIGINT NOT NULL DEFAULT 0,
    like_count BIGINT NOT NULL DEFAULT 0,
    save_count BIGINT NOT NULL DEFAULT 0,
    comment_count BIGINT NOT NULL DEFAULT 0,
    share_count BIGINT NOT NULL DEFAULT 0,
    download_count BIGINT NOT NULL DEFAULT 0,
    completion_rate NUMERIC(5,2) NOT NULL DEFAULT 0.00,
    avg_watch_seconds NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    trending_score NUMERIC(12,6) NOT NULL DEFAULT 0.000000,
    quality_score NUMERIC(5,2) NOT NULL DEFAULT 0.00,
    published_at TIMESTAMPTZ,

    search_vector TSVECTOR,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_duration_nonnegative CHECK (duration_seconds >= 0),
    CONSTRAINT chk_completion_0_100 CHECK (completion_rate >= 0 AND completion_rate <= 100),
    CONSTRAINT chk_quality_0_100 CHECK (quality_score >= 0 AND quality_score <= 100)
);

CREATE TABLE IF NOT EXISTS feed_feedlesson_tags (
    id BIGSERIAL PRIMARY KEY,
    feedlesson_id BIGINT NOT NULL REFERENCES feed_feedlesson(id) ON DELETE CASCADE,
    feedtag_id BIGINT NOT NULL REFERENCES feed_feedtag(id) ON DELETE CASCADE,
    UNIQUE (feedlesson_id, feedtag_id)
);

CREATE TABLE IF NOT EXISTS feed_lessonresource (
    id BIGSERIAL PRIMARY KEY,
    lesson_id BIGINT NOT NULL REFERENCES feed_feedlesson(id) ON DELETE CASCADE,
    resource_type VARCHAR(20) NOT NULL
        CHECK (resource_type IN ('video', 'pdf', 'image', 'audio', 'assignment', 'quiz')),
    title VARCHAR(255),
    storage_bucket VARCHAR(100) NOT NULL,
    storage_path TEXT NOT NULL,
    public_url TEXT,
    file_size BIGINT,
    mime_type VARCHAR(100),
    duration_seconds INTEGER,
    width INTEGER,
    height INTEGER,
    page_count INTEGER,
    extra_metadata JSONB NOT NULL DEFAULT '{}',
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_resource_duration_nonnegative CHECK (duration_seconds IS NULL OR duration_seconds >= 0)
);

-- Core indexes for feed queries
CREATE INDEX IF NOT EXISTS idx_feedlesson_teacher
    ON feed_feedlesson (teacher_id);
CREATE INDEX IF NOT EXISTS idx_feedlesson_school
    ON feed_feedlesson (school_id);
CREATE INDEX IF NOT EXISTS idx_feedlesson_level
    ON feed_feedlesson (level_id);
CREATE INDEX IF NOT EXISTS idx_feedlesson_class
    ON feed_feedlesson (class_id);
CREATE INDEX IF NOT EXISTS idx_feedlesson_subject
    ON feed_feedlesson (subject_id);
CREATE INDEX IF NOT EXISTS idx_feedlesson_visibility_status
    ON feed_feedlesson (visibility, status);
CREATE INDEX IF NOT EXISTS idx_feedlesson_visibility_status_published
    ON feed_feedlesson (visibility, status, published_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_feedlesson_trending
    ON feed_feedlesson (trending_score DESC, published_at DESC)
    WHERE status = 'approved' AND visibility = 'public';
CREATE INDEX IF NOT EXISTS idx_feedlesson_latest
    ON feed_feedlesson (published_at DESC NULLS LAST)
    WHERE status = 'approved' AND visibility = 'public';
CREATE INDEX IF NOT EXISTS idx_feedlesson_completion
    ON feed_feedlesson (completion_rate DESC)
    WHERE status = 'approved' AND visibility = 'public';
CREATE INDEX IF NOT EXISTS idx_feedlesson_school_only
    ON feed_feedlesson (school_id, status, visibility)
    WHERE visibility = 'school_only';
CREATE INDEX IF NOT EXISTS idx_feedlesson_verified
    ON feed_feedlesson (verification_status)
    WHERE verification_status = 'verified';
CREATE INDEX IF NOT EXISTS idx_feedlesson_level_class_subject
    ON feed_feedlesson (level_id, class_id, subject_id, status, visibility);

-- Full-text search GIN index
CREATE INDEX IF NOT EXISTS idx_feedlesson_search_vector
    ON feed_feedlesson USING gin (search_vector);

-- Trigram indexes for autocomplete / fallback search
CREATE INDEX IF NOT EXISTS idx_feedlesson_title_trgm
    ON feed_feedlesson USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_feedlesson_topic_trgm
    ON feed_feedlesson USING gin (topic gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_lessonresource_lesson
    ON feed_lessonresource (lesson_id);
CREATE INDEX IF NOT EXISTS idx_lessonresource_type
    ON feed_lessonresource (resource_type);

-- ============================================================================
-- 5. Engagement tables (likes, saves, watch history, follows)
-- ============================================================================

CREATE TABLE IF NOT EXISTS feed_feedlike (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    lesson_id BIGINT NOT NULL REFERENCES feed_feedlesson(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, lesson_id)
);
CREATE INDEX IF NOT EXISTS idx_feedlike_lesson
    ON feed_feedlike (lesson_id);
CREATE INDEX IF NOT EXISTS idx_feedlike_user
    ON feed_feedlike (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS feed_feedsave (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    lesson_id BIGINT NOT NULL REFERENCES feed_feedlesson(id) ON DELETE CASCADE,
    offline_download_metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, lesson_id)
);
CREATE INDEX IF NOT EXISTS idx_feedsave_lesson
    ON feed_feedsave (lesson_id);
CREATE INDEX IF NOT EXISTS idx_feedsave_user
    ON feed_feedsave (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS feed_watchhistory (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    lesson_id BIGINT NOT NULL REFERENCES feed_feedlesson(id) ON DELETE CASCADE,
    watch_seconds INTEGER NOT NULL DEFAULT 0,
    completion_percentage NUMERIC(5,2) NOT NULL DEFAULT 0.00,
    is_completed BOOLEAN NOT NULL DEFAULT FALSE,
    resume_position_seconds INTEGER NOT NULL DEFAULT 0,
    last_watched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, lesson_id)
);
CREATE INDEX IF NOT EXISTS idx_watchhistory_user
    ON feed_watchhistory (user_id, last_watched_at DESC);
CREATE INDEX IF NOT EXISTS idx_watchhistory_lesson
    ON feed_watchhistory (lesson_id);
CREATE INDEX IF NOT EXISTS idx_watchhistory_completed
    ON feed_watchhistory (user_id, is_completed);

CREATE TABLE IF NOT EXISTS feed_teacherfollower (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    teacher_id BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, teacher_id)
);
CREATE INDEX IF NOT EXISTS idx_teacherfollower_user
    ON feed_teacherfollower (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_teacherfollower_teacher
    ON feed_teacherfollower (teacher_id);

-- ============================================================================
-- 6. Comments (nested, soft delete, likes, pinned)
-- ============================================================================

CREATE TABLE IF NOT EXISTS feed_feedcomment (
    id BIGSERIAL PRIMARY KEY,
    lesson_id BIGINT NOT NULL REFERENCES feed_feedlesson(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    parent_id BIGINT REFERENCES feed_feedcomment(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
    is_moderated BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    like_count BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_comment_not_self_parent CHECK (id <> parent_id)
);
CREATE INDEX IF NOT EXISTS idx_feedcomment_lesson
    ON feed_feedcomment (lesson_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedcomment_parent
    ON feed_feedcomment (parent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedcomment_pinned
    ON feed_feedcomment (lesson_id, is_pinned DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS feed_commentlike (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    comment_id BIGINT NOT NULL REFERENCES feed_feedcomment(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, comment_id)
);
CREATE INDEX IF NOT EXISTS idx_commentlike_comment
    ON feed_commentlike (comment_id);
CREATE INDEX IF NOT EXISTS idx_commentlike_user
    ON feed_commentlike (user_id);

-- ============================================================================
-- 7. Notifications
-- ============================================================================

CREATE TABLE IF NOT EXISTS feed_feednotification (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    notification_type VARCHAR(30) NOT NULL
        CHECK (notification_type IN (
            'new_lesson', 'teacher_reply', 'comment_reply',
            'follower', 'report_update', 'lesson_approved',
            'lesson_suspended', 'general'
        )),
    title VARCHAR(255) NOT NULL,
    message TEXT,
    lesson_id BIGINT REFERENCES feed_feedlesson(id) ON DELETE SET NULL,
    comment_id BIGINT REFERENCES feed_feedcomment(id) ON DELETE SET NULL,
    actor_id BIGINT REFERENCES users_user(id) ON DELETE SET NULL,
    related_object_type VARCHAR(50),
    related_object_id VARCHAR(50),
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    priority VARCHAR(20) NOT NULL DEFAULT 'normal'
        CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_feednotification_user
    ON feed_feednotification (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feednotification_unread
    ON feed_feednotification (user_id, is_read, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feednotification_type
    ON feed_feednotification (notification_type);

-- ============================================================================
-- 8. Reports & moderation
-- ============================================================================

CREATE TABLE IF NOT EXISTS feed_feedreport (
    id BIGSERIAL PRIMARY KEY,
    reporter_id BIGINT REFERENCES users_user(id) ON DELETE SET NULL,
    target_type VARCHAR(20) NOT NULL
        CHECK (target_type IN ('lesson', 'comment', 'teacher')),
    lesson_id BIGINT REFERENCES feed_feedlesson(id) ON DELETE CASCADE,
    comment_id BIGINT REFERENCES feed_feedcomment(id) ON DELETE CASCADE,
    teacher_id BIGINT REFERENCES users_user(id) ON DELETE CASCADE,
    reason VARCHAR(50) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'reviewing', 'resolved', 'dismissed')),
    resolution TEXT,
    resolved_by_id BIGINT REFERENCES users_user(id) ON DELETE SET NULL,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_report_single_target CHECK (
        (target_type = 'lesson' AND lesson_id IS NOT NULL AND comment_id IS NULL AND teacher_id IS NULL) OR
        (target_type = 'comment' AND comment_id IS NOT NULL AND lesson_id IS NULL AND teacher_id IS NULL) OR
        (target_type = 'teacher' AND teacher_id IS NOT NULL AND lesson_id IS NULL AND comment_id IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS idx_feedreport_status
    ON feed_feedreport (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedreport_reporter
    ON feed_feedreport (reporter_id, created_at DESC);

-- ============================================================================
-- 9. Search & recommendation support
-- ============================================================================

CREATE TABLE IF NOT EXISTS feed_feedsearchquery (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users_user(id) ON DELETE SET NULL,
    query TEXT NOT NULL,
    result_count INTEGER,
    ip_hash VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_feedsearchquery_user
    ON feed_feedsearchquery (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedsearchquery_query_trgm
    ON feed_feedsearchquery USING gin (query gin_trgm_ops);

CREATE TABLE IF NOT EXISTS feed_recommendationcache (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users_user(id) ON DELETE CASCADE,
    cache_key VARCHAR(255) NOT NULL,
    strategy VARCHAR(50) NOT NULL,
    lesson_ids BIGINT[] NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, cache_key)
);
CREATE INDEX IF NOT EXISTS idx_recommendationcache_user
    ON feed_recommendationcache (user_id, cache_key);
CREATE INDEX IF NOT EXISTS idx_recommendationcache_expires
    ON feed_recommendationcache (expires_at);

-- ============================================================================
-- 10. Analytics tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS feed_lessonanalytics (
    id BIGSERIAL PRIMARY KEY,
    lesson_id BIGINT NOT NULL UNIQUE REFERENCES feed_feedlesson(id) ON DELETE CASCADE,
    views BIGINT NOT NULL DEFAULT 0,
    unique_views BIGINT NOT NULL DEFAULT 0,
    total_watch_seconds BIGINT NOT NULL DEFAULT 0,
    avg_watch_seconds NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    likes BIGINT NOT NULL DEFAULT 0,
    saves BIGINT NOT NULL DEFAULT 0,
    comments BIGINT NOT NULL DEFAULT 0,
    shares BIGINT NOT NULL DEFAULT 0,
    downloads BIGINT NOT NULL DEFAULT 0,
    completions BIGINT NOT NULL DEFAULT 0,
    completion_rate NUMERIC(5,2) NOT NULL DEFAULT 0.00,
    date JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feed_dailyanalytics (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    school_id BIGINT REFERENCES schools_school(id) ON DELETE SET NULL,
    metric_name VARCHAR(50) NOT NULL,
    metric_value BIGINT NOT NULL DEFAULT 0,
    dimension VARCHAR(100),
    UNIQUE (date, school_id, metric_name, dimension)
);
CREATE INDEX IF NOT EXISTS idx_dailyanalytics_date_metric
    ON feed_dailyanalytics (date, metric_name);
CREATE INDEX IF NOT EXISTS idx_dailyanalytics_school
    ON feed_dailyanalytics (school_id, date);

-- ============================================================================
-- 11. Triggers & functions
-- ============================================================================

-- Auto-update updated_at columns
CREATE OR REPLACE FUNCTION feed_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
    tbl TEXT;
    tables TEXT[] := ARRAY[
        'feed_feedacademiclevel',
        'feed_feedacademicclass',
        'feed_feedsubject',
        'feed_feedtag',
        'feed_learningprofile',
        'feed_feedlesson',
        'feed_lessonresource',
        'feed_feedcomment',
        'feed_feednotification',
        'feed_feedreport',
        'feed_lessonanalytics'
    ];
BEGIN
    FOREACH tbl IN ARRAY tables
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_updated_at ON %I;', replace(tbl, '.', '_'), tbl);
        EXECUTE format(
            'CREATE TRIGGER trg_%s_updated_at BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION feed_set_updated_at();',
            replace(tbl, '.', '_'), tbl
        );
    END LOOP;
END $$;

-- Full-text search update function
CREATE OR REPLACE FUNCTION feed_lesson_update_search_vector()
RETURNS TRIGGER AS $$
DECLARE
    tag_names TEXT;
    teacher_name TEXT;
    school_name TEXT;
    level_name TEXT;
    class_name TEXT;
    subject_name TEXT;
BEGIN
    SELECT string_agg(t.name, ' ')
    INTO tag_names
    FROM feed_feedtag t
    JOIN feed_feedlesson_tags lt ON lt.feedtag_id = t.id
    WHERE lt.feedlesson_id = NEW.id;

    SELECT COALESCE(u.first_name, '') || ' ' || COALESCE(u.last_name, '') || ' ' || COALESCE(u.username, '')
    INTO teacher_name
    FROM users_user u
    WHERE u.id = NEW.teacher_id;

    SELECT s.name
    INTO school_name
    FROM schools_school s
    WHERE s.id = NEW.school_id;

    SELECT l.name
    INTO level_name
    FROM feed_feedacademiclevel l
    WHERE l.id = NEW.level_id;

    SELECT c.name
    INTO class_name
    FROM feed_feedacademicclass c
    WHERE c.id = NEW.class_id;

    SELECT sub.name
    INTO subject_name
    FROM feed_feedsubject sub
    WHERE sub.id = NEW.subject_id;

    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.topic, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(tag_names, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(teacher_name, '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(school_name, '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(level_name, '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(class_name, '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(subject_name, '')), 'C');

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_feedlesson_search_vector ON feed_feedlesson;
CREATE TRIGGER trg_feedlesson_search_vector
    BEFORE INSERT OR UPDATE ON feed_feedlesson
    FOR EACH ROW
    EXECUTE FUNCTION feed_lesson_update_search_vector();

-- Trigger to update denormalized engagement counters safely
CREATE OR REPLACE FUNCTION feed_update_lesson_counts()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_TABLE_NAME = 'feed_feedlike' THEN
        IF TG_OP = 'INSERT' THEN
            UPDATE feed_feedlesson SET like_count = like_count + 1 WHERE id = NEW.lesson_id;
        ELSIF TG_OP = 'DELETE' THEN
            UPDATE feed_feedlesson SET like_count = GREATEST(like_count - 1, 0) WHERE id = OLD.lesson_id;
        END IF;
    ELSIF TG_TABLE_NAME = 'feed_feedsave' THEN
        IF TG_OP = 'INSERT' THEN
            UPDATE feed_feedlesson SET save_count = save_count + 1 WHERE id = NEW.lesson_id;
        ELSIF TG_OP = 'DELETE' THEN
            UPDATE feed_feedlesson SET save_count = GREATEST(save_count - 1, 0) WHERE id = OLD.lesson_id;
        END IF;
    ELSIF TG_TABLE_NAME = 'feed_feedcomment' THEN
        IF TG_OP = 'INSERT' AND NEW.is_deleted = FALSE THEN
            UPDATE feed_feedlesson SET comment_count = comment_count + 1 WHERE id = NEW.lesson_id;
        ELSIF TG_OP = 'DELETE' AND OLD.is_deleted = FALSE THEN
            UPDATE feed_feedlesson SET comment_count = GREATEST(comment_count - 1, 0) WHERE id = OLD.lesson_id;
        ELSIF TG_OP = 'UPDATE' AND OLD.is_deleted = FALSE AND NEW.is_deleted = TRUE THEN
            UPDATE feed_feedlesson SET comment_count = GREATEST(comment_count - 1, 0) WHERE id = NEW.lesson_id;
        ELSIF TG_OP = 'UPDATE' AND OLD.is_deleted = TRUE AND NEW.is_deleted = FALSE THEN
            UPDATE feed_feedlesson SET comment_count = comment_count + 1 WHERE id = NEW.lesson_id;
        END IF;
    ELSIF TG_TABLE_NAME = 'feed_commentlike' THEN
        IF TG_OP = 'INSERT' THEN
            UPDATE feed_feedcomment SET like_count = like_count + 1 WHERE id = NEW.comment_id;
        ELSIF TG_OP = 'DELETE' THEN
            UPDATE feed_feedcomment SET like_count = GREATEST(like_count - 1, 0) WHERE id = OLD.comment_id;
        END IF;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_feedlike_counts ON feed_feedlike;
CREATE TRIGGER trg_feedlike_counts
    AFTER INSERT OR DELETE ON feed_feedlike
    FOR EACH ROW EXECUTE FUNCTION feed_update_lesson_counts();

DROP TRIGGER IF EXISTS trg_feedsave_counts ON feed_feedsave;
CREATE TRIGGER trg_feedsave_counts
    AFTER INSERT OR DELETE ON feed_feedsave
    FOR EACH ROW EXECUTE FUNCTION feed_update_lesson_counts();

DROP TRIGGER IF EXISTS trg_feedcomment_counts ON feed_feedcomment;
CREATE TRIGGER trg_feedcomment_counts
    AFTER INSERT OR DELETE OR UPDATE OF is_deleted ON feed_feedcomment
    FOR EACH ROW EXECUTE FUNCTION feed_update_lesson_counts();

DROP TRIGGER IF EXISTS trg_commentlike_counts ON feed_commentlike;
CREATE TRIGGER trg_commentlike_counts
    AFTER INSERT OR DELETE ON feed_commentlike
    FOR EACH ROW EXECUTE FUNCTION feed_update_lesson_counts();

-- ============================================================================
-- 12. Materialized views for trending & analytics
-- ============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_feed_trending_lessons AS
SELECT
    l.id AS lesson_id,
    l.title,
    l.teacher_id,
    l.school_id,
    l.subject_id,
    l.level_id,
    l.class_id,
    l.published_at,
    l.view_count,
    l.unique_view_count,
    l.like_count,
    l.save_count,
    l.comment_count,
    l.share_count,
    l.completion_rate,
    l.avg_watch_seconds,
    l.trending_score,
    (l.view_count * 1.0
        + l.unique_view_count * 2.0
        + l.like_count * 4.0
        + l.save_count * 5.0
        + l.comment_count * 3.0
        + l.share_count * 6.0
        + COALESCE(l.completion_rate, 0) * 10.0
        + COALESCE(l.avg_watch_seconds, 0) * 0.1
    ) AS raw_score
FROM feed_feedlesson l
WHERE l.status = 'approved'
  AND l.visibility = 'public'
  AND l.published_at IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_trending_lesson_id
    ON mv_feed_trending_lessons (lesson_id);
CREATE INDEX IF NOT EXISTS idx_mv_trending_raw_score
    ON mv_feed_trending_lessons (raw_score DESC, published_at DESC);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_feed_popular_teachers AS
SELECT
    u.id AS teacher_id,
    COUNT(DISTINCT l.id) AS lesson_count,
    COALESCE(SUM(l.view_count), 0) AS total_views,
    COALESCE(SUM(l.like_count), 0) AS total_likes,
    COALESCE(AVG(l.quality_score), 0) AS avg_quality_score,
    COALESCE(AVG(l.completion_rate), 0) AS avg_completion_rate
FROM users_user u
LEFT JOIN feed_feedlesson l ON l.teacher_id = u.id
WHERE u.role = 'teacher'
GROUP BY u.id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_popular_teachers_id
    ON mv_feed_popular_teachers (teacher_id);

-- ============================================================================
-- 13. Storage buckets (Supabase Storage)
-- ============================================================================

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES
    ('lesson-videos', 'lesson-videos', TRUE, 5368709120, ARRAY[
        'video/mp4', 'video/webm', 'video/quicktime', 'video/x-msvideo',
        'video/mpeg', 'video/ogg'
    ]),
    ('lesson-images', 'lesson-images', TRUE, 104857600, ARRAY[
        'image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/svg+xml'
    ]),
    ('lesson-pdfs', 'lesson-pdfs', TRUE, 209715200, ARRAY[
        'application/pdf'
    ]),
    ('lesson-thumbnails', 'lesson-thumbnails', TRUE, 52428800, ARRAY[
        'image/jpeg', 'image/png', 'image/webp'
    ]),
    ('lesson-audio', 'lesson-audio', TRUE, 209715200, ARRAY[
        'audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/aac', 'audio/webm'
    ]),
    ('lesson-assignments', 'lesson-assignments', TRUE, 104857600, ARRAY[
        'application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'text/plain'
    ]),
    ('lesson-quizzes', 'lesson-quizzes', TRUE, 52428800, ARRAY[
        'application/json', 'application/pdf', 'text/plain'
    ]),
    ('teacher-avatars', 'teacher-avatars', TRUE, 52428800, ARRAY[
        'image/jpeg', 'image/png', 'image/webp'
    ])
ON CONFLICT (id) DO UPDATE SET
    public = EXCLUDED.public,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

-- ============================================================================
-- 14. Storage RLS policies
-- ============================================================================
ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    pol TEXT;
    policies TEXT[] := ARRAY[
        'feed_public_read',
        'feed_teacher_upload',
        'feed_owner_manage',
        'feed_school_admin_manage',
        'feed_avatar_public_read',
        'feed_avatar_owner_manage'
    ];
BEGIN
    FOREACH pol IN ARRAY policies
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON storage.objects;', pol);
    END LOOP;
END $$;

-- Public read access for lesson assets (anyone can view public content)
CREATE POLICY feed_public_read ON storage.objects
    FOR SELECT
    USING (bucket_id IN (
        'lesson-videos', 'lesson-images', 'lesson-pdfs', 'lesson-thumbnails',
        'lesson-audio', 'lesson-assignments', 'lesson-quizzes'
    ));

-- Teachers can upload lesson content (service role / authenticated with teacher role)
CREATE POLICY feed_teacher_upload ON storage.objects
    FOR INSERT
    WITH CHECK (
        bucket_id IN (
            'lesson-videos', 'lesson-images', 'lesson-pdfs', 'lesson-thumbnails',
            'lesson-audio', 'lesson-assignments', 'lesson-quizzes'
        )
        AND auth.uid() IS NOT NULL
        AND EXISTS (
            SELECT 1 FROM users_user u
            WHERE u.supabase_uid = auth.uid()
              AND u.role = 'teacher'
              AND u.is_active_user = TRUE
        )
    );

-- Users can manage objects they own (path starts with their supabase_uid folder)
CREATE POLICY feed_owner_manage ON storage.objects
    FOR ALL
    USING (
        auth.uid() IS NOT NULL
        AND owner = auth.uid()
    )
    WITH CHECK (
        auth.uid() IS NOT NULL
        AND owner = auth.uid()
    );

-- School admins can manage lesson content within their school
CREATE POLICY feed_school_admin_manage ON storage.objects
    FOR ALL
    USING (
        auth.uid() IS NOT NULL
        AND bucket_id IN (
            'lesson-videos', 'lesson-images', 'lesson-pdfs', 'lesson-thumbnails',
            'lesson-audio', 'lesson-assignments', 'lesson-quizzes'
        )
        AND EXISTS (
            SELECT 1 FROM users_user u
            WHERE u.supabase_uid = auth.uid()
              AND u.role IN ('school_admin', 'super_admin')
              AND u.is_active_user = TRUE
        )
    )
    WITH CHECK (
        auth.uid() IS NOT NULL
        AND bucket_id IN (
            'lesson-videos', 'lesson-images', 'lesson-pdfs', 'lesson-thumbnails',
            'lesson-audio', 'lesson-assignments', 'lesson-quizzes'
        )
        AND EXISTS (
            SELECT 1 FROM users_user u
            WHERE u.supabase_uid = auth.uid()
              AND u.role IN ('school_admin', 'super_admin')
              AND u.is_active_user = TRUE
        )
    );

-- Teacher avatar policies
CREATE POLICY feed_avatar_public_read ON storage.objects
    FOR SELECT
    USING (bucket_id = 'teacher-avatars');

CREATE POLICY feed_avatar_owner_manage ON storage.objects
    FOR ALL
    USING (
        auth.uid() IS NOT NULL
        AND bucket_id = 'teacher-avatars'
        AND owner = auth.uid()
    )
    WITH CHECK (
        auth.uid() IS NOT NULL
        AND bucket_id = 'teacher-avatars'
        AND owner = auth.uid()
    );

-- ============================================================================
-- 15. Seed data
-- ============================================================================

-- Academic levels
INSERT INTO feed_feedacademiclevel (name, slug, "order") VALUES
    ('Primary', 'primary', 1),
    ('Junior High School', 'jhs', 2),
    ('Senior High School', 'shs', 3),
    ('Tertiary', 'tertiary', 4)
ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name, "order" = EXCLUDED."order";

-- Academic classes
DO $$
DECLARE
    primary_id BIGINT;
    jhs_id BIGINT;
    shs_id BIGINT;
BEGIN
    SELECT id INTO primary_id FROM feed_feedacademiclevel WHERE slug = 'primary';
    SELECT id INTO jhs_id FROM feed_feedacademiclevel WHERE slug = 'jhs';
    SELECT id INTO shs_id FROM feed_feedacademiclevel WHERE slug = 'shs';

    INSERT INTO feed_feedacademicclass (level_id, name, slug, "order") VALUES
        (primary_id, 'Primary 1', 'primary-1', 1),
        (primary_id, 'Primary 2', 'primary-2', 2),
        (primary_id, 'Primary 3', 'primary-3', 3),
        (primary_id, 'Primary 4', 'primary-4', 4),
        (primary_id, 'Primary 5', 'primary-5', 5),
        (primary_id, 'Primary 6', 'primary-6', 6),
        (jhs_id, 'JHS 1', 'jhs-1', 7),
        (jhs_id, 'JHS 2', 'jhs-2', 8),
        (jhs_id, 'JHS 3', 'jhs-3', 9),
        (shs_id, 'SHS 1', 'shs-1', 10),
        (shs_id, 'SHS 2', 'shs-2', 11),
        (shs_id, 'SHS 3', 'shs-3', 12)
    ON CONFLICT (level_id, slug) DO UPDATE SET name = EXCLUDED.name, "order" = EXCLUDED."order";
END $$;

-- Subjects
INSERT INTO feed_feedsubject (name, slug) VALUES
    ('Mathematics', 'mathematics'),
    ('Science', 'science'),
    ('English Language', 'english-language'),
    ('Information and Communications Technology', 'ict'),
    ('Social Studies', 'social-studies'),
    ('Integrated Science', 'integrated-science'),
    ('Physics', 'physics'),
    ('Chemistry', 'chemistry'),
    ('Biology', 'biology'),
    ('History', 'history'),
    ('Geography', 'geography'),
    ('Economics', 'economics'),
    ('French', 'french'),
    ('Religious and Moral Education', 'rme'),
    ('Creative Arts', 'creative-arts'),
    ('Physical Education', 'physical-education')
ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name;

-- Common tags
INSERT INTO feed_feedtag (name, slug) VALUES
    ('algebra', 'algebra'),
    ('geometry', 'geometry'),
    ('grammar', 'grammar'),
    ('essay', 'essay'),
    ('programming', 'programming'),
    ('cell-biology', 'cell-biology'),
    ('electricity', 'electricity'),
    ('exam-prep', 'exam-prep'),
    ('quick-lesson', 'quick-lesson'),
    ('stem', 'stem'),
    ('literature', 'literature'),
    ('ghana', 'ghana')
ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name;

-- ============================================================================
-- 16. Seed lookup option tables (Django enums mirrored here for reporting)
-- ============================================================================

CREATE TABLE IF NOT EXISTS feed_lkpvisibility (
    value VARCHAR(20) PRIMARY KEY,
    label VARCHAR(50) NOT NULL
);
INSERT INTO feed_lkpvisibility (value, label) VALUES
    ('draft', 'Draft'),
    ('pending_review', 'Pending Review'),
    ('public', 'Public'),
    ('school_only', 'School Only'),
    ('hidden', 'Hidden'),
    ('suspended', 'Suspended')
ON CONFLICT (value) DO UPDATE SET label = EXCLUDED.label;

CREATE TABLE IF NOT EXISTS feed_lkpstatus (
    value VARCHAR(20) PRIMARY KEY,
    label VARCHAR(50) NOT NULL
);
INSERT INTO feed_lkpstatus (value, label) VALUES
    ('pending_review', 'Pending Review'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('suspended', 'Suspended')
ON CONFLICT (value) DO UPDATE SET label = EXCLUDED.label;

CREATE TABLE IF NOT EXISTS feed_lkpnotificationtype (
    value VARCHAR(30) PRIMARY KEY,
    label VARCHAR(50) NOT NULL
);
INSERT INTO feed_lkpnotificationtype (value, label) VALUES
    ('new_lesson', 'New Lesson'),
    ('teacher_reply', 'Teacher Reply'),
    ('comment_reply', 'Comment Reply'),
    ('follower', 'New Follower'),
    ('report_update', 'Report Update'),
    ('lesson_approved', 'Lesson Approved'),
    ('lesson_suspended', 'Lesson Suspended'),
    ('general', 'General')
ON CONFLICT (value) DO UPDATE SET label = EXCLUDED.label;

CREATE TABLE IF NOT EXISTS feed_lkpreportreason (
    value VARCHAR(50) PRIMARY KEY,
    label VARCHAR(100) NOT NULL
);
INSERT INTO feed_lkpreportreason (value, label) VALUES
    ('inappropriate_content', 'Inappropriate Content'),
    ('misinformation', 'Misinformation'),
    ('copyright', 'Copyright Violation'),
    ('bullying', 'Bullying / Harassment'),
    ('spam', 'Spam'),
    ('other', 'Other')
ON CONFLICT (value) DO UPDATE SET label = EXCLUDED.label;

-- ============================================================================
-- 17. Refresh materialized views after seeding
-- ============================================================================
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_feed_trending_lessons;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_feed_popular_teachers;

-- ============================================================================
-- End of schema
-- ============================================================================
