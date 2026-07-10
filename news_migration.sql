-- ============================================================
-- News Table Migration
-- Allows school admins to create, manage, and publish news items
-- with banner images that display on student/teacher dashboards.
-- ============================================================

-- Create the news table
CREATE TABLE IF NOT EXISTS news (
    id              BIGSERIAL PRIMARY KEY,
    school_id       BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    title           VARCHAR(500) NOT NULL,
    excerpt         TEXT NOT NULL DEFAULT '',
    content         TEXT NOT NULL DEFAULT '',
    category        VARCHAR(100) NOT NULL DEFAULT 'Announcements',
    audience        VARCHAR(50) NOT NULL DEFAULT 'all',
    -- audience values: 'all', 'students', 'teachers', 'parents', 'staff'
    
    banner_image_url TEXT DEFAULT NULL,
    -- image uploaded to Supabase 'news-banners' bucket
    
    is_published    BOOLEAN NOT NULL DEFAULT TRUE,
    is_banner       BOOLEAN NOT NULL DEFAULT FALSE,
    -- When TRUE, this news item appears in the rotating banner/carousel
    
    created_by_id   BIGINT DEFAULT NULL REFERENCES users_user(id) ON DELETE SET NULL,
    published_at    TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_news_school_published
    ON news(school_id, is_published DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_news_school_banner
    ON news(school_id, is_banner DESC, created_at DESC)
    WHERE is_banner = TRUE AND is_published = TRUE;

CREATE INDEX IF NOT EXISTS idx_news_audience
    ON news(audience);

CREATE INDEX IF NOT EXISTS idx_news_category
    ON news(category);

CREATE INDEX IF NOT EXISTS idx_news_created_by
    ON news(created_by_id);

-- Trigger to auto-set updated_at
CREATE OR REPLACE FUNCTION update_news_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_news_updated_at ON news;
CREATE TRIGGER trg_news_updated_at
    BEFORE UPDATE ON news
    FOR EACH ROW
    EXECUTE FUNCTION update_news_updated_at();

-- Trigger to auto-set published_at when first published
CREATE OR REPLACE FUNCTION set_news_published_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_published = TRUE AND OLD.is_published = FALSE THEN
        NEW.published_at = NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_news_published_at ON news;
CREATE TRIGGER trg_news_published_at
    BEFORE UPDATE ON news
    FOR EACH ROW
    EXECUTE FUNCTION set_news_published_at();

-- ============================================================
-- Supabase Storage Bucket (run in Supabase SQL Editor)
-- ============================================================
-- Note: Buckets must be created via Supabase dashboard or API.
-- Run the following in your Supabase SQL Editor to create the bucket:

-- INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
-- VALUES (
--     'news-banners',
--     'news-banners',
--     TRUE,
--     5242880,  -- 5 MB
--     ARRAY['image/jpeg', 'image/png', 'image/webp', 'image/gif']
-- );

-- -- Storage policy: Allow authenticated uploads (school admins)
-- CREATE POLICY "School admins can upload news banners"
-- ON storage.objects FOR INSERT
-- TO authenticated
-- WITH CHECK (
--     bucket_id = 'news-banners'
--     AND (auth.role() = 'authenticated')
-- );

-- -- Storage policy: Public read access for news banners
-- CREATE POLICY "Public can view news banners"
-- ON storage.objects FOR SELECT
-- TO public
-- USING (bucket_id = 'news-banners');

-- -- Storage policy: Authenticated users can update their banners
-- CREATE POLICY "Authenticated users can update news banners"
-- ON storage.objects FOR UPDATE
-- TO authenticated
-- USING (bucket_id = 'news-banners');

-- -- Storage policy: Authenticated users can delete their banners
-- CREATE POLICY "Authenticated users can delete news banners"
-- ON storage.objects FOR DELETE
-- TO authenticated
-- USING (bucket_id = 'news-banners');
