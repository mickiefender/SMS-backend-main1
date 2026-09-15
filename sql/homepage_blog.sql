-- Initialize the public blog setting used by the homepage/blog APIs.
INSERT INTO system_setting (key, category, description, value)
VALUES (
  'homepage.blog_posts',
  'content',
  'Blog posts displayed on the public website',
  '[]'::jsonb
)
ON CONFLICT (key) DO NOTHING;
