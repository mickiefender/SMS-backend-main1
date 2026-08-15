-- ============================================================================
-- Alara Learning Feed — Schema Sync / Migration Script
-- ============================================================================
-- Purpose: Bring an existing database (created by the older
--          supabase_feed_schema.sql) in line with the current Django models
--          and add the super-admin-managed lesson metadata tables.
--
-- Why this is needed:
--   * The feed app has no Django migration files, so `python manage.py
--     migrate` (syncdb) *only creates missing tables* — it NEVER alters an
--     existing table to add columns.
--   * The legacy `feed_feedlesson` table was created with `class_id` and
--     (on some deployments) `academic_level_id`, while the current Django
--     model maps to `level_id` and `class_obj_id`, and additionally expects
--     metadata FK columns (content type, difficulty level, curriculum,
--     learning objective), keywords/hashtags JSON and Cloudflare video
--     fields.  Every teacher upload inserts those columns, which fails with
--     errors like  "column feed_feedlesson.academic_level_id does not exist"
--     / "column feed_feedlesson.class_obj_id does not exist".
--
-- How to run:
--   psql "$DATABASE_URL" -f feed_schema_sync.sql
--   or paste into the Supabase SQL Editor.
--
-- The script is fully idempotent — safe to re-run.
-- ============================================================================

-- ============================================================================
-- 1. New lesson-metadata reference tables (super-admin managed)
-- ============================================================================

CREATE TABLE IF NOT EXISTS feed_feedcontenttype (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feed_feeddifficultylevel (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    "order" INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feed_feedcurriculum (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feed_feedlearningobjective (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feed_feedvisibilityscope (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- 2. Recommendation / interaction tables (models_v2.py)
-- ============================================================================

CREATE TABLE IF NOT EXISTS feed_userinteraction (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users_user(id) ON DELETE CASCADE,
    guest_device_id VARCHAR(255) NOT NULL DEFAULT '',
    lesson_id BIGINT NOT NULL REFERENCES feed_feedlesson(id) ON DELETE CASCADE,
    interaction_type VARCHAR(30) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_userinteraction_user_created
    ON feed_userinteraction (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_userinteraction_guest_created
    ON feed_userinteraction (guest_device_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_userinteraction_lesson_type
    ON feed_userinteraction (lesson_id, interaction_type);
CREATE INDEX IF NOT EXISTS idx_userinteraction_created
    ON feed_userinteraction (created_at DESC);

CREATE TABLE IF NOT EXISTS feed_userinterestscore (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users_user(id) ON DELETE CASCADE,
    guest_device_id VARCHAR(255) NOT NULL DEFAULT '',
    interest_domain VARCHAR(20) NOT NULL,
    interest_id INTEGER NOT NULL,
    score NUMERIC(8,2) NOT NULL DEFAULT 0,
    positive_interactions INTEGER NOT NULL DEFAULT 0,
    negative_interactions INTEGER NOT NULL DEFAULT 0,
    is_onboarding_preference BOOLEAN NOT NULL DEFAULT FALSE,
    last_interaction_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_interest_score_range CHECK (score >= -100 AND score <= 100),
    UNIQUE (user_id, interest_domain, interest_id),
    UNIQUE (guest_device_id, interest_domain, interest_id)
);
CREATE INDEX IF NOT EXISTS idx_userinterest_user_domain_score
    ON feed_userinterestscore (user_id, interest_domain, score DESC);
CREATE INDEX IF NOT EXISTS idx_userinterest_guest_domain_score
    ON feed_userinterestscore (guest_device_id, interest_domain, score DESC);

CREATE TABLE IF NOT EXISTS feed_guestinteraction (
    id BIGSERIAL PRIMARY KEY,
    device_id UUID NOT NULL,
    lesson_id BIGINT NOT NULL REFERENCES feed_feedlesson(id) ON DELETE CASCADE,
    interaction_type VARCHAR(30) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_guestinteraction_device_created
    ON feed_guestinteraction (device_id, created_at DESC);

-- ============================================================================
-- 3. Fix legacy feed_feedlesson columns
-- ============================================================================
-- The current Django model maps:
--   FeedLesson.level     -> column level_id      (legacy: academic_level_id)
--   FeedLesson.class_obj -> column class_obj_id  (legacy: class_id)
--
-- If the legacy column exists and the new one does not, RENAME it so any
-- existing foreign-key constraint + index move with it.

DO $$
BEGIN
    -- level_id
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'feed_feedlesson' AND column_name = 'level_id'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'feed_feedlesson' AND column_name = 'academic_level_id'
        ) THEN
            ALTER TABLE feed_feedlesson RENAME COLUMN academic_level_id TO level_id;
        ELSE
            ALTER TABLE feed_feedlesson
                ADD COLUMN level_id BIGINT REFERENCES feed_feedacademiclevel(id) ON DELETE SET NULL;
        END IF;
    END IF;

    -- class_obj_id
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'feed_feedlesson' AND column_name = 'class_obj_id'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'feed_feedlesson' AND column_name = 'class_id'
        ) THEN
            ALTER TABLE feed_feedlesson RENAME COLUMN class_id TO class_obj_id;
        ELSE
            ALTER TABLE feed_feedlesson
                ADD COLUMN class_obj_id BIGINT REFERENCES feed_feedacademicclass(id) ON DELETE SET NULL;
        END IF;
    END IF;
END $$;

-- If BOTH the legacy and the new column happen to exist (partial manual fix),
-- copy any missing values across.  Wrapped so it is a no-op when the legacy
-- column was renamed/dropped.
DO $$
BEGIN
    BEGIN
        UPDATE feed_feedlesson
           SET level_id = academic_level_id
         WHERE level_id IS NULL AND academic_level_id IS NOT NULL;
    EXCEPTION WHEN undefined_column THEN NULL;
    END;

    BEGIN
        UPDATE feed_feedlesson
           SET class_obj_id = class_id
         WHERE class_obj_id IS NULL AND class_id IS NOT NULL;
    EXCEPTION WHEN undefined_column THEN NULL;
    END;
END $$;

-- ============================================================================
-- 4. Add the remaining columns the current FeedLesson model expects
-- ============================================================================

ALTER TABLE feed_feedlesson ADD COLUMN IF NOT EXISTS content_type_id
    BIGINT REFERENCES feed_feedcontenttype(id) ON DELETE SET NULL;
ALTER TABLE feed_feedlesson ADD COLUMN IF NOT EXISTS difficulty_level_id
    BIGINT REFERENCES feed_feeddifficultylevel(id) ON DELETE SET NULL;
ALTER TABLE feed_feedlesson ADD COLUMN IF NOT EXISTS curriculum_id
    BIGINT REFERENCES feed_feedcurriculum(id) ON DELETE SET NULL;
ALTER TABLE feed_feedlesson ADD COLUMN IF NOT EXISTS learning_objective_id
    BIGINT REFERENCES feed_feedlearningobjective(id) ON DELETE SET NULL;

ALTER TABLE feed_feedlesson ADD COLUMN IF NOT EXISTS keywords JSONB NOT NULL DEFAULT '[]';
ALTER TABLE feed_feedlesson ADD COLUMN IF NOT EXISTS hashtags JSONB NOT NULL DEFAULT '[]';

ALTER TABLE feed_feedlesson ADD COLUMN IF NOT EXISTS cloudflare_video_uid VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE feed_feedlesson ADD COLUMN IF NOT EXISTS cloudflare_playback_url VARCHAR(1000) NOT NULL DEFAULT '';
ALTER TABLE feed_feedlesson ADD COLUMN IF NOT EXISTS cloudflare_thumbnail_url VARCHAR(1000) NOT NULL DEFAULT '';
ALTER TABLE feed_feedlesson ADD COLUMN IF NOT EXISTS video_duration DOUBLE PRECISION NOT NULL DEFAULT 0;

-- Indexes for the new columns (existing ones may already exist from the
-- legacy schema — IF NOT EXISTS keeps this re-runnable).
CREATE INDEX IF NOT EXISTS idx_feedlesson_level ON feed_feedlesson (level_id);
CREATE INDEX IF NOT EXISTS idx_feedlesson_class_obj ON feed_feedlesson (class_obj_id);
CREATE INDEX IF NOT EXISTS idx_feedlesson_content_type ON feed_feedlesson (content_type_id);
CREATE INDEX IF NOT EXISTS idx_feedlesson_difficulty_level ON feed_feedlesson (difficulty_level_id);
CREATE INDEX IF NOT EXISTS idx_feedlesson_curriculum ON feed_feedlesson (curriculum_id);
CREATE INDEX IF NOT EXISTS idx_feedlesson_cloudflare_uid ON feed_feedlesson (cloudflare_video_uid);

-- ============================================================================
-- 5. Recreate the full-text search trigger (legacy trigger references
--    NEW.class_id which no longer exists after the rename above)
-- ============================================================================

DO $$
BEGIN
    -- If the old trigger/function exists, drop them so we can replace.
    DROP TRIGGER IF EXISTS trg_feedlesson_search_vector ON feed_feedlesson;
END $$;

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
    WHERE c.id = NEW.class_obj_id;

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

CREATE TRIGGER trg_feedlesson_search_vector
    BEFORE INSERT OR UPDATE ON feed_feedlesson
    FOR EACH ROW
    EXECUTE FUNCTION feed_lesson_update_search_vector();

-- ============================================================================
-- 6. Recreate the trending materialized view (legacy version selected
--    l.class_id which no longer exists)
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS mv_feed_trending_lessons;

CREATE MATERIALIZED VIEW mv_feed_trending_lessons AS
SELECT
    l.id AS lesson_id,
    l.title,
    l.teacher_id,
    l.school_id,
    l.subject_id,
    l.level_id,
    l.class_obj_id AS class_id,
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

REFRESH MATERIALIZED VIEW CONCURRENTLY mv_feed_popular_teachers;

-- ============================================================================
-- 7. Add updated_at triggers for the new tables
-- ============================================================================

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
        'feed_lessonanalytics',
        'feed_feedcontenttype',
        'feed_feeddifficultylevel',
        'feed_feedcurriculum',
        'feed_feedlearningobjective',
        'feed_feedvisibilityscope',
        'feed_userinteraction',
        'feed_userinterestscore'
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

-- ============================================================================
-- 8. Seed / restore the canonical lesson metadata
--    (same data the Flutter upload flow falls back to; super admins can then
--     edit, add or delete these from their dashboard).
--    Uses explicit IDs and ON CONFLICT (slug) DO UPDATE (never rewrites ids
--    once rows already exist, so existing FK references stay valid).
-- ============================================================================

-- ── Academic levels ─────────────────────────────────────────────
INSERT INTO feed_feedacademiclevel (id, name, slug, "order") VALUES
    (1, 'Nursery', 'nursery', 0),
    (2, 'KG', 'kg', 1),
    (3, 'Primary 1', 'primary_1', 2),
    (4, 'Primary 2', 'primary_2', 3),
    (5, 'Primary 3', 'primary_3', 4),
    (6, 'Primary 4', 'primary_4', 5),
    (7, 'Primary 5', 'primary_5', 6),
    (8, 'Primary 6', 'primary_6', 7),
    (9, 'JHS 1', 'jhs_1', 8),
    (10, 'JHS 2', 'jhs_2', 9),
    (11, 'JHS 3', 'jhs_3', 10),
    (12, 'SHS', 'shs', 11),
    (13, 'University', 'university', 12)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    "order" = EXCLUDED."order",
    is_active = TRUE;

-- ── Academic classes (one per level, matching the app's class map) ──
INSERT INTO feed_feedacademicclass (id, level_id, name, slug, "order") VALUES
    (1, 1, 'Nursery', 'nursery', 0),
    (2, 2, 'KG', 'kg', 1),
    (3, 3, 'Primary 1', 'primary_1', 2),
    (4, 4, 'Primary 2', 'primary_2', 3),
    (5, 5, 'Primary 3', 'primary_3', 4),
    (6, 6, 'Primary 4', 'primary_4', 5),
    (7, 7, 'Primary 5', 'primary_5', 6),
    (8, 8, 'Primary 6', 'primary_6', 7),
    (9, 9, 'JHS 1', 'jhs_1', 8),
    (10, 10, 'JHS 2', 'jhs_2', 9),
    (11, 11, 'JHS 3', 'jhs_3', 10),
    (12, 12, 'SHS', 'shs', 11),
    (13, 13, 'University', 'university', 12)
ON CONFLICT (level_id, slug) DO UPDATE SET
    name = EXCLUDED.name,
    "order" = EXCLUDED."order",
    is_active = TRUE;

-- ── Subjects ───────────────────────────────────────────────────
INSERT INTO feed_feedsubject (id, name, slug) VALUES
    (1, 'Mathematics', 'mathematics'),
    (2, 'English Language', 'english_language'),
    (3, 'Science', 'science'),
    (4, 'ICT', 'ict'),
    (5, 'Social Studies', 'social_studies'),
    (6, 'French', 'french'),
    (7, 'Religious Studies', 'religious_studies'),
    (8, 'Creative Arts', 'creative_arts'),
    (9, 'Physics', 'physics'),
    (10, 'Chemistry', 'chemistry'),
    (11, 'Biology', 'biology'),
    (12, 'Business', 'business'),
    (13, 'Other', 'other')
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    is_active = TRUE;

-- ── Content types ──────────────────────────────────────────────
INSERT INTO feed_feedcontenttype (id, name, slug) VALUES
    (1, 'Lesson Explanation', 'lesson_explanation'),
    (2, 'Exam Preparation', 'exam_preparation'),
    (3, 'Homework Help', 'homework_help'),
    (4, 'Study Tips', 'study_tips'),
    (5, 'Classroom Activity', 'classroom_activity'),
    (6, 'School Announcement', 'school_announcement'),
    (7, 'Teacher Training', 'teacher_training'),
    (8, 'Motivation', 'motivation'),
    (9, 'Educational Entertainment', 'educational_entertainment')
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    is_active = TRUE;

-- ── Difficulty levels ──────────────────────────────────────────
INSERT INTO feed_feeddifficultylevel (id, name, slug, "order") VALUES
    (1, 'Beginner', 'beginner', 0),
    (2, 'Intermediate', 'intermediate', 1),
    (3, 'Advanced', 'advanced', 2)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    "order" = EXCLUDED."order",
    is_active = TRUE;

-- ── Curricula ──────────────────────────────────────────────────
INSERT INTO feed_feedcurriculum (id, name, slug) VALUES
    (1, 'GES Curriculum', 'ges_curriculum'),
    (2, 'NaCCA', 'nacca'),
    (3, 'BECE Preparation', 'bece_preparation'),
    (4, 'Cambridge', 'cambridge'),
    (5, 'Other', 'other')
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    is_active = TRUE;

-- ── Learning objectives ────────────────────────────────────────
INSERT INTO feed_feedlearningobjective (id, name, slug) VALUES
    (1, 'Introduce a New Concept', 'introduce_new_concept'),
    (2, 'Revision', 'revision'),
    (3, 'Practice Questions', 'practice_questions'),
    (4, 'Exam Preparation', 'exam_preparation'),
    (5, 'Demonstration', 'demonstration'),
    (6, 'Motivation', 'motivation')
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    is_active = TRUE;

-- ── Visibility scopes ──────────────────────────────────────────
INSERT INTO feed_feedvisibilityscope (name, slug, description) VALUES
    ('Only My School', 'only_my_school', 'Visible only to users within the same school.'),
    ('Schools in My Region', 'schools_in_region', 'Visible to users in schools within the same region.'),
    ('Public Feed', 'public_feed', 'Visible to all users on the platform.')
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description;

-- ============================================================================
-- 9. Recompute search vectors for any existing rows (columns changed)
-- ============================================================================
UPDATE feed_feedlesson
   SET updated_at = updated_at
 WHERE id IN (
    SELECT l.id
    FROM feed_feedlesson l
    LEFT JOIN feed_feedacademiclevel al ON al.id = l.level_id
    LEFT JOIN feed_feedacademicclass ac ON ac.id = l.class_obj_id
    LEFT JOIN feed_feedsubject s ON s.id = l.subject_id
    WHERE l.search_vector IS NULL
       OR l.level_id IS NOT NULL AND al.id IS NULL
       OR l.class_obj_id IS NOT NULL AND ac.id IS NULL
       OR l.subject_id IS NOT NULL AND s.id IS NULL
    LIMIT 1000
);

-- ============================================================================
-- End of script
-- ============================================================================
