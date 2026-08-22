-- =============================================================================
-- Staff Activity Log — Database Migration (run manually, no Django migration)
--
-- Creates the table backing core.models.StaffActivityLog:
--   core_staff_activity_log
--
-- The admin-staff dashboard reads this table to render the real
-- "This Week's Activity" bar chart and the Recent Activity list.
-- =============================================================================

CREATE TABLE IF NOT EXISTS core_staff_activity_log (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    action_type     VARCHAR(20) NOT NULL DEFAULT 'task'
                        CHECK (action_type IN ('task', 'approval')),
    title           VARCHAR(255) NOT NULL,
    path            VARCHAR(500) NOT NULL DEFAULT '',
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Per-user timeline lookups (dashboard: weekly chart + recent activity)
CREATE INDEX IF NOT EXISTS idx_staff_activity_user_created
    ON core_staff_activity_log (user_id, created_at DESC);

-- Action-type breakdowns (tasks vs approvals per day)
CREATE INDEX IF NOT EXISTS idx_staff_activity_action_created
    ON core_staff_activity_log (action_type, created_at DESC);

-- Housekeeping: keep 180 days of history
CREATE OR REPLACE FUNCTION staff_activity_cleanup_old()
RETURNS void AS $$
BEGIN
    DELETE FROM core_staff_activity_log
    WHERE created_at < NOW() - INTERVAL '180 days';
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------
-- Verify the table was created
-- ---------------------------------------------------------------
DO $$
DECLARE
    tbl_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO tbl_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'core_staff_activity_log';

    IF tbl_count = 0 THEN
        RAISE WARNING 'core_staff_activity_log was NOT created';
    ELSE
        RAISE NOTICE 'core_staff_activity_log created successfully';
    END IF;
END;
$$;
