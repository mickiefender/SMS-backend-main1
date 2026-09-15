-- Subscription plan setup for Alara
-- PostgreSQL
--
-- Existing tables:
--   schools_plan
--   schools_school
--   schools_subscription
--
-- The plan names are stored as slugs. The application displays them as:
--   starter  -> Starter
--   standard -> Standard
--   premium  -> Premium

BEGIN;

-- Migrate the old plan names if they exist.
UPDATE schools_plan
SET name = 'standard'
WHERE name = 'professional'
  AND NOT EXISTS (
    SELECT 1 FROM schools_plan WHERE name = 'standard'
  );

UPDATE schools_plan
SET name = 'premium'
WHERE name = 'enterprise'
  AND NOT EXISTS (
    SELECT 1 FROM schools_plan WHERE name = 'premium'
  );

-- If both an old and new row exist, move references before removing the
-- duplicate legacy row.
DO $$
DECLARE
  old_plan_id bigint;
  replacement_plan_id bigint;
BEGIN
  SELECT id INTO old_plan_id FROM schools_plan WHERE name = 'professional' LIMIT 1;
  SELECT id INTO replacement_plan_id FROM schools_plan WHERE name = 'standard' LIMIT 1;
  IF old_plan_id IS NOT NULL AND replacement_plan_id IS NOT NULL THEN
    UPDATE schools_school SET plan_id = replacement_plan_id WHERE plan_id = old_plan_id;
    UPDATE schools_subscription SET plan_id = replacement_plan_id WHERE plan_id = old_plan_id;
    DELETE FROM schools_plan WHERE id = old_plan_id;
  END IF;

  SELECT id INTO old_plan_id FROM schools_plan WHERE name = 'enterprise' LIMIT 1;
  SELECT id INTO replacement_plan_id FROM schools_plan WHERE name = 'premium' LIMIT 1;
  IF old_plan_id IS NOT NULL AND replacement_plan_id IS NOT NULL THEN
    UPDATE schools_school SET plan_id = replacement_plan_id WHERE plan_id = old_plan_id;
    UPDATE schools_subscription SET plan_id = replacement_plan_id WHERE plan_id = old_plan_id;
    DELETE FROM schools_plan WHERE id = old_plan_id;
  END IF;
END $$;

-- Create the three supported plans when they do not already exist.
INSERT INTO schools_plan (
  name,
  description,
  price,
  max_students,
  max_teachers,
  max_classes,
  features,
  is_active,
  created_at,
  updated_at
)
VALUES
  (
    'starter',
    'Starter subscription',
    0,
    100,
    20,
    10,
    '[]'::jsonb,
    TRUE,
    NOW(),
    NOW()
  ),
  (
    'standard',
    'Standard subscription',
    0,
    500,
    50,
    30,
    '[]'::jsonb,
    TRUE,
    NOW(),
    NOW()
  ),
  (
    'premium',
    'Premium subscription',
    0,
    2000,
    200,
    100,
    '[]'::jsonb,
    TRUE,
    NOW(),
    NOW()
  )
ON CONFLICT (name) DO UPDATE
SET is_active = TRUE,
    updated_at = NOW();

COMMIT;

-- Example: assign a plan and duration to one school.
-- Replace the IDs and dates before running. This resets the subscription
-- start date and makes the plan visible to the school admin immediately.
--
-- BEGIN;
--
-- UPDATE schools_school
-- SET plan_id = (SELECT id FROM schools_plan WHERE name = 'standard'),
--     subscription_start = CURRENT_DATE,
--     subscription_end = CURRENT_DATE + 365,
--     updated_at = NOW()
-- WHERE id = 123;
--
-- INSERT INTO schools_subscription (
--   school_id,
--   plan_id,
--   status,
--   start_date,
--   end_date,
--   auto_renew,
--   created_at,
--   updated_at
-- )
-- VALUES (
--   123,
--   (SELECT id FROM schools_plan WHERE name = 'standard'),
--   'active',
--   CURRENT_DATE,
--   CURRENT_DATE + 365,
--   FALSE,
--   NOW(),
--   NOW()
-- )
-- ON CONFLICT (school_id) DO UPDATE
-- SET plan_id = EXCLUDED.plan_id,
--     status = 'active',
--     start_date = EXCLUDED.start_date,
--     end_date = EXCLUDED.end_date,
--     updated_at = NOW();
--
-- COMMIT;
