-- Initializes the homepage FAQ setting managed from the super-admin dashboard.
INSERT INTO system_setting (
    key, category, value, is_secret, description, updated_at
)
VALUES (
    'homepage.faqs',
    'general',
    '[]'::jsonb,
    FALSE,
    'Frequently asked questions displayed on the homepage',
    NOW()
)
ON CONFLICT (key) DO NOTHING;
