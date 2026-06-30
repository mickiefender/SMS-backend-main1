-- Grading System Migration SQL
-- Tables: GradingScale, GradingScaleEntry, Assessment
-- Adds fields to TerminalReport: promotion_status, best_subject_name, best_subject_score

-- ============================================================
-- 1. GradingScale - School-defined grade boundaries
-- ============================================================
CREATE TABLE IF NOT EXISTS academics_gradingscale (
    id SERIAL PRIMARY KEY,
    school_id BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    academic_session_id BIGINT REFERENCES academics_academicsession(id) ON DELETE SET NULL,
    name VARCHAR(100) NOT NULL DEFAULT 'Default Grading Scale',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 2. GradingScaleEntry - Individual grade boundary (A, B, B2, etc.)
-- ============================================================
CREATE TABLE IF NOT EXISTS academics_gradingscaleentry (
    id SERIAL PRIMARY KEY,
    grading_scale_id BIGINT NOT NULL REFERENCES academics_gradingscale(id) ON DELETE CASCADE,
    grade_letter VARCHAR(5) NOT NULL,
    min_percentage DOUBLE PRECISION NOT NULL,
    max_percentage DOUBLE PRECISION NOT NULL,
    points DOUBLE PRECISION NOT NULL DEFAULT 0,
    is_passing BOOLEAN NOT NULL DEFAULT TRUE,
    remark VARCHAR(255) NOT NULL DEFAULT '',
    promotion_eligible BOOLEAN NOT NULL DEFAULT TRUE,
    "order" INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- 3. Assessment - Exam types created by school admin
-- ============================================================
CREATE TABLE IF NOT EXISTS academics_assessment (
    id SERIAL PRIMARY KEY,
    school_id BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    academic_session_id BIGINT NOT NULL REFERENCES academics_academicsession(id) ON DELETE CASCADE,
    subject_id BIGINT NOT NULL REFERENCES academics_subject(id) ON DELETE CASCADE,
    class_obj_id BIGINT NOT NULL REFERENCES academics_class(id) ON DELETE CASCADE,
    term INTEGER NOT NULL CHECK (term IN (1, 2, 3, 4)),
    category VARCHAR(25) NOT NULL DEFAULT 'continuous_assessment' CHECK (category IN ('continuous_assessment', 'examination')),
    title VARCHAR(255) NOT NULL,
    total_marks DOUBLE PRECISION NOT NULL DEFAULT 100,
    assessment_date DATE NOT NULL,
    weight_percentage DOUBLE PRECISION NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_id BIGINT REFERENCES users_user(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assessment_school_class_subject_term 
    ON academics_assessment(school_id, class_obj_id, subject_id, term);

-- ============================================================
-- 4. Add fields to TerminalReport
-- ============================================================
ALTER TABLE academics_terminalreport 
    ADD COLUMN IF NOT EXISTS promotion_status VARCHAR(20) NOT NULL DEFAULT 'unknown'
        CHECK (promotion_status IN ('promoted', 'repeated', 'unknown'));

ALTER TABLE academics_terminalreport 
    ADD COLUMN IF NOT EXISTS best_subject_name VARCHAR(255) NOT NULL DEFAULT '';

ALTER TABLE academics_terminalreport 
    ADD COLUMN IF NOT EXISTS best_subject_score DOUBLE PRECISION NOT NULL DEFAULT 0;

-- ============================================================
-- Record migrations so Django knows they've been applied
-- ============================================================
INSERT INTO django_migrations (app, name, applied) 
VALUES ('academics', '0003_grading_scale_assessment', NOW())
ON CONFLICT (app, name) DO NOTHING;
