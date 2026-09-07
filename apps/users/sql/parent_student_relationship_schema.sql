-- Parent accounts use the existing users_user table with role = 'parent'.
-- Run this script once in the Supabase/PostgreSQL SQL editor.

CREATE TABLE IF NOT EXISTS users_parentstudentrelationship (
    id BIGSERIAL PRIMARY KEY,
    relationship_type VARCHAR(20) NOT NULL DEFAULT 'guardian'
        CHECK (relationship_type IN ('mother', 'father', 'guardian', 'other')),
    status VARCHAR(20) NOT NULL DEFAULT 'approved'
        CHECK (status IN ('pending', 'approved', 'revoked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_id BIGINT NULL
        REFERENCES users_user(id) ON DELETE SET NULL,
    parent_id BIGINT NOT NULL
        REFERENCES users_user(id) ON DELETE CASCADE,
    student_id BIGINT NOT NULL
        REFERENCES users_user(id) ON DELETE CASCADE,
    CONSTRAINT unique_parent_student_relationship UNIQUE (parent_id, student_id)
);

CREATE INDEX IF NOT EXISTS users_parentstudentrelationship_parent_status_idx
    ON users_parentstudentrelationship (parent_id, status);

CREATE INDEX IF NOT EXISTS users_parentstudentrelationship_student_status_idx
    ON users_parentstudentrelationship (student_id, status);

CREATE OR REPLACE FUNCTION update_parentstudentrelationship_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS users_parentstudentrelationship_updated_at
    ON users_parentstudentrelationship;

CREATE TRIGGER users_parentstudentrelationship_updated_at
BEFORE UPDATE ON users_parentstudentrelationship
FOR EACH ROW
EXECUTE FUNCTION update_parentstudentrelationship_updated_at();

-- Prevent invalid account roles at the database boundary.
CREATE OR REPLACE FUNCTION validate_parentstudentrelationship_users()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    parent_role VARCHAR(20);
    student_role VARCHAR(20);
    parent_school_id BIGINT;
    student_school_id BIGINT;
BEGIN
    SELECT role, school_id INTO parent_role, parent_school_id
    FROM users_user WHERE id = NEW.parent_id;

    SELECT role, school_id INTO student_role, student_school_id
    FROM users_user WHERE id = NEW.student_id;

    IF parent_role IS DISTINCT FROM 'parent' THEN
        RAISE EXCEPTION 'parent_id must reference a user with role parent';
    END IF;

    IF student_role IS DISTINCT FROM 'student' THEN
        RAISE EXCEPTION 'student_id must reference a user with role student';
    END IF;

    IF parent_school_id IS DISTINCT FROM student_school_id THEN
        RAISE EXCEPTION 'parent and student must belong to the same school';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS users_parentstudentrelationship_validate_users
    ON users_parentstudentrelationship;

CREATE TRIGGER users_parentstudentrelationship_validate_users
BEFORE INSERT OR UPDATE OF parent_id, student_id ON users_parentstudentrelationship
FOR EACH ROW
EXECUTE FUNCTION validate_parentstudentrelationship_users();
