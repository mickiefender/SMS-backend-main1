-- Stores the homepage trusted-school logo list.
-- Logo binaries are uploaded through:
-- POST /api/platform/trusted-schools/upload/
-- and the JSON value stores their public storage URLs.

INSERT INTO system_setting (
    key,
    category,
    value,
    is_secret,
    description,
    updated_at
)
VALUES (
    'homepage.trusted_schools',
    'branding',
    '[]'::jsonb,
    FALSE,
    'School logos displayed in the homepage trusted schools section',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

-- Example shape after an upload:
-- UPDATE system_setting
-- SET value = '[
--   {"id": 1, "name": "Example Academy", "logo": "https://.../trusted-schools/logo.png"}
-- ]'::jsonb,
-- updated_at = NOW()
-- WHERE key = 'homepage.trusted_schools';
