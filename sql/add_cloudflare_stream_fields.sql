-- =============================================================================
-- Cloudflare Stream Migration
-- =============================================================================
-- Replaces the old Supabase video upload/storage flow with Cloudflare Stream.
--
-- Adds Cloudflare-specific fields to feed_feedlesson so videos are stored
-- and streamed exclusively through Cloudflare Stream — no more MP4 downloads
-- from Supabase Storage.
--
-- To apply:
--   psql "$DATABASE_URL" -f backend/sql/add_cloudflare_stream_fields.sql
-- =============================================================================

-- 1. Add Cloudflare Stream columns to feed_feedlesson
ALTER TABLE feed_feedlesson
    ADD COLUMN IF NOT EXISTS cloudflare_video_uid      VARCHAR(255) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS cloudflare_playback_url   VARCHAR(1000) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS cloudflare_thumbnail_url  VARCHAR(1000) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS video_duration            DOUBLE PRECISION NOT NULL DEFAULT 0.0;

-- 2. Add index on cloudflare_video_uid for fast lookups
CREATE INDEX IF NOT EXISTS idx_feedlesson_cloudflare_video_uid
    ON feed_feedlesson(cloudflare_video_uid)
    WHERE cloudflare_video_uid != '';

COMMENT ON COLUMN feed_feedlesson.cloudflare_video_uid      IS 'Unique video identifier returned by Cloudflare Stream API';
COMMENT ON COLUMN feed_feedlesson.cloudflare_playback_url   IS 'HLS or DASH manifest URL for video playback via Cloudflare Stream';
COMMENT ON COLUMN feed_feedlesson.cloudflare_thumbnail_url  IS 'Auto-generated thumbnail URL from Cloudflare Stream';
COMMENT ON COLUMN feed_feedlesson.video_duration            IS 'Video duration in seconds (float) as reported by Cloudflare Stream';
