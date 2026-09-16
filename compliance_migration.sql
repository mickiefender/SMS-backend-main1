-- ============================================================
-- ALARA — SCHOOL COMPLIANCE WORKFLOW SCHEMA
--
-- Backs the school-compliance onboarding gate:
--   Super Admin creates school → school account created →
--   School Admin logs in → compliance page first →
--   school submits → Super Admin reviews → approve / reject /
--   BYPASS (individual or all) → school becomes active.
--
-- Run in Supabase SQL Editor (or psql). Idempotent (IF NOT EXISTS /
-- ON CONFLICT). NO Django migrations are used for these tables — the
-- Django models in apps/compliance pin db_table to the names below
-- (same pattern as supervisor's backend/sql/superadmin_platform.sql).
--
-- STRICT TENANT ISOLATION: every compliance row carries school_id and
-- the API always filters by the caller's school.
-- ============================================================

-- ------------------------------------------------------------
-- 0. EXTEND THE EXISTING SCHOOL RECORD
--    schools_school.status IS the school_status (single source of
--    truth). Existing values (active/suspended/inactive) are kept;
--    we only ADD the two new compliance lifecycle values and give
--    NEW rows a compliance-first default.
-- ------------------------------------------------------------
ALTER TABLE schools_school
    ADD COLUMN IF NOT EXISTS school_type        VARCHAR(30) NOT NULL DEFAULT 'combined',
    ADD COLUMN IF NOT EXISTS compliance_status  VARCHAR(30) NOT NULL DEFAULT 'not_started',
    ADD COLUMN IF NOT EXISTS approved_at        TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS approved_by_id     BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS approval_method    VARCHAR(30) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS rejected_at        TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS rejected_by_id     BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS rejection_reason   TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS suspended_at       TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS suspended_by_id    BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS suspension_reason  TEXT NOT NULL DEFAULT '';

-- New schools start compliance-pending. Existing rows keep their value.
ALTER TABLE schools_school ALTER COLUMN status SET DEFAULT 'pending_compliance';

CREATE INDEX IF NOT EXISTS idx_school_compliance_status
    ON schools_school(compliance_status);
CREATE INDEX IF NOT EXISTS idx_school_school_status
    ON schools_school(status);

-- ------------------------------------------------------------
-- 1. REQUIREMENT CATALOG (super-admin editable)
--    A "requirement" is a TYPE of thing a school must provide.
--    Each shipped school gets a per-school instance row (see table 3).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliance_requirement (
    id                      BIGSERIAL PRIMARY KEY,
    code                    VARCHAR(80) NOT NULL UNIQUE,   -- certificate_of_registration | regulatory_licence | ...
    name                    VARCHAR(255) NOT NULL,
    description             TEXT NOT NULL DEFAULT '',
    -- requirement_type: document | information | agreement
    requirement_type        VARCHAR(20) NOT NULL DEFAULT 'document',
    -- institution_types: [] = applies to every school type.
    institution_types       JSONB NOT NULL DEFAULT '[]',
    is_mandatory            BOOLEAN NOT NULL DEFAULT TRUE,
    has_expiry              BOOLEAN NOT NULL DEFAULT FALSE,
    requires_document_number BOOLEAN NOT NULL DEFAULT FALSE,
    requires_issue_date     BOOLEAN NOT NULL DEFAULT FALSE,
    -- information_schema: field definitions for requirement_type='information'
    -- e.g. [{"key":"tin","label":"Tax Identification Number","type":"text","required":true}]
    information_schema      JSONB NOT NULL DEFAULT '[]',
    -- agreement_code links a requirement to a row in compliance_agreement
    agreement_code          VARCHAR(80) DEFAULT NULL,
    sort_order              INTEGER NOT NULL DEFAULT 0,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_compliance_requirement_type CHECK (
        requirement_type IN ('document', 'information', 'agreement')
    )
);
CREATE INDEX IF NOT EXISTS idx_compliance_requirement_active
    ON compliance_requirement(is_active, sort_order);

-- ------------------------------------------------------------
-- 2. COMPLIANCE PROFILE (one per school)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliance_profile (
    id                      BIGSERIAL PRIMARY KEY,
    school_id               BIGINT NOT NULL UNIQUE REFERENCES schools_school(id) ON DELETE CASCADE,
    -- status: pending | in_progress | submitted | under_review
    --         | approved | rejected | requires_resubmission
    status                  VARCHAR(30) NOT NULL DEFAULT 'pending',
    total_requirements      INTEGER NOT NULL DEFAULT 0,
    approved_count          INTEGER NOT NULL DEFAULT 0,
    bypassed_count          INTEGER NOT NULL DEFAULT 0,
    rejected_count          INTEGER NOT NULL DEFAULT 0,
    pending_count           INTEGER NOT NULL DEFAULT 0,
    -- approval_method: fully_compliant | approved_with_overrides
    approval_method         VARCHAR(30) DEFAULT NULL,
    submitted_at            TIMESTAMPTZ DEFAULT NULL,
    review_started_at       TIMESTAMPTZ DEFAULT NULL,
    reviewed_at             TIMESTAMPTZ DEFAULT NULL,
    reviewed_by_id          BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    approved_at             TIMESTAMPTZ DEFAULT NULL,
    approved_by_id          BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    rejected_at             TIMESTAMPTZ DEFAULT NULL,
    rejected_by_id          BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    rejection_reason        TEXT NOT NULL DEFAULT '',
    last_submitted_by_id    BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    -- documents expiring: set when a renewal reminder was last raised
    renewal_notified_at     TIMESTAMPTZ DEFAULT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_compliance_profile_status CHECK (
        status IN ('pending', 'in_progress', 'submitted', 'under_review',
                   'approved', 'rejected', 'requires_resubmission')
    )
);
CREATE INDEX IF NOT EXISTS idx_compliance_profile_status
    ON compliance_profile(status, submitted_at DESC);

-- ------------------------------------------------------------
-- 3. PER-SCHOOL REQUIREMENT INSTANCE (the checklist row)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS school_compliance_requirement (
    id                      BIGSERIAL PRIMARY KEY,
    school_id               BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    profile_id              BIGINT NOT NULL REFERENCES compliance_profile(id) ON DELETE CASCADE,
    requirement_id          BIGINT NOT NULL REFERENCES compliance_requirement(id) ON DELETE CASCADE,
    -- status: not_started | in_progress | submitted | under_review
    --         | approved | rejected | bypassed | requires_resubmission
    status                  VARCHAR(30) NOT NULL DEFAULT 'not_started',
    is_applicable           BOOLEAN NOT NULL DEFAULT TRUE,  -- false when the type does not apply to this institution
    -- form information for requirement_type='information'
    information             JSONB NOT NULL DEFAULT '{}',
    -- agreement acceptance (requirement_type='agreement')
    agreement_version       VARCHAR(30) NOT NULL DEFAULT '',
    agreement_accepted_at   TIMESTAMPTZ DEFAULT NULL,
    agreement_accepted_by_id BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    -- submission / review
    submitted_at            TIMESTAMPTZ DEFAULT NULL,
    reviewed_by_id          BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    reviewed_at             TIMESTAMPTZ DEFAULT NULL,
    review_notes            TEXT NOT NULL DEFAULT '',
    rejection_reason        TEXT NOT NULL DEFAULT '',
    previous_status         VARCHAR(30) NOT NULL DEFAULT '',  -- status before the last reviewer action
    resubmission_requested_at TIMESTAMPTZ DEFAULT NULL,
    resubmission_reason     TEXT NOT NULL DEFAULT '',
    -- bypass (administrative override — NEVER the same as approved)
    bypassed_by_id          BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    bypassed_at             TIMESTAMPTZ DEFAULT NULL,
    bypass_reason           TEXT NOT NULL DEFAULT '',
    sort_order              INTEGER NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_school_compliance_requirement UNIQUE (school_id, requirement_id),
    CONSTRAINT ck_school_compliance_requirement_status CHECK (
        status IN ('not_started', 'in_progress', 'submitted', 'under_review',
                   'approved', 'rejected', 'bypassed', 'requires_resubmission')
    )
);
CREATE INDEX IF NOT EXISTS idx_school_compliance_req_school_status
    ON school_compliance_requirement(school_id, status);
CREATE INDEX IF NOT EXISTS idx_school_compliance_req_profile
    ON school_compliance_requirement(profile_id);
CREATE INDEX IF NOT EXISTS idx_school_compliance_req_requirement
    ON school_compliance_requirement(requirement_id);
-- ------------------------------------------------------------
-- 4. COMPLIANCE DOCUMENT (current document for a requirement)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliance_document (
    id                      BIGSERIAL PRIMARY KEY,
    school_id               BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    school_requirement_id   BIGINT NOT NULL REFERENCES school_compliance_requirement(id) ON DELETE CASCADE,
    file_name               VARCHAR(255) NOT NULL DEFAULT '',
    file_url                TEXT NOT NULL DEFAULT '',        -- public/signed URL
    storage_path            TEXT NOT NULL DEFAULT '',        -- bucket-relative path (for delete / re-sign)
    bucket                  VARCHAR(80) NOT NULL DEFAULT 'compliance-documents',
    mime_type               VARCHAR(120) NOT NULL DEFAULT '',
    file_size               BIGINT NOT NULL DEFAULT 0,
    document_number         VARCHAR(120) NOT NULL DEFAULT '',
    issue_date              DATE DEFAULT NULL,
    expiry_date             DATE DEFAULT NULL,
    uploaded_by_id          BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    is_current              BOOLEAN NOT NULL DEFAULT TRUE,   -- exactly one current doc per requirement
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_compliance_document_school
    ON compliance_document(school_id);
CREATE INDEX IF NOT EXISTS idx_compliance_document_req
    ON compliance_document(school_requirement_id, is_current);
-- Only one current document per school requirement.
CREATE UNIQUE INDEX IF NOT EXISTS uq_compliance_document_current
    ON compliance_document(school_requirement_id)
    WHERE is_current = TRUE;
-- Fast expiry scans for the renewal reminders.
CREATE INDEX IF NOT EXISTS idx_compliance_document_expiry
    ON compliance_document(expiry_date)
    WHERE expiry_date IS NOT NULL;

-- ------------------------------------------------------------
-- 5. COMPLIANCE DOCUMENT VERSION (immutable history)
--    Nothing is ever deleted when a document is rejected/resubmitted.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliance_document_version (
    id                      BIGSERIAL PRIMARY KEY,
    document_id             BIGINT DEFAULT NULL REFERENCES compliance_document(id) ON DELETE SET NULL,
    school_id               BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    school_requirement_id   BIGINT NOT NULL REFERENCES school_compliance_requirement(id) ON DELETE CASCADE,
    version                 INTEGER NOT NULL DEFAULT 1,
    file_name               VARCHAR(255) NOT NULL DEFAULT '',
    file_url                TEXT NOT NULL DEFAULT '',
    storage_path            TEXT NOT NULL DEFAULT '',
    bucket                  VARCHAR(80) NOT NULL DEFAULT 'compliance-documents',
    mime_type               VARCHAR(120) NOT NULL DEFAULT '',
    file_size               BIGINT NOT NULL DEFAULT 0,
    document_number         VARCHAR(120) NOT NULL DEFAULT '',
    issue_date              DATE DEFAULT NULL,
    expiry_date             DATE DEFAULT NULL,
    uploaded_by_id          BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    uploaded_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- review_status mirrors the requirement status at the time this version was reviewed
    review_status           VARCHAR(30) NOT NULL DEFAULT 'submitted',
    review_notes            TEXT NOT NULL DEFAULT '',
    replaced_at             TIMESTAMPTZ DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_compliance_doc_version_req
    ON compliance_document_version(school_requirement_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_compliance_doc_version_school
    ON compliance_document_version(school_id, uploaded_at DESC);

-- ------------------------------------------------------------
-- 6. COMPLIANCE REVIEW (one row per reviewer decision)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliance_review (
    id                      BIGSERIAL PRIMARY KEY,
    school_id               BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    profile_id              BIGINT NOT NULL REFERENCES compliance_profile(id) ON DELETE CASCADE,
    school_requirement_id   BIGINT DEFAULT NULL REFERENCES school_compliance_requirement(id) ON DELETE CASCADE,
    document_id             BIGINT DEFAULT NULL REFERENCES compliance_document(id) ON DELETE SET NULL,
    -- action: submit | approve | reject | request_resubmission | bypass
    --         | bypass_all | approve_school | reject_school | suspend
    action                  VARCHAR(30) NOT NULL,
    previous_status         VARCHAR(30) NOT NULL DEFAULT '',
    new_status              VARCHAR(30) NOT NULL DEFAULT '',
    reason                  TEXT NOT NULL DEFAULT '',
    reviewer_id             BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_compliance_review_action CHECK (
        action IN ('submit', 'approve', 'reject', 'request_resubmission', 'bypass',
                   'bypass_all', 'approve_school', 'reject_school', 'suspend')
    )
);
CREATE INDEX IF NOT EXISTS idx_compliance_review_school
    ON compliance_review(school_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_compliance_review_req
    ON compliance_review(school_requirement_id, created_at DESC);

-- ------------------------------------------------------------
-- 7. COMPLIANCE AUDIT LOG (append-only — every action)
--    SECURITY: revoke UPDATE/DELETE from the app role after creation
--    so history cannot be edited from the normal interface.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliance_audit_log (
    id                      BIGSERIAL PRIMARY KEY,
    school_id               BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    school_name             VARCHAR(255) NOT NULL DEFAULT '',   -- denormalized label for the audit feed
    requirement_id          BIGINT DEFAULT NULL REFERENCES compliance_requirement(id) ON DELETE SET NULL,
    requirement_name        VARCHAR(255) NOT NULL DEFAULT '',
    school_requirement_id   BIGINT DEFAULT NULL REFERENCES school_compliance_requirement(id) ON DELETE SET NULL,
    action                  VARCHAR(60) NOT NULL,   -- school_created | compliance_started | document_uploaded |
                                                    -- compliance_submitted | document_approved | document_rejected |
                                                    -- resubmission_requested | requirement_bypassed |
                                                    -- all_requirements_bypassed | school_approved | school_rejected |
                                                    -- school_suspended | info_requested | information_updated ...
    actor_id                BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    actor_name              VARCHAR(150) NOT NULL DEFAULT '',
    actor_role              VARCHAR(40) NOT NULL DEFAULT '',
    previous_status         VARCHAR(30) NOT NULL DEFAULT '',
    new_status              VARCHAR(30) NOT NULL DEFAULT '',
    reason                  TEXT NOT NULL DEFAULT '',
    metadata                JSONB NOT NULL DEFAULT '{}',
    ip_address              VARCHAR(64) NOT NULL DEFAULT '',
    user_agent              TEXT NOT NULL DEFAULT '',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_compliance_audit_school
    ON compliance_audit_log(school_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_compliance_audit_action
    ON compliance_audit_log(action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_compliance_audit_actor
    ON compliance_audit_log(actor_id, created_at DESC);

-- ------------------------------------------------------------
-- 8. COMPLIANCE INFORMATION REQUEST (super admin → school)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliance_information_request (
    id                      BIGSERIAL PRIMARY KEY,
    school_id               BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    school_requirement_id   BIGINT DEFAULT NULL REFERENCES school_compliance_requirement(id) ON DELETE CASCADE,
    requested_by_id         BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    title                   VARCHAR(255) NOT NULL,
    message                 TEXT NOT NULL DEFAULT '',
    -- status: open | responded | closed
    status                  VARCHAR(15) NOT NULL DEFAULT 'open',
    response                TEXT NOT NULL DEFAULT '',
    responded_by_id         BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    responded_at            TIMESTAMPTZ DEFAULT NULL,
    closed_by_id            BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    closed_at               TIMESTAMPTZ DEFAULT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_compliance_info_request_school
    ON compliance_information_request(school_id, status);

-- ------------------------------------------------------------
-- 9. AGREEMENT CATALOG
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliance_agreement (
    id                      BIGSERIAL PRIMARY KEY,
    code                    VARCHAR(80) NOT NULL UNIQUE,
    title                   VARCHAR(255) NOT NULL,
    version                 VARCHAR(30) NOT NULL DEFAULT '1.0',
    body                    TEXT NOT NULL DEFAULT '',   -- agreement text (markdown/plain)
    summary                 TEXT NOT NULL DEFAULT '',   -- short description for the UI
    is_required             BOOLEAN NOT NULL DEFAULT TRUE,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 10. AGREEMENT ACCEPTANCE (electronic signature)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliance_agreement_acceptance (
    id                      BIGSERIAL PRIMARY KEY,
    agreement_id            BIGINT NOT NULL REFERENCES compliance_agreement(id) ON DELETE CASCADE,
    school_id               BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    user_id                 BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    version                 VARCHAR(30) NOT NULL DEFAULT '1.0',
    accepted_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ip_address              VARCHAR(64) NOT NULL DEFAULT '',
    user_agent              TEXT NOT NULL DEFAULT '',
    CONSTRAINT uq_agreement_acceptance_school_version UNIQUE (agreement_id, school_id, version)
);
CREATE INDEX IF NOT EXISTS idx_agreement_acceptance_school
    ON compliance_agreement_acceptance(school_id);
-- ------------------------------------------------------------
-- 11. updated_at TRIGGERS
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_compliance_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_compliance_requirement_updated ON compliance_requirement;
CREATE TRIGGER trg_compliance_requirement_updated BEFORE UPDATE ON compliance_requirement
FOR EACH ROW EXECUTE FUNCTION update_compliance_updated_at();

DROP TRIGGER IF EXISTS trg_compliance_profile_updated ON compliance_profile;
CREATE TRIGGER trg_compliance_profile_updated BEFORE UPDATE ON compliance_profile
FOR EACH ROW EXECUTE FUNCTION update_compliance_updated_at();

DROP TRIGGER IF EXISTS trg_school_compliance_requirement_updated ON school_compliance_requirement;
CREATE TRIGGER trg_school_compliance_requirement_updated BEFORE UPDATE ON school_compliance_requirement
FOR EACH ROW EXECUTE FUNCTION update_compliance_updated_at();

DROP TRIGGER IF EXISTS trg_compliance_document_updated ON compliance_document;
CREATE TRIGGER trg_compliance_document_updated BEFORE UPDATE ON compliance_document
FOR EACH ROW EXECUTE FUNCTION update_compliance_updated_at();

DROP TRIGGER IF EXISTS trg_compliance_info_request_updated ON compliance_information_request;
CREATE TRIGGER trg_compliance_info_request_updated BEFORE UPDATE ON compliance_information_request
FOR EACH ROW EXECUTE FUNCTION update_compliance_updated_at();

DROP TRIGGER IF EXISTS trg_compliance_agreement_updated ON compliance_agreement;
CREATE TRIGGER trg_compliance_agreement_updated BEFORE UPDATE ON compliance_agreement
FOR EACH ROW EXECUTE FUNCTION update_compliance_updated_at();

-- ============================================================
-- 12. SEED DATA
-- ============================================================

-- 12a. The Alara School Agreement
INSERT INTO compliance_agreement (code, title, version, summary, body, is_required, is_active)
VALUES (
    'alara_school_agreement',
    'Alara School Agreement',
    '1.0',
    'The terms governing your school''s use of the Alara platform.',
    'ALARA SCHOOL AGREEMENT

By accepting this agreement you confirm, on behalf of your institution, that:

1. You are authorised to act on behalf of the school and to accept these terms.
2. All information and documents you submit to Alara are accurate and belong
   to your institution.
3. Your school will use Alara in accordance with applicable education,
   data-protection and child-safety regulations.
4. Alara may verify your institution''s information with the relevant
   authorities where required.
5. Alara may suspend or withdraw access if the information provided is found
   to be false or misleading.

You may withdraw acceptance at any time by contacting Alara support, which
will end your school''s access to the platform.',
    TRUE,
    TRUE
)
ON CONFLICT (code) DO NOTHING;

-- 12b. Default requirement catalog (the checklist every new school sees)
INSERT INTO compliance_requirement
    (code, name, description, requirement_type, is_mandatory, has_expiry,
     requires_document_number, requires_issue_date, information_schema,
     agreement_code, sort_order, is_active)
VALUES
    ('certificate_of_registration', 'Certificate of Registration',
     'Official certificate showing your institution is legally registered.',
     'document', TRUE, TRUE, TRUE, TRUE, '[]', NULL, 10, TRUE),

    ('regulatory_licence', 'Regulatory Licence',
     'Licence or permit issued by your national/regional education authority.',
     'document', TRUE, TRUE, TRUE, TRUE, '[]', NULL, 20, TRUE),

    ('tax_identification', 'Tax Identification',
     'Your institution''s tax identification number and issuing authority.',
     'information', TRUE, FALSE, FALSE, FALSE,
     '[{"key":"tin","label":"Tax Identification Number","type":"text","required":true},
       {"key":"issuing_authority","label":"Issuing Authority","type":"text","required":true},
       {"key":"registered_name","label":"Registered Legal Name","type":"text","required":true}]',
     NULL, 30, TRUE),

    ('authorised_representative_id', 'Authorised Representative ID',
     'Government-issued photo ID of the person authorised to represent the school.',
     'document', TRUE, TRUE, TRUE, FALSE, '[]', NULL, 40, TRUE),

    ('school_address', 'School Address',
     'The physical address of your institution, verified for accuracy.',
     'information', TRUE, FALSE, FALSE, FALSE,
     '[{"key":"street","label":"Street Address","type":"text","required":true},
       {"key":"city","label":"City / Town","type":"text","required":true},
       {"key":"region","label":"Region / State","type":"text","required":true},
       {"key":"country","label":"Country","type":"text","required":true},
       {"key":"postal_code","label":"Postal Code","type":"text","required":false}]',
     NULL, 50, TRUE),

    ('fire_safety', 'Fire/Safety Documentation',
     'Current fire-safety certificate or inspection report for the premises.',
     'document', TRUE, TRUE, FALSE, TRUE, '[]', NULL, 60, TRUE),

    ('alara_school_agreement', 'Alara School Agreement',
     'Read and electronically accept the Alara School Agreement.',
     'agreement', TRUE, FALSE, FALSE, FALSE, '[]',
     'alara_school_agreement', 70, TRUE),

    ('data_protection', 'Data Protection Documentation',
     'Evidence of your data-protection policy and registration (where required).',
     'document', FALSE, TRUE, FALSE, FALSE, '[]', NULL, 80, TRUE)
ON CONFLICT (code) DO NOTHING;

-- 12c. Platform permission codes for compliance
--      super_admin holds "*"; the granular codes are also made explicit so
--      future Compliance Officers can be granted them individually.
--      (compliance.bypass is deliberately separate: review/approve/reject
--      do NOT imply bypass.)
UPDATE platform_role
SET permissions = '["*"]'
WHERE name = 'super_admin' AND NOT (permissions @> '["*"]'::jsonb);

INSERT INTO platform_role (name, display_name, description, permissions, is_system)
VALUES (
    'compliance_officer',
    'Compliance Officer',
    'Reviews school compliance submissions. Cannot bypass requirements or approve schools unless granted the extra permissions.',
    '["compliance.view","compliance.review","compliance.reject","schools.view"]',
    TRUE
)
ON CONFLICT (name) DO NOTHING;

-- 12d. Notification types for the existing notification system
INSERT INTO notifications_type (name, slug, description, is_enabled_by_default, sort_order)
VALUES
    ('Compliance Required',        'compliance_required',        'Your school must complete compliance verification.', TRUE, 200),
    ('Compliance Submitted',       'compliance_submitted',       'Your compliance submission was received.',           TRUE, 201),
    ('Compliance Under Review',    'compliance_under_review',    'Your compliance submission is being reviewed.',      TRUE, 202),
    ('Compliance Approved',        'compliance_approved',        'A compliance requirement was approved.',             TRUE, 203),
    ('Compliance Rejected',        'compliance_rejected',        'A compliance requirement was rejected.',             TRUE, 204),
    ('Resubmission Requested',     'compliance_resubmission',    'A compliance document must be resubmitted.',         TRUE, 205),
    ('School Approved',            'school_approved',            'Your school is now fully active on Alara.',          TRUE, 206),
    ('School Rejected',            'school_rejected',            'Your school verification was rejected.',             TRUE, 207),
    ('Document Expiring',          'compliance_document_expiring','A compliance document is expiring soon.',           TRUE, 208),
    ('Compliance Renewal Required','compliance_renewal_required','A compliance document has expired.',                 TRUE, 209),
    ('New School Compliance',      'school_compliance_submitted','A school submitted compliance for review.',          TRUE, 210)
ON CONFLICT (slug) DO NOTHING;

-- ============================================================
-- 13. BACKFILL EXISTING SCHOOLS
--     Existing schools are already live, so they are NOT locked into
--     the compliance gate. We give them a profile marked approved and
--     seed their checklist from the catalog so the super-admin review
--     UI has data and no school is blocked retroactively.
--     (Idempotent: only schools without a profile are touched.)
-- ============================================================
INSERT INTO compliance_profile (school_id, status, approval_method, approved_at, total_requirements)
SELECT s.id, 'approved', NULL, NOW(),
       (SELECT COUNT(*) FROM compliance_requirement r WHERE r.is_active = TRUE)
FROM schools_school s
WHERE NOT EXISTS (SELECT 1 FROM compliance_profile p WHERE p.school_id = s.id);

UPDATE schools_school s
SET compliance_status = 'approved'
WHERE s.status = 'active'
  AND s.compliance_status = 'not_started'
  AND EXISTS (SELECT 1 FROM compliance_profile p WHERE p.school_id = s.id AND p.status = 'approved');

-- Seed per-school checklist rows for every backfilled profile.
INSERT INTO school_compliance_requirement
    (school_id, profile_id, requirement_id, status, is_applicable, sort_order)
SELECT p.school_id, p.id, r.id, 'approved', TRUE, r.sort_order
FROM compliance_profile p
JOIN compliance_requirement r ON r.is_active = TRUE
WHERE p.status = 'approved'
  AND NOT EXISTS (
      SELECT 1 FROM school_compliance_requirement scr
      WHERE scr.school_id = p.school_id AND scr.requirement_id = r.id
  );

-- ============================================================
-- 14. OPTIONAL — make the audit log truly append-only.
--     Run manually if your application role is NOT the table owner
--     (Supabase: the service role is the owner, so this is a no-op
--     there; the API never exposes an update/delete path regardless).
-- ============================================================
-- REVOKE UPDATE, DELETE ON compliance_audit_log FROM PUBLIC;
-- REVOKE UPDATE, DELETE ON compliance_review FROM PUBLIC;
-- REVOKE UPDATE, DELETE ON compliance_document_version FROM PUBLIC;
