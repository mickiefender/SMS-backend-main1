-- ============================================================
-- Student Promotion System Migration
-- Academic years, year-based student enrollments, configurable
-- promotion rules/policies, promotion batches (history) and
-- per-student promotion records.
--
-- Run in Supabase SQL Editor (or psql) BEFORE applying the
-- Django migration, or as a standalone schema bootstrap.
-- ============================================================

-- ------------------------------------------------------------
-- 1. Academic Year
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS academics_academicyear (
    id              BIGSERIAL PRIMARY KEY,
    school_id       BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    name            VARCHAR(50) NOT NULL,               -- e.g. "2025/2026"
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    is_current      BOOLEAN NOT NULL DEFAULT FALSE,
    -- status: 'upcoming' | 'active' | 'completed'
    status          VARCHAR(20) NOT NULL DEFAULT 'upcoming',
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_academicyear_school_name UNIQUE (school_id, name),
    CONSTRAINT ck_academicyear_dates CHECK (end_date > start_date)
);

CREATE INDEX IF NOT EXISTS idx_academicyear_school_current
    ON academics_academicyear(school_id, is_current);
CREATE INDEX IF NOT EXISTS idx_academicyear_school_status
    ON academics_academicyear(school_id, status);

-- Only one current academic year per school (partial unique index).
CREATE UNIQUE INDEX IF NOT EXISTS uq_academicyear_one_current_per_school
    ON academics_academicyear(school_id)
    WHERE is_current = TRUE;

-- ------------------------------------------------------------
-- 2. Student Enrollment (per academic year)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS academics_studentenrollment (
    id                  BIGSERIAL PRIMARY KEY,
    school_id           BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    student_id          BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    academic_year_id    BIGINT NOT NULL REFERENCES academics_academicyear(id) ON DELETE CASCADE,
    class_id            BIGINT NOT NULL REFERENCES academics_class(id) ON DELETE CASCADE,
    -- status: 'active' | 'promoted' | 'repeating' | 'graduated'
    --         | 'withdrawn' | 'transferred'
    status              VARCHAR(20) NOT NULL DEFAULT 'active',
    promoted_from_id    BIGINT DEFAULT NULL REFERENCES academics_studentenrollment(id) ON DELETE SET NULL,
    notes               TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Prevents duplicate enrollment of the same student in the same
    -- academic year (idempotency for double-clicked promotions).
    CONSTRAINT uq_studentenrollment_student_year UNIQUE (student_id, academic_year_id)
);

CREATE INDEX IF NOT EXISTS idx_studentenrollment_school_year_class
    ON academics_studentenrollment(school_id, academic_year_id, class_id);
CREATE INDEX IF NOT EXISTS idx_studentenrollment_student_status
    ON academics_studentenrollment(student_id, status);
CREATE INDEX IF NOT EXISTS idx_studentenrollment_promoted_from
    ON academics_studentenrollment(promoted_from_id);

-- ------------------------------------------------------------
-- 3. Promotion Rules (configurable FROM -> TO class transitions)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS academics_promotionrule (
    id              BIGSERIAL PRIMARY KEY,
    school_id       BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    from_class_id   BIGINT NOT NULL REFERENCES academics_class(id) ON DELETE CASCADE,
    -- NULL to_class = terminal class: students graduate instead of moving.
    to_class_id     BIGINT DEFAULT NULL REFERENCES academics_class(id) ON DELETE SET NULL,
    -- "order" is a PostgreSQL reserved word, so the column is sort_order.
    sort_order      INTEGER NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_promotionrule_school_from_class UNIQUE (school_id, from_class_id),
    -- A class cannot promote into itself.
    CONSTRAINT ck_promotionrule_not_self CHECK (to_class_id IS NULL OR to_class_id <> from_class_id)
);

CREATE INDEX IF NOT EXISTS idx_promotionrule_school_active
    ON academics_promotionrule(school_id, is_active, sort_order);
CREATE INDEX IF NOT EXISTS idx_promotionrule_from_class
    ON academics_promotionrule(from_class_id);
CREATE INDEX IF NOT EXISTS idx_promotionrule_to_class
    ON academics_promotionrule(to_class_id);

-- ------------------------------------------------------------
-- 4. Promotion Policy (per-school, singleton)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS academics_promotionpolicy (
    id              BIGSERIAL PRIMARY KEY,
    school_id       BIGINT NOT NULL UNIQUE REFERENCES schools_school(id) ON DELETE CASCADE,
    -- mode: 'promote_all' | 'average_threshold' | 'grading_scale' | 'manual_review'
    mode            VARCHAR(30) NOT NULL DEFAULT 'promote_all',
    pass_mark       DOUBLE PRECISION NOT NULL DEFAULT 50,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_promotionpolicy_mode CHECK (
        mode IN ('promote_all', 'average_threshold', 'grading_scale', 'manual_review')
    ),
    CONSTRAINT ck_promotionpolicy_pass_mark CHECK (pass_mark >= 0 AND pass_mark <= 100)
);

-- ------------------------------------------------------------
-- 5. Promotion Batch (history of each promotion run)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS academics_promotionbatch (
    id                          BIGSERIAL PRIMARY KEY,
    school_id                   BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    source_academic_year_id     BIGINT NOT NULL REFERENCES academics_academicyear(id) ON DELETE CASCADE,
    destination_academic_year_id BIGINT NOT NULL REFERENCES academics_academicyear(id) ON DELETE CASCADE,
    created_by_id               BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    total_students              INTEGER NOT NULL DEFAULT 0,
    promoted_count              INTEGER NOT NULL DEFAULT 0,
    repeated_count              INTEGER NOT NULL DEFAULT 0,
    graduated_count             INTEGER NOT NULL DEFAULT 0,
    withdrawn_count             INTEGER NOT NULL DEFAULT 0,
    transferred_count           INTEGER NOT NULL DEFAULT 0,
    failed_count                INTEGER NOT NULL DEFAULT 0,
    skipped_count               INTEGER NOT NULL DEFAULT 0,
    -- status: 'pending' | 'in_progress' | 'completed'
    --         | 'partially_completed' | 'failed'
    status                      VARCHAR(25) NOT NULL DEFAULT 'pending',
    created_at                  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at                TIMESTAMP WITH TIME ZONE DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_promotionbatch_school_created
    ON academics_promotionbatch(school_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_promotionbatch_source_year
    ON academics_promotionbatch(source_academic_year_id);
CREATE INDEX IF NOT EXISTS idx_promotionbatch_dest_year
    ON academics_promotionbatch(destination_academic_year_id);
CREATE INDEX IF NOT EXISTS idx_promotionbatch_created_by
    ON academics_promotionbatch(created_by_id);

-- ------------------------------------------------------------
-- 6. Promotion Record (per-student outcome inside a batch)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS academics_promotionrecord (
    id                      BIGSERIAL PRIMARY KEY,
    batch_id                BIGINT NOT NULL REFERENCES academics_promotionbatch(id) ON DELETE CASCADE,
    student_id              BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    -- action: 'promote' | 'repeat' | 'graduate' | 'withdraw' | 'transfer'
    --         | 'manual_review'
    action                  VARCHAR(20) NOT NULL,
    source_enrollment_id    BIGINT DEFAULT NULL REFERENCES academics_studentenrollment(id) ON DELETE SET NULL,
    from_class_id           BIGINT DEFAULT NULL REFERENCES academics_class(id) ON DELETE SET NULL,
    to_class_id             BIGINT DEFAULT NULL REFERENCES academics_class(id) ON DELETE SET NULL,
    final_average           DOUBLE PRECISION DEFAULT NULL,
    reason                  TEXT NOT NULL DEFAULT '',
    warning                 TEXT NOT NULL DEFAULT '',
    -- status: 'success' | 'skipped' | 'failed'
    status                  VARCHAR(10) NOT NULL DEFAULT 'success',
    error_message           TEXT NOT NULL DEFAULT '',
    created_at              TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_promotionrecord_batch_status
    ON academics_promotionrecord(batch_id, status);
CREATE INDEX IF NOT EXISTS idx_promotionrecord_student
    ON academics_promotionrecord(student_id);
CREATE INDEX IF NOT EXISTS idx_promotionrecord_source_enrollment
    ON academics_promotionrecord(source_enrollment_id);

-- ------------------------------------------------------------
-- 7. updated_at triggers
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_promotion_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_academicyear_updated_at ON academics_academicyear;
CREATE TRIGGER trg_academicyear_updated_at
    BEFORE UPDATE ON academics_academicyear
    FOR EACH ROW EXECUTE FUNCTION update_promotion_updated_at();

DROP TRIGGER IF EXISTS trg_studentenrollment_updated_at ON academics_studentenrollment;
CREATE TRIGGER trg_studentenrollment_updated_at
    BEFORE UPDATE ON academics_studentenrollment
    FOR EACH ROW EXECUTE FUNCTION update_promotion_updated_at();

DROP TRIGGER IF EXISTS trg_promotionrule_updated_at ON academics_promotionrule;
CREATE TRIGGER trg_promotionrule_updated_at
    BEFORE UPDATE ON academics_promotionrule
    FOR EACH ROW EXECUTE FUNCTION update_promotion_updated_at();

DROP TRIGGER IF EXISTS trg_promotionpolicy_updated_at ON academics_promotionpolicy;
CREATE TRIGGER trg_promotionpolicy_updated_at
    BEFORE UPDATE ON academics_promotionpolicy
    FOR EACH ROW EXECUTE FUNCTION update_promotion_updated_at();

-- ------------------------------------------------------------
-- 8. Optional: backfill the current academic year's enrollments
--    from existing StudentClass assignments.
--
--    Adjust the year name/dates before running.
-- ------------------------------------------------------------
-- WITH new_year AS (
--     INSERT INTO academics_academicyear (school_id, name, start_date, end_date, is_current, status)
--     SELECT id, '2025/2026', '2025-09-01', '2026-07-31', TRUE, 'active'
--     FROM schools_school
--     ON CONFLICT (school_id, name) DO NOTHING
--     RETURNING id, school_id
-- )
-- INSERT INTO academics_studentenrollment
--     (school_id, student_id, academic_year_id, class_id, status, notes)
-- SELECT ny.school_id, sc.student_id, ny.id, sc.class_id, 'active',
--        'Backfilled from current class assignment'
-- FROM academics_studentclass sc
-- JOIN new_year ny ON ny.school_id = sc.school_id
-- WHERE sc.is_active = TRUE
-- ON CONFLICT (student_id, academic_year_id) DO NOTHING;
