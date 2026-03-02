-- =====================================================
-- ACADEMIC SESSION AND TERMINAL REPORTS TABLES
-- Run this SQL to add the new grading system tables
-- =====================================================

-- Academic Session Table
CREATE TABLE IF NOT EXISTS academics_academicsession (
    id SERIAL PRIMARY KEY,
    school_id INTEGER REFERENCES schools_school(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    term INTEGER NOT NULL CHECK (term IN (1, 2, 3, 4)),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_current BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(school_id, name)
);

-- Terminal Report Table
CREATE TABLE IF NOT EXISTS academics_terminalreport (
    id SERIAL PRIMARY KEY,
    school_id INTEGER REFERENCES schools_school(id) ON DELETE CASCADE,
    student_id INTEGER REFERENCES users_user(id) ON DELETE CASCADE,
    class_obj_id INTEGER REFERENCES academics_class(id) ON DELETE CASCADE,
    academic_session_id INTEGER REFERENCES academics_academicsession(id) ON DELETE CASCADE,
    total_marks FLOAT DEFAULT 0,
    average_marks FLOAT DEFAULT 0,
    position INTEGER,
    total_students INTEGER DEFAULT 0,
    grade VARCHAR(5) DEFAULT '',
    total_days INTEGER DEFAULT 0,
    days_present INTEGER DEFAULT 0,
    attendance_percentage FLOAT DEFAULT 0,
    form_teacher_remarks TEXT DEFAULT '',
    principal_remarks TEXT DEFAULT '',
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
    generated_by_id INTEGER REFERENCES users_user(id) ON DELETE SET NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, class_obj_id, academic_session_id)
);

-- Subject Score Table
CREATE TABLE IF NOT EXISTS academics_subjectscore (
    id SERIAL PRIMARY KEY,
    terminal_report_id INTEGER REFERENCES academics_terminalreport(id) ON DELETE CASCADE,
    subject_id INTEGER REFERENCES academics_subject(id) ON DELETE CASCADE,
    ca1_score FLOAT,
    ca2_score FLOAT,
    ca3_score FLOAT,
    exam_score FLOAT,
    total_score FLOAT DEFAULT 0,
    percentage FLOAT DEFAULT 0,
    grade VARCHAR(5) DEFAULT '',
    remarks VARCHAR(100) DEFAULT '',
    subject_position INTEGER,
    subject_total_students INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(terminal_report_id, subject_id)
);

-- Add indexes for better performance
CREATE INDEX IF NOT EXISTS idx_academicsession_school ON academics_academicsession(school_id);
CREATE INDEX IF NOT EXISTS idx_academicsession_current ON academics_academicsession(is_current);
CREATE INDEX IF NOT EXISTS idx_terminalreport_student ON academics_terminalreport(student_id);
CREATE INDEX IF NOT EXISTS idx_terminalreport_class ON academics_terminalreport(class_obj_id);
CREATE INDEX IF NOT EXISTS idx_terminalreport_session ON academics_terminalreport(academic_session_id);
CREATE INDEX IF NOT EXISTS idx_terminalreport_status ON academics_terminalreport(status);
CREATE INDEX IF NOT EXISTS idx_subjectscore_terminal ON academics_subjectscore(terminal_report_id);
CREATE INDEX IF NOT EXISTS idx_subjectscore_subject ON academics_subjectscore(subject_id);

-- Add foreign key indexes
CREATE INDEX IF NOT EXISTS idx_terminalreport_school_fk ON academics_terminalreport(school_id);
CREATE INDEX IF NOT EXISTS idx_terminalreport_class_fk ON academics_terminalreport(class_obj_id);
CREATE INDEX IF NOT EXISTS idx_terminalreport_session_fk ON academics_terminalreport(academic_session_id);
CREATE INDEX IF NOT EXISTS idx_terminalreport_generated_fk ON academics_terminalreport(generated_by_id);

COMMENT ON TABLE academics_academicsession IS 'Academic sessions/terms (e.g., "First Term 2024", "Second Term 2024")';
COMMENT ON TABLE academics_terminalreport IS 'Computed terminal reports for students';
COMMENT ON TABLE academics_subjectscore IS 'Subject-wise scores for terminal reports';

-- Sample data for testing (optional)
-- INSERT INTO academics_academicsession (school_id, name, term, start_date, end_date, is_current) 
-- VALUES (1, 'First Term 2024', 1, '2024-01-01', '2024-03-31', true);

