-- Targeted notices & announcements:
-- 1. M2M tables for individually selected recipients (students AND teachers)
-- 2. priority column on announcements

CREATE TABLE IF NOT EXISTS messaging_announcement_recipients (
    id BIGSERIAL PRIMARY KEY,
    announcement_id BIGINT NOT NULL REFERENCES messaging_announcement(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    UNIQUE(announcement_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_ann_recipients_announcement ON messaging_announcement_recipients(announcement_id);
CREATE INDEX IF NOT EXISTS idx_ann_recipients_user ON messaging_announcement_recipients(user_id);

CREATE TABLE IF NOT EXISTS messaging_notice_recipients (
    id BIGSERIAL PRIMARY KEY,
    notice_id BIGINT NOT NULL REFERENCES messaging_notice(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    UNIQUE(notice_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_notice_recipients_notice ON messaging_notice_recipients(notice_id);
CREATE INDEX IF NOT EXISTS idx_notice_recipients_user ON messaging_notice_recipients(user_id);

ALTER TABLE messaging_announcement
    ADD COLUMN IF NOT EXISTS priority VARCHAR(10) NOT NULL DEFAULT 'medium';
