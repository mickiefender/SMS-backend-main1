-- FIXED SQL: Create billing_onlinepayment table for Django (Supabase-compatible)
-- Run in Supabase SQL Editor. Checks prerequisites first.

-- 0. PREREQUISITES CHECK
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'schools_school') THEN
    RAISE EXCEPTION 'Missing prerequisite: schools_school table';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users_user') THEN
    RAISE EXCEPTION 'Missing prerequisite: users_user table';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'billing_studentfeeassignment') THEN
    RAISE EXCEPTION 'Missing prerequisite: billing_studentfeeassignment table';
  END IF;
END $$;

-- 1. DROP if exists (clean slate)
DROP TABLE IF EXISTS billing_onlinepayment CASCADE;

-- 2. CREATE TABLE (exact Django OnlinePayment match)
CREATE TABLE billing_onlinepayment (
    id BIGSERIAL PRIMARY KEY,
    school_id BIGINT NOT NULL REFERENCES public.schools_school(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    student_id BIGINT NOT NULL REFERENCES public.users_user(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    fee_assignment_id BIGINT REFERENCES public.billing_studentfeeassignment(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    amount NUMERIC(10,2) NOT NULL,
    payment_method VARCHAR(50) NOT NULL DEFAULT 'paystack',
    transaction_id VARCHAR(100) NOT NULL UNIQUE,
    reference VARCHAR(100) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'success', 'failed')),
    receipt_number VARCHAR(100) NOT NULL UNIQUE,
    notes TEXT,
    channel VARCHAR(50),
    currency VARCHAR(10) NOT NULL DEFAULT 'GHS',
    paid_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- 3. INDEXES (no CONCURRENTLY needed for new table)
CREATE INDEX idx_billing_onlinepayment_student_created ON billing_onlinepayment (student_id, created_at);
CREATE INDEX idx_billing_onlinepayment_reference ON billing_onlinepayment (reference);
CREATE INDEX idx_billing_onlinepayment_status ON billing_onlinepayment (status);

-- 4. updated_at TRIGGER (safe)
DROP FUNCTION IF EXISTS update_billing_onlinepayment_updated_at() CASCADE;
CREATE OR REPLACE FUNCTION update_billing_onlinepayment_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_billing_onlinepayment_updated_at ON billing_onlinepayment;
CREATE TRIGGER trg_billing_onlinepayment_updated_at
    BEFORE UPDATE ON billing_onlinepayment
    FOR EACH ROW EXECUTE FUNCTION update_billing_onlinepayment_updated_at();

-- 5. GRANTS (Supabase RLS compatible)
GRANT ALL ON billing_onlinepayment TO postgres, authenticated, anon;
GRANT USAGE, SELECT ON SEQUENCE billing_onlinepayment_id_seq TO postgres, authenticated, anon;

-- 6. COMMENTS
COMMENT ON TABLE billing_onlinepayment IS 'Django: Track online payments made via Paystack';
COMMENT ON COLUMN billing_onlinepayment.student_id IS 'FK: users_user (role=student)';

-- 7. VERIFY
SELECT 'Table created successfully!' AS status, 
       COUNT(*) AS row_count 
FROM billing_onlinepayment;

-- USAGE: Test Django endpoint after running this
