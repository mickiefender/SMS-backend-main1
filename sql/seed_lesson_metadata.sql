-- =============================================================================
-- Create and seed lesson metadata reference tables
-- =============================================================================
-- Run this if you skipped makemigrations/migrate or need to create tables
-- directly in the database.
--
-- Usage: psql -f backend/sql/seed_lesson_metadata.sql
-- =============================================================================

-- 1. Feed Content Type
CREATE TABLE IF NOT EXISTS feed_feedcontenttype (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO feed_feedcontenttype (name, slug) VALUES
    ('Lesson Explanation', 'lesson_explanation'),
    ('Exam Preparation', 'exam_preparation'),
    ('Homework Help', 'homework_help'),
    ('Study Tips', 'study_tips'),
    ('Classroom Activity', 'classroom_activity'),
    ('School Announcement', 'school_announcement'),
    ('Teacher Training', 'teacher_training'),
    ('Motivation', 'motivation'),
    ('Educational Entertainment', 'educational_entertainment')
ON CONFLICT (slug) DO NOTHING;

-- 2. Feed Difficulty Level
CREATE TABLE IF NOT EXISTS feed_feeddifficultylevel (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    "order" INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO feed_feeddifficultylevel (name, slug, "order") VALUES
    ('Beginner', 'beginner', 0),
    ('Intermediate', 'intermediate', 1),
    ('Advanced', 'advanced', 2)
ON CONFLICT (slug) DO NOTHING;

-- 3. Feed Curriculum
CREATE TABLE IF NOT EXISTS feed_feedcurriculum (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO feed_feedcurriculum (name, slug) VALUES
    ('GES Curriculum', 'ges_curriculum'),
    ('NaCCA', 'nacca'),
    ('BECE Preparation', 'bece_preparation'),
    ('Cambridge', 'cambridge'),
    ('Other', 'other')
ON CONFLICT (slug) DO NOTHING;

-- 4. Feed Learning Objective
CREATE TABLE IF NOT EXISTS feed_feedlearningobjective (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO feed_feedlearningobjective (name, slug) VALUES
    ('Introduce a New Concept', 'introduce_new_concept'),
    ('Revision', 'revision'),
    ('Practice Questions', 'practice_questions'),
    ('Exam Preparation', 'exam_preparation'),
    ('Demonstration', 'demonstration'),
    ('Motivation', 'motivation')
ON CONFLICT (slug) DO NOTHING;

-- 5. Feed Visibility Scope
CREATE TABLE IF NOT EXISTS feed_feedvisibilityscope (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO feed_feedvisibilityscope (name, slug, description) VALUES
    ('Only My School', 'only_my_school', 'Visible only to users within the same school.'),
    ('Schools in My Region', 'schools_in_region', 'Visible to users in schools within the same region.'),
    ('Public Feed', 'public_feed', 'Visible to all users on the platform.')
ON CONFLICT (slug) DO NOTHING;

-- 6. Add missing FeedLesson columns (if not already added by Django migrations)
ALTER TABLE feed_feedlesson ADD COLUMN IF NOT EXISTS content_type_id BIGINT REFERENCES feed_feedcontenttype(id) ON DELETE SET NULL;
ALTER TABLE feed_feedlesson ADD COLUMN IF NOT EXISTS difficulty_level_id BIGINT REFERENCES feed_feeddifficultylevel(id) ON DELETE SET NULL;
ALTER TABLE feed_feedlesson ADD COLUMN IF NOT EXISTS curriculum_id BIGINT REFERENCES feed_feedcurriculum(id) ON DELETE SET NULL;
ALTER TABLE feed_feedlesson ADD COLUMN IF NOT EXISTS learning_objective_id BIGINT REFERENCES feed_feedlearningobjective(id) ON DELETE SET NULL;
ALTER TABLE feed_feedlesson ADD COLUMN IF NOT EXISTS keywords JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE feed_feedlesson ADD COLUMN IF NOT EXISTS hashtags JSONB NOT NULL DEFAULT '[]'::jsonb;

-- 7. Add indexes for the new FK columns
CREATE INDEX IF NOT EXISTS idx_feed_feedlesson_content_type ON feed_feedlesson(content_type_id);
CREATE INDEX IF NOT EXISTS idx_feed_feedlesson_difficulty_level ON feed_feedlesson(difficulty_level_id);
CREATE INDEX IF NOT EXISTS idx_feed_feedlesson_curriculum ON feed_feedlesson(curriculum_id);

-- 8. Add GIN indexes for keyword and hashtag search
CREATE INDEX IF NOT EXISTS idx_feed_feedlesson_keywords_gin ON feed_feedlesson USING GIN (keywords);
CREATE INDEX IF NOT EXISTS idx_feed_feedlesson_hashtags_gin ON feed_feedlesson USING GIN (hashtags);

-- 9. Add content_type and difficulty to the recommendation schema interest domains
--    (these are used by feed_userinterestscore.interest_domain column)
COMMENT ON TABLE feed_feedcontenttype IS 'Content type classification for lessons (Lesson Explanation, Exam Prep, etc.)';
COMMENT ON TABLE feed_feeddifficultylevel IS 'Difficulty level for lessons (Beginner, Intermediate, Advanced)';
COMMENT ON TABLE feed_feedcurriculum IS 'Curriculum alignment options';
COMMENT ON TABLE feed_feedlearningobjective IS 'Learning objectives for lessons';
COMMENT ON TABLE feed_feedvisibilityscope IS 'Visibility scope options for lessons';
