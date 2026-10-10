-- PostgreSQL schema for the Django library app.
-- Requires the existing schools_school, academics_class, and users_user tables.
-- In normal deployments, apply the Django migration instead:
--   python manage.py migrate library

BEGIN;

CREATE TABLE IF NOT EXISTS library_category (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    school_id BIGINT NOT NULL REFERENCES schools_school (id) ON DELETE CASCADE,
    CONSTRAINT library_category_school_name_uniq UNIQUE (school_id, name)
);

CREATE TABLE IF NOT EXISTS library_book (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    author VARCHAR(255) NOT NULL DEFAULT '',
    isbn VARCHAR(32) NOT NULL DEFAULT '',
    total_copies INTEGER NOT NULL DEFAULT 1 CHECK (total_copies >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    category_id BIGINT REFERENCES library_category (id) ON DELETE RESTRICT,
    school_id BIGINT NOT NULL REFERENCES schools_school (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS library_book_school_title_idx
    ON library_book (school_id, title);

CREATE TABLE IF NOT EXISTS library_loan (
    id BIGSERIAL PRIMARY KEY,
    issued_at DATE NOT NULL,
    due_date DATE NOT NULL,
    returned_at DATE,
    created_at TIMESTAMPTZ NOT NULL,
    book_id BIGINT NOT NULL REFERENCES library_book (id) ON DELETE RESTRICT,
    class_obj_id BIGINT REFERENCES academics_class (id) ON DELETE SET NULL,
    issued_by_id BIGINT REFERENCES users_user (id) ON DELETE SET NULL,
    school_id BIGINT NOT NULL REFERENCES schools_school (id) ON DELETE CASCADE,
    student_id BIGINT NOT NULL REFERENCES users_user (id) ON DELETE RESTRICT,
    CONSTRAINT library_loan_due_after_issue CHECK (due_date >= issued_at)
);

CREATE INDEX IF NOT EXISTS library_loan_school_due_idx
    ON library_loan (school_id, returned_at, due_date);

CREATE INDEX IF NOT EXISTS library_loan_book_active_idx
    ON library_loan (book_id, returned_at);

COMMIT;
