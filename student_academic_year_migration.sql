-- ============================================================
-- Student "Current Academic Year" Migration
--
-- Adds users_studentprofile.academic_year_id so every student is tied to an
-- academic year (auto-set at onboarding, editable by a school admin from the
-- student detail page), and backfills existing students with their school's
-- current academic year.
--
-- Run in Supabase SQL Editor (or psql). Safe to re-run: every statement is
-- guarded with IF NOT EXISTS / idempotent WHERE clauses.
-- ============================================================

-- ------------------------------------------------------------
-- 1. Add the column (FK -> academics_academicyear, nullable)
-- ------------------------------------------------------------
ALTER TABLE users_studentprofile
    ADD COLUMN IF NOT EXISTS academic_year_id BIGINT DEFAULT NULL;

ALTER TABLE users_studentprofile
    DROP CONSTRAINT IF EXISTS fk_studentprofile_academic_year;

ALTER TABLE users_studentprofile
    ADD CONSTRAINT fk_studentprofile_academic_year
    FOREIGN KEY (academic_year_id)
    REFERENCES academics_academicyear(id)
    ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_studentprofile_academic_year
    ON users_studentprofile(academic_year_id);

-- ------------------------------------------------------------
-- 2. Backfill existing students with their school's CURRENT year.
--
--    Prefers the year flagged is_current; falls back to the most recent year
--    still marked 'active' (same rule the API uses). Students who already have
--    a year set are left untouched.
-- ------------------------------------------------------------
UPDATE users_studentprofile sp
SET academic_year_id = (
    SELECT ay.id
    FROM academics_academicyear ay
    WHERE ay.school_id = u.school_id
    ORDER BY ay.is_current DESC, ay.start_date DESC
    LIMIT 1
)
FROM users_user u
WHERE u.id = sp.user_id
  AND sp.academic_year_id IS NULL
  AND u.school_id IS NOT NULL
  AND EXISTS (
      SELECT 1 FROM academics_academicyear ay
      WHERE ay.school_id = u.school_id
  );

-- ------------------------------------------------------------
-- 3. Backfill year-based enrollments for students who are already in a class,
--    so the promotion views and the per-year history reflect the backfilled
--    academic year instead of showing nothing.
--
--    Only creates a row when the student has an active class and does not
--    already have an enrollment for that year.
-- ------------------------------------------------------------
INSERT INTO academics_studentenrollment
    (school_id, student_id, academic_year_id, class_id, status, notes)
SELECT
    sp_user.school_id,
    sc.student_id,
    sp.academic_year_id,
    sc.class_obj_id,
    'active',
    'Backfilled from current class assignment'
FROM academics_studentclass sc
JOIN users_studentprofile sp ON sp.user_id = sc.student_id
JOIN users_user sp_user ON sp_user.id = sp.user_id
WHERE sc.is_active = TRUE
  AND sp.academic_year_id IS NOT NULL
  AND sp_user.school_id IS NOT NULL
ON CONFLICT (student_id, academic_year_id) DO NOTHING;
