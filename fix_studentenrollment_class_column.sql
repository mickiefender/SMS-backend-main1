-- ============================================================
-- FIX: academics_studentenrollment.class_id NOT NULL violation
--
-- WHY THIS FAILS
-- --------------
-- The table was first bootstrapped by raw SQL in
-- `backend/promotion_migration.sql`, which created a NOT NULL
-- column named `class_id`:
--
--     class_id  BIGINT NOT NULL REFERENCES academics_class(id)
--
-- Later the Django model declared the SAME relationship with a
-- different field name:
--
--     class_obj = models.ForeignKey('Class', ...)
--
-- whose database column is `class_obj_id` (added afterwards and
-- left NULLABLE). The live table now carries BOTH columns:
--
--     class_id       | NOT NULL |  <- raw-SQL column (never filled by the ORM)
--     class_obj_id   | NULL     |  <- column the Django ORM writes
--
-- So every StudentEnrollment the ORM inserts sets `class_obj_id`
-- and leaves `class_id` empty, and PostgreSQL rejects it with:
--
--     null value in column "class_id" of relation
--     "academics_studentenrollment" violates not-null constraint
--
-- That single bad INSERT is what blew up student promotion (and
-- the class-assignment enrollment sync) mid-batch.
--
-- THE FIX (no data dropped)
-- -------------------------
--   1. Backfill each class column from the other for existing rows.
--   2. Install a BEFORE INSERT/UPDATE trigger so the two columns can
--      never drift again:
--        * the ORM writes `class_obj_id`  -> trigger mirrors it into `class_id`
--        * legacy raw SQL writes `class_id` -> trigger mirrors it into `class_obj_id`
--
-- Safe to re-run: every statement is idempotent.
-- Run in the Supabase SQL editor (or psql) against the application DB.
-- ============================================================

-- ------------------------------------------------------------
-- 1. Backfill existing rows so the two columns agree.
-- ------------------------------------------------------------
UPDATE academics_studentenrollment
SET class_obj_id = class_id
WHERE class_obj_id IS NULL
  AND class_id IS NOT NULL;

UPDATE academics_studentenrollment
SET class_id = class_obj_id
WHERE class_id IS NULL
  AND class_obj_id IS NOT NULL;

-- ------------------------------------------------------------
-- 2. Keep both columns in step on every future write.
--
--    `class_obj_id` wins when present (that is the column the
--    Django ORM writes); when it is absent we copy `class_id`
--    across instead, so raw-SQL inserts keep working and stay
--    NOT NULL-valid.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION sync_studentenrollment_class_column()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.class_obj_id IS NOT NULL THEN
        NEW.class_id := NEW.class_obj_id;
    ELSIF NEW.class_id IS NOT NULL THEN
        NEW.class_obj_id := NEW.class_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_studentenrollment_sync_class_column
    ON academics_studentenrollment;

CREATE TRIGGER trg_studentenrollment_sync_class_column
    BEFORE INSERT OR UPDATE ON academics_studentenrollment
    FOR EACH ROW
    EXECUTE FUNCTION sync_studentenrollment_class_column();

-- ------------------------------------------------------------
-- 3. Verification — both queries must return 0.
-- ------------------------------------------------------------
-- Rows still missing the ORM column (should be 0):
-- SELECT count(*) AS missing_class_obj FROM academics_studentenrollment
--   WHERE class_obj_id IS NULL;
-- Rows still missing the NOT NULL raw column (should be 0):
-- SELECT count(*) AS missing_class FROM academics_studentenrollment
--   WHERE class_id IS NULL;
