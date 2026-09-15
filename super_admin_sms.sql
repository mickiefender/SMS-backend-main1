-- Super-admin SMS setup for Alara
-- PostgreSQL / Supabase
--
-- Run backend/sms_migration.sql before this script.
-- Super-admin sending uses the existing school-scoped SMS tables. This script
-- only initializes missing rows and adds indexes needed by the platform view.

BEGIN;

-- Every school needs an SMS configuration before it can receive an approved
-- Sender ID or send a platform message.
INSERT INTO messaging_smsconfiguration (
    school_id,
    sender_id,
    sender_id_status,
    rejection_reason,
    is_enabled
)
SELECT
    s.id,
    '',
    'pending',
    '',
    FALSE
FROM schools_school s
WHERE NOT EXISTS (
    SELECT 1
    FROM messaging_smsconfiguration c
    WHERE c.school_id = s.id
);

-- Every school needs a balance row so super-admin credit allocation and
-- balance checks are atomic and consistent.
INSERT INTO messaging_smsbalance (school_id, credits)
SELECT s.id, 0
FROM schools_school s
WHERE NOT EXISTS (
    SELECT 1
    FROM messaging_smsbalance b
    WHERE b.school_id = s.id
);

CREATE INDEX IF NOT EXISTS messaging_smsconfiguration_status_school_idx
    ON messaging_smsconfiguration (sender_id_status, school_id);

CREATE INDEX IF NOT EXISTS messaging_smsjob_school_status_created_idx
    ON messaging_smsjob (school_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS messaging_smsmessage_school_status_created_idx
    ON messaging_smsmessage (school_id, status, created_at DESC);

COMMIT;

-- -------------------------------------------------------------------------
-- Optional operational statements
-- -------------------------------------------------------------------------
-- Approve a Sender ID after it has been reviewed by the platform team:
--
-- UPDATE messaging_smsconfiguration
-- SET sender_id_status = 'approved',
--     is_enabled = TRUE,
--     rejection_reason = '',
--     updated_at = NOW()
-- WHERE school_id = 123
--   AND sender_id = 'STMARYS';
--
-- Allocate SMS credits to a school. Replace 123 and 1000 as appropriate:
--
-- BEGIN;
-- SELECT id
-- FROM schools_school
-- WHERE id = 123
-- FOR UPDATE;
--
-- INSERT INTO messaging_smsbalance (school_id, credits)
-- VALUES (123, 0)
-- ON CONFLICT (school_id) DO NOTHING;
--
-- UPDATE messaging_smsbalance
-- SET credits = credits + 1000,
--     updated_at = NOW()
-- WHERE school_id = 123
-- RETURNING credits;
--
-- INSERT INTO messaging_smscreditledger (
--     school_id, amount, balance_after, reason, actor_id
-- )
-- SELECT school_id, 1000, credits, 'admin_adjustment', NULL
-- FROM messaging_smsbalance
-- WHERE school_id = 123;
-- COMMIT;
--
-- Review messages sent by the super-admin:
--
-- SELECT
--     m.id,
--     s.name AS school,
--     m.recipient,
--     m.message,
--     m.status,
--     m.credits_used,
--     m.created_at
-- FROM messaging_smsmessage m
-- JOIN schools_school s ON s.id = m.school_id
-- ORDER BY m.created_at DESC;
