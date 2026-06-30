-- TERMINAL REPORT TEMPLATES MIGRATION
-- Run this SQL to add customizable template support for terminal reports

-- Template table
CREATE TABLE IF NOT EXISTS academics_terminalreporttemplate (
    id SERIAL PRIMARY KEY,
    school_id INTEGER REFERENCES schools_school(id) ON DELETE CASCADE,
    academic_session_id INTEGER REFERENCES academics_academicsession(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    structure JSONB DEFAULT '[]'::jsonb,
    is_active BOOLEAN DEFAULT true,
    is_default BOOLEAN DEFAULT false,
    preview_data JSONB DEFAULT '{}'::jsonb,
    created_by_id INTEGER REFERENCES auth_user(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_terminalreporttemplate_school ON academics_terminalreporttemplate(school_id);
CREATE INDEX IF NOT EXISTS idx_terminalreporttemplate_session ON academics_terminalreporttemplate(academic_session_id);
CREATE INDEX IF NOT EXISTS idx_terminalreporttemplate_active ON academics_terminalreporttemplate(is_active);
CREATE INDEX IF NOT EXISTS idx_terminalreporttemplate_default ON academics_terminalreporttemplate(is_default);
CREATE UNIQUE INDEX IF NOT EXISTS idx_terminalreporttemplate_unique_name ON academics_terminalreporttemplate(school_id, name);

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_academics_terminalreporttemplate_updated_at 
    BEFORE UPDATE ON academics_terminalreporttemplate 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Default template data (optional - insert sample data)
INSERT INTO academics_terminalreporttemplate (school_id, name, structure, is_default) VALUES 
(1, 'Standard Report', '[
  {"type": "header", "logo": true, "school_name": true, "address": true, "session": true},
  {"type": "student_info", "fields": ["name", "class", "roll_no"]},
  {"type": "attendance", "show": true},
  {"type": "subjects_table", "columns": ["subject", "score", "percentage", "grade"]},
  {"type": "summary", "show": true},
  {"type": "remarks", "form_teacher": true, "principal": true},
  {"type": "footer", "signature": true}
]', true)
ON CONFLICT (school_id, name) DO NOTHING;

COMMENT ON TABLE academics_terminalreporttemplate IS 'Customizable templates for terminal reports - school admin designed';

