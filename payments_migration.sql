-- =====================================================================================================================
-- COMPLETE FEE & PAYMENT SYSTEM DATABASE MIGRATION
-- School Management System — Full SQL for all fee/payment-related tables
-- =====================================================================================================================
--
-- This script creates ALL tables related to fee management and payments across the entire system:
--
--   SECTION 1: Core Billing System          (apps/billing)     — 6 tables
--   SECTION 2: Academic Fee Management      (apps/academics)   — 5 tables
--   SECTION 3: Paystack Payment Integration (apps/payments)    — 6 tables
--   SECTION 4: Performance Indexes
--   SECTION 5: Auto-update Triggers for updated_at
--   SECTION 6: Utility Functions
--   SECTION 7: Database Views for Reporting
--   SECTION 8: Table & Column Comments
--
-- Prerequisites: The following tables MUST already exist before running this script:
--   - schools_school (id SERIAL PK)
--   - schools_plan (id SERIAL PK)
--   - users_user (id SERIAL PK, role VARCHAR, school_id FK)
--   - academics_class (id SERIAL PK, school_id FK)
--   - academics_subject (id SERIAL PK)
--   - academics_academicsession (id SERIAL PK)
--
-- Target Database: PostgreSQL 14+ (Supabase compatible)
-- =====================================================================================================================

BEGIN;

-- =====================================================================================================================
-- SECTION 1: CORE BILLING SYSTEM (apps/billing)
-- Platform-level billing for school subscriptions and plan payments
-- =====================================================================================================================

-- 1.1 Billing Invoice — invoices for school subscription/plan payments
CREATE TABLE IF NOT EXISTS billing_invoice (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    plan_id INTEGER REFERENCES schools_plan(id) ON DELETE SET NULL,
    invoice_number VARCHAR(50) NOT NULL UNIQUE,
    amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'sent', 'paid', 'overdue', 'cancelled')),
    issued_date DATE NOT NULL DEFAULT CURRENT_DATE,
    due_date DATE NOT NULL,
    paid_date DATE,
    notes TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 1.2 Billing Payment — payments against billing invoices
CREATE TABLE IF NOT EXISTS billing_payment (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES billing_invoice(id) ON DELETE CASCADE,
    amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'completed', 'failed', 'refunded')),
    payment_method VARCHAR(50) NOT NULL,
    transaction_id VARCHAR(100) NOT NULL UNIQUE,
    paid_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 1.3 Billing Fee — predefined fee types for a school
CREATE TABLE IF NOT EXISTS billing_fee (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT DEFAULT '',
    amount DECIMAL(10, 2) NOT NULL,
    fee_type VARCHAR(20) NOT NULL DEFAULT 'academic'
        CHECK (fee_type IN ('academic', 'administrative', 'other')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_mandatory BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(school_id, name)
);

-- 1.4 School Fee Assignment — fees assigned to an entire school
CREATE TABLE IF NOT EXISTS billing_schoolfeeassignment (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    fee_id INTEGER NOT NULL REFERENCES billing_fee(id) ON DELETE CASCADE,
    amount DECIMAL(10, 2) NOT NULL,
    due_date DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(school_id, fee_id)
);

-- 1.5 Class Fee Assignment — fees assigned to entire classes
CREATE TABLE IF NOT EXISTS billing_classfeeassignment (
    id SERIAL PRIMARY KEY,
    class_obj_id INTEGER NOT NULL REFERENCES academics_class(id) ON DELETE CASCADE,
    fee_id INTEGER NOT NULL REFERENCES billing_fee(id) ON DELETE CASCADE,
    amount DECIMAL(10, 2) NOT NULL,
    due_date DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(class_obj_id, fee_id)
);

-- 1.6 Student Fee Assignment (Billing) — individual fee assigned to a student
CREATE TABLE IF NOT EXISTS billing_studentfeeassignment (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    fee_id INTEGER NOT NULL REFERENCES billing_fee(id) ON DELETE CASCADE,
    amount DECIMAL(10, 2) NOT NULL,
    due_date DATE NOT NULL,
    paid BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, fee_id)
);


-- =====================================================================================================================
-- SECTION 2: ACADEMIC FEE MANAGEMENT (apps/academics)
-- School-level fee types, class/student assignments, payments, and waivers
-- =====================================================================================================================

-- 2.1 Fee Type — define types of fees (School Fees, PTA, Transport, etc.)
CREATE TABLE IF NOT EXISTS academics_feetype (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT DEFAULT '',
    amount DECIMAL(10, 2) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_mandatory BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(school_id, name)
);

-- 2.2 Student Fee Assignment (Academic) — bulk assignment of fees to classes
CREATE TABLE IF NOT EXISTS academics_studentfeeassignment (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    fee_type_id INTEGER NOT NULL REFERENCES academics_feetype(id) ON DELETE CASCADE,
    class_obj_id INTEGER NOT NULL REFERENCES academics_class(id) ON DELETE CASCADE,
    amount DECIMAL(10, 2) NOT NULL,
    due_date DATE NOT NULL,
    description TEXT DEFAULT '',
    created_by_id INTEGER REFERENCES users_user(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fee_type_id, class_obj_id)
);

-- 2.3 Student Individual Fee — individual fee assignment to specific students
CREATE TABLE IF NOT EXISTS academics_studentindividualfee (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    fee_type_id INTEGER NOT NULL REFERENCES academics_feetype(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    class_obj_id INTEGER NOT NULL REFERENCES academics_class(id) ON DELETE CASCADE,
    amount DECIMAL(10, 2) NOT NULL,
    due_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'partial', 'paid', 'overdue')),
    description TEXT DEFAULT '',
    created_by_id INTEGER REFERENCES users_user(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fee_type_id, student_id, class_obj_id)
);

-- 2.4 Fee Payment (Academic) — track fee payments from students
CREATE TABLE IF NOT EXISTS academics_feepayment (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    individual_fee_id INTEGER NOT NULL REFERENCES academics_studentindividualfee(id) ON DELETE CASCADE,
    amount_paid DECIMAL(10, 2) NOT NULL,
    payment_date DATE NOT NULL DEFAULT CURRENT_DATE,
    payment_method VARCHAR(20) NOT NULL DEFAULT 'cash'
        CHECK (payment_method IN ('cash', 'bank_transfer', 'credit_card', 'check', 'mobile_money', 'other')),
    transaction_id VARCHAR(100) DEFAULT '',
    receipt_number VARCHAR(100) NOT NULL UNIQUE,
    notes TEXT DEFAULT '',
    recorded_by_id INTEGER REFERENCES users_user(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2.5 Fee Waiver — manage fee waivers/discounts for students
CREATE TABLE IF NOT EXISTS academics_feewaiver (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    individual_fee_id INTEGER NOT NULL REFERENCES academics_studentindividualfee(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    waiver_percentage INTEGER NOT NULL DEFAULT 100
        CHECK (waiver_percentage >= 0 AND waiver_percentage <= 100),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    approved_by_id INTEGER REFERENCES users_user(id) ON DELETE SET NULL,
    approval_date DATE,
    rejection_reason TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =====================================================================================================================
-- SECTION 3: PAYSTACK PAYMENT INTEGRATION (apps/payments)
-- Online payment processing via Paystack with invoicing, receipts, and webhook logging
-- =====================================================================================================================

-- 3.1 Fee Structure — defines fee structures for different classes/terms
CREATE TABLE IF NOT EXISTS payments_feestructure (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id INTEGER NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    class_level_id INTEGER REFERENCES academics_class(id) ON DELETE CASCADE,
    academic_year VARCHAR(20) NOT NULL,
    term VARCHAR(10) NOT NULL
        CHECK (term IN ('first', 'second', 'third')),
    name VARCHAR(255) NOT NULL,
    description TEXT DEFAULT '',
    amount DECIMAL(12, 2) NOT NULL,
    is_compulsory BOOLEAN NOT NULL DEFAULT TRUE,
    due_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(school_id, class_level_id, academic_year, term, name)
);

-- 3.2 Invoice (Paystack) — invoices generated for students for specific fees
CREATE TABLE IF NOT EXISTS payments_invoice (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_number VARCHAR(50) NOT NULL UNIQUE,
    school_id INTEGER NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    academic_year VARCHAR(20) NOT NULL,
    term VARCHAR(10) NOT NULL
        CHECK (term IN ('first', 'second', 'third')),
    status VARCHAR(20) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'sent', 'partially_paid', 'paid', 'overdue', 'cancelled')),
    total_amount DECIMAL(12, 2) NOT NULL DEFAULT 0,
    amount_paid DECIMAL(12, 2) NOT NULL DEFAULT 0,
    balance DECIMAL(12, 2) NOT NULL DEFAULT 0,
    due_date DATE,
    notes TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3.3 Invoice Item — individual line items on an invoice
CREATE TABLE IF NOT EXISTS payments_invoiceitem (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID NOT NULL REFERENCES payments_invoice(id) ON DELETE CASCADE,
    fee_structure_id UUID REFERENCES payments_feestructure(id) ON DELETE SET NULL,
    description VARCHAR(255) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL
);

-- 3.4 Payment (Paystack) — records of payments made via Paystack or offline
CREATE TABLE IF NOT EXISTS payments_payment (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID NOT NULL REFERENCES payments_invoice(id) ON DELETE CASCADE,
    school_id INTEGER NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    amount DECIMAL(12, 2) NOT NULL,
    payment_method VARCHAR(20) NOT NULL DEFAULT 'paystack'
        CHECK (payment_method IN ('paystack', 'bank_transfer', 'cash', 'cheque', 'pos', 'other')),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'success', 'failed', 'refunded', 'abandoned')),

    -- Paystack-specific fields
    paystack_reference VARCHAR(255) UNIQUE,
    paystack_access_code VARCHAR(255),
    paystack_authorization_url TEXT,
    paystack_transaction_id VARCHAR(255),
    paystack_channel VARCHAR(50),
    paystack_paid_at TIMESTAMP,
    paystack_fees DECIMAL(12, 2),

    -- General fields
    transaction_reference VARCHAR(255) NOT NULL UNIQUE,
    receipt_number VARCHAR(50) UNIQUE,
    paid_by VARCHAR(255) DEFAULT '',
    paid_by_email VARCHAR(254) DEFAULT '',
    paid_by_phone VARCHAR(20) DEFAULT '',
    notes TEXT DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}',

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3.5 Paystack Webhook Log — audit log for all Paystack webhook events
CREATE TABLE IF NOT EXISTS payments_paystackwebhooklog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    reference VARCHAR(255),
    processed BOOLEAN NOT NULL DEFAULT FALSE,
    processing_error TEXT DEFAULT '',
    ip_address INET,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3.6 Payment Receipt — generated receipts for successful payments
CREATE TABLE IF NOT EXISTS payments_paymentreceipt (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id UUID NOT NULL UNIQUE REFERENCES payments_payment(id) ON DELETE CASCADE,
    receipt_number VARCHAR(50) NOT NULL UNIQUE,
    receipt_data JSONB NOT NULL DEFAULT '{}',
    generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =====================================================================================================================
-- SECTION 4: PERFORMANCE INDEXES
-- =====================================================================================================================

-- -----------------------------------------------
-- 4.1 Billing Invoice indexes
-- -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_billing_invoice_school ON billing_invoice(school_id);
CREATE INDEX IF NOT EXISTS idx_billing_invoice_plan ON billing_invoice(plan_id);
CREATE INDEX IF NOT EXISTS idx_billing_invoice_status ON billing_invoice(status);
CREATE INDEX IF NOT EXISTS idx_billing_invoice_due_date ON billing_invoice(due_date);
CREATE INDEX IF NOT EXISTS idx_billing_invoice_issued ON billing_invoice(issued_date DESC);

-- -----------------------------------------------
-- 4.2 Billing Payment indexes
-- -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_billing_payment_invoice ON billing_payment(invoice_id);
CREATE INDEX IF NOT EXISTS idx_billing_payment_status ON billing_payment(status);
CREATE INDEX IF NOT EXISTS idx_billing_payment_created ON billing_payment(created_at DESC);

-- -----------------------------------------------
-- 4.3 Billing Fee indexes
-- -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_billing_fee_school ON billing_fee(school_id);
CREATE INDEX IF NOT EXISTS idx_billing_fee_active ON billing_fee(school_id, is_active);
CREATE INDEX IF NOT EXISTS idx_billing_fee_type ON billing_fee(fee_type);

-- -----------------------------------------------
-- 4.4 Billing Assignment indexes
-- -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_billing_schoolfee_school ON billing_schoolfeeassignment(school_id);
CREATE INDEX IF NOT EXISTS idx_billing_schoolfee_due ON billing_schoolfeeassignment(due_date);
CREATE INDEX IF NOT EXISTS idx_billing_classfee_class ON billing_classfeeassignment(class_obj_id);
CREATE INDEX IF NOT EXISTS idx_billing_classfee_due ON billing_classfeeassignment(due_date);
CREATE INDEX IF NOT EXISTS idx_billing_studentfee_student ON billing_studentfeeassignment(student_id);
CREATE INDEX IF NOT EXISTS idx_billing_studentfee_due ON billing_studentfeeassignment(due_date);
CREATE INDEX IF NOT EXISTS idx_billing_studentfee_paid ON billing_studentfeeassignment(paid);

-- -----------------------------------------------
-- 4.5 Academic Fee Type indexes
-- -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_acad_feetype_school ON academics_feetype(school_id);
CREATE INDEX IF NOT EXISTS idx_acad_feetype_active ON academics_feetype(school_id, is_active);

-- -----------------------------------------------
-- 4.6 Academic Student Fee Assignment indexes
-- -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_acad_feeassign_school ON academics_studentfeeassignment(school_id);
CREATE INDEX IF NOT EXISTS idx_acad_feeassign_feetype ON academics_studentfeeassignment(fee_type_id);
CREATE INDEX IF NOT EXISTS idx_acad_feeassign_class ON academics_studentfeeassignment(class_obj_id);
CREATE INDEX IF NOT EXISTS idx_acad_feeassign_due ON academics_studentfeeassignment(due_date);

-- -----------------------------------------------
-- 4.7 Academic Student Individual Fee indexes
-- -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_acad_indfee_school ON academics_studentindividualfee(school_id);
CREATE INDEX IF NOT EXISTS idx_acad_indfee_student ON academics_studentindividualfee(student_id);
CREATE INDEX IF NOT EXISTS idx_acad_indfee_class ON academics_studentindividualfee(class_obj_id);
CREATE INDEX IF NOT EXISTS idx_acad_indfee_status ON academics_studentindividualfee(status);
CREATE INDEX IF NOT EXISTS idx_acad_indfee_student_status ON academics_studentindividualfee(student_id, status);
CREATE INDEX IF NOT EXISTS idx_acad_indfee_due ON academics_studentindividualfee(due_date);

-- -----------------------------------------------
-- 4.8 Academic Fee Payment indexes
-- -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_acad_feepay_school ON academics_feepayment(school_id);
CREATE INDEX IF NOT EXISTS idx_acad_feepay_indfee ON academics_feepayment(individual_fee_id);
CREATE INDEX IF NOT EXISTS idx_acad_feepay_date ON academics_feepayment(payment_date DESC);
CREATE INDEX IF NOT EXISTS idx_acad_feepay_method ON academics_feepayment(payment_method);
CREATE INDEX IF NOT EXISTS idx_acad_feepay_indfee_date ON academics_feepayment(individual_fee_id, payment_date);

-- -----------------------------------------------
-- 4.9 Academic Fee Waiver indexes
-- -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_acad_waiver_school ON academics_feewaiver(school_id);
CREATE INDEX IF NOT EXISTS idx_acad_waiver_student ON academics_feewaiver(student_id);
CREATE INDEX IF NOT EXISTS idx_acad_waiver_status ON academics_feewaiver(status);
CREATE INDEX IF NOT EXISTS idx_acad_waiver_student_status ON academics_feewaiver(student_id, status);

-- -----------------------------------------------
-- 4.10 Paystack Fee Structure indexes
-- -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ps_feestructure_school ON payments_feestructure(school_id);
CREATE INDEX IF NOT EXISTS idx_ps_feestructure_class ON payments_feestructure(class_level_id);
CREATE INDEX IF NOT EXISTS idx_ps_feestructure_active ON payments_feestructure(is_active);
CREATE INDEX IF NOT EXISTS idx_ps_feestructure_year_term ON payments_feestructure(academic_year, term);
CREATE INDEX IF NOT EXISTS idx_ps_feestructure_school_year ON payments_feestructure(school_id, academic_year, term);

-- -----------------------------------------------
-- 4.11 Paystack Invoice indexes
-- -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ps_invoice_school ON payments_invoice(school_id);
CREATE INDEX IF NOT EXISTS idx_ps_invoice_student ON payments_invoice(student_id);
CREATE INDEX IF NOT EXISTS idx_ps_invoice_status ON payments_invoice(status);
CREATE INDEX IF NOT EXISTS idx_ps_invoice_year_term ON payments_invoice(academic_year, term);
CREATE INDEX IF NOT EXISTS idx_ps_invoice_created ON payments_invoice(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ps_invoice_school_student ON payments_invoice(school_id, student_id);
CREATE INDEX IF NOT EXISTS idx_ps_invoice_student_status ON payments_invoice(student_id, status);

-- -----------------------------------------------
-- 4.12 Paystack Invoice Item indexes
-- -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ps_invoiceitem_invoice ON payments_invoiceitem(invoice_id);
CREATE INDEX IF NOT EXISTS idx_ps_invoiceitem_fee ON payments_invoiceitem(fee_structure_id);

-- -----------------------------------------------
-- 4.13 Paystack Payment indexes
-- -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ps_payment_invoice ON payments_payment(invoice_id);
CREATE INDEX IF NOT EXISTS idx_ps_payment_school ON payments_payment(school_id);
CREATE INDEX IF NOT EXISTS idx_ps_payment_student ON payments_payment(student_id);
CREATE INDEX IF NOT EXISTS idx_ps_payment_status ON payments_payment(status);
CREATE INDEX IF NOT EXISTS idx_ps_payment_method ON payments_payment(payment_method);
CREATE INDEX IF NOT EXISTS idx_ps_payment_paystack_ref ON payments_payment(paystack_reference);
CREATE INDEX IF NOT EXISTS idx_ps_payment_txn_ref ON payments_payment(transaction_reference);
CREATE INDEX IF NOT EXISTS idx_ps_payment_created ON payments_payment(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ps_payment_school_status ON payments_payment(school_id, status);
CREATE INDEX IF NOT EXISTS idx_ps_payment_student_status ON payments_payment(student_id, status);

-- -----------------------------------------------
-- 4.14 Paystack Webhook Log indexes
-- -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ps_webhook_event ON payments_paystackwebhooklog(event_type);
CREATE INDEX IF NOT EXISTS idx_ps_webhook_reference ON payments_paystackwebhooklog(reference);
CREATE INDEX IF NOT EXISTS idx_ps_webhook_processed ON payments_paystackwebhooklog(processed);
CREATE INDEX IF NOT EXISTS idx_ps_webhook_created ON payments_paystackwebhooklog(created_at DESC);

-- -----------------------------------------------
-- 4.15 Paystack Receipt indexes
-- -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ps_receipt_payment ON payments_paymentreceipt(payment_id);


-- =====================================================================================================================
-- SECTION 5: AUTO-UPDATE TRIGGERS FOR updated_at
-- =====================================================================================================================

-- Generic trigger function to auto-update the updated_at column
CREATE OR REPLACE FUNCTION fn_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Billing tables
DO $$ BEGIN
    CREATE TRIGGER trg_billing_invoice_updated BEFORE UPDATE ON billing_invoice
        FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TRIGGER trg_billing_payment_updated BEFORE UPDATE ON billing_payment
        FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TRIGGER trg_billing_fee_updated BEFORE UPDATE ON billing_fee
        FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TRIGGER trg_billing_schoolfee_updated BEFORE UPDATE ON billing_schoolfeeassignment
        FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TRIGGER trg_billing_classfee_updated BEFORE UPDATE ON billing_classfeeassignment
        FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TRIGGER trg_billing_studentfee_updated BEFORE UPDATE ON billing_studentfeeassignment
        FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Academic fee tables
DO $$ BEGIN
    CREATE TRIGGER trg_acad_feetype_updated BEFORE UPDATE ON academics_feetype
        FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TRIGGER trg_acad_feeassign_updated BEFORE UPDATE ON academics_studentfeeassignment
        FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TRIGGER trg_acad_indfee_updated BEFORE UPDATE ON academics_studentindividualfee
        FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TRIGGER trg_acad_feepay_updated BEFORE UPDATE ON academics_feepayment
        FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TRIGGER trg_acad_waiver_updated BEFORE UPDATE ON academics_feewaiver
        FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Paystack payment tables
DO $$ BEGIN
    CREATE TRIGGER trg_ps_feestructure_updated BEFORE UPDATE ON payments_feestructure
        FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TRIGGER trg_ps_invoice_updated BEFORE UPDATE ON payments_invoice
        FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TRIGGER trg_ps_payment_updated BEFORE UPDATE ON payments_payment
        FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;


-- =====================================================================================================================
-- SECTION 6: UTILITY FUNCTIONS
-- =====================================================================================================================

-- 6.1 Generate a unique invoice number: INV-YYYYMMDD-XXXXXX
CREATE OR REPLACE FUNCTION fn_generate_invoice_number()
RETURNS VARCHAR AS $$
DECLARE
    v_prefix VARCHAR := 'INV';
    v_date VARCHAR;
    v_random VARCHAR;
BEGIN
    v_date := TO_CHAR(CURRENT_TIMESTAMP, 'YYYYMMDD');
    v_random := UPPER(SUBSTR(MD5(RANDOM()::TEXT), 1, 6));
    RETURN v_prefix || '-' || v_date || '-' || v_random;
END;
$$ LANGUAGE plpgsql;

-- 6.2 Generate a unique transaction reference: TXN-YYYYMMDDHHmmSS-XXXXXXXX
CREATE OR REPLACE FUNCTION fn_generate_transaction_reference()
RETURNS VARCHAR AS $$
DECLARE
    v_prefix VARCHAR := 'TXN';
    v_timestamp VARCHAR;
    v_random VARCHAR;
BEGIN
    v_timestamp := TO_CHAR(CURRENT_TIMESTAMP, 'YYYYMMDDHH24MISS');
    v_random := UPPER(SUBSTR(MD5(RANDOM()::TEXT), 1, 8));
    RETURN v_prefix || '-' || v_timestamp || '-' || v_random;
END;
$$ LANGUAGE plpgsql;

-- 6.3 Generate a unique receipt number: RCT-YYYYMMDD-XXXXXX
CREATE OR REPLACE FUNCTION fn_generate_receipt_number()
RETURNS VARCHAR AS $$
DECLARE
    v_prefix VARCHAR := 'RCT';
    v_date VARCHAR;
    v_random VARCHAR;
BEGIN
    v_date := TO_CHAR(CURRENT_TIMESTAMP, 'YYYYMMDD');
    v_random := UPPER(SUBSTR(MD5(RANDOM()::TEXT), 1, 6));
    RETURN v_prefix || '-' || v_date || '-' || v_random;
END;
$$ LANGUAGE plpgsql;

-- 6.4 Calculate invoice balance (recalculates from payments)
CREATE OR REPLACE FUNCTION fn_recalculate_invoice_balance(p_invoice_id UUID)
RETURNS DECIMAL AS $$
DECLARE
    v_total DECIMAL(12,2);
    v_paid DECIMAL(12,2);
    v_balance DECIMAL(12,2);
BEGIN
    SELECT total_amount INTO v_total
    FROM payments_invoice WHERE id = p_invoice_id;

    SELECT COALESCE(SUM(amount), 0) INTO v_paid
    FROM payments_payment
    WHERE invoice_id = p_invoice_id AND status = 'success';

    v_balance := v_total - v_paid;

    UPDATE payments_invoice
    SET amount_paid = v_paid,
        balance = v_balance,
        status = CASE
            WHEN v_paid >= v_total AND v_total > 0 THEN 'paid'
            WHEN v_paid > 0 THEN 'partially_paid'
            ELSE status
        END,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = p_invoice_id;

    RETURN v_balance;
END;
$$ LANGUAGE plpgsql;

-- 6.5 Calculate student individual fee balance (academic fees)
CREATE OR REPLACE FUNCTION fn_recalculate_individual_fee_status(p_fee_id INTEGER)
RETURNS VOID AS $$
DECLARE
    v_amount DECIMAL(10,2);
    v_paid DECIMAL(10,2);
    v_waiver_pct INTEGER;
    v_effective_amount DECIMAL(10,2);
BEGIN
    SELECT amount INTO v_amount
    FROM academics_studentindividualfee WHERE id = p_fee_id;

    -- Check for approved waivers
    SELECT COALESCE(MAX(waiver_percentage), 0) INTO v_waiver_pct
    FROM academics_feewaiver
    WHERE individual_fee_id = p_fee_id AND status = 'approved';

    v_effective_amount := v_amount * (1 - v_waiver_pct::DECIMAL / 100);

    SELECT COALESCE(SUM(amount_paid), 0) INTO v_paid
    FROM academics_feepayment
    WHERE individual_fee_id = p_fee_id;

    UPDATE academics_studentindividualfee
    SET status = CASE
            WHEN v_paid >= v_effective_amount AND v_effective_amount > 0 THEN 'paid'
            WHEN v_paid > 0 THEN 'partial'
            WHEN due_date < CURRENT_DATE THEN 'overdue'
            ELSE 'pending'
        END,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = p_fee_id;
END;
$$ LANGUAGE plpgsql;

-- 6.6 Get total fees owed by a student (academic fees)
CREATE OR REPLACE FUNCTION fn_get_student_total_fees(p_student_id INTEGER, p_school_id INTEGER)
RETURNS TABLE (
    total_assigned DECIMAL,
    total_paid DECIMAL,
    total_waived DECIMAL,
    total_outstanding DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COALESCE(SUM(sif.amount), 0)::DECIMAL AS total_assigned,
        COALESCE(SUM(fp_total.paid), 0)::DECIMAL AS total_paid,
        COALESCE(SUM(
            CASE WHEN fw.status = 'approved'
                 THEN sif.amount * fw.waiver_percentage / 100
                 ELSE 0
            END
        ), 0)::DECIMAL AS total_waived,
        (COALESCE(SUM(sif.amount), 0)
         - COALESCE(SUM(fp_total.paid), 0)
         - COALESCE(SUM(
            CASE WHEN fw.status = 'approved'
                 THEN sif.amount * fw.waiver_percentage / 100
                 ELSE 0
            END
         ), 0))::DECIMAL AS total_outstanding
    FROM academics_studentindividualfee sif
    LEFT JOIN (
        SELECT individual_fee_id, SUM(amount_paid) AS paid
        FROM academics_feepayment
        GROUP BY individual_fee_id
    ) fp_total ON fp_total.individual_fee_id = sif.id
    LEFT JOIN (
        SELECT DISTINCT ON (individual_fee_id)
            individual_fee_id, waiver_percentage, status
        FROM academics_feewaiver
        WHERE status = 'approved'
        ORDER BY individual_fee_id, created_at DESC
    ) fw ON fw.individual_fee_id = sif.id
    WHERE sif.student_id = p_student_id
      AND sif.school_id = p_school_id;
END;
$$ LANGUAGE plpgsql;

-- 6.7 Get total Paystack collections for a school
CREATE OR REPLACE FUNCTION fn_get_school_paystack_totals(
    p_school_id INTEGER,
    p_academic_year VARCHAR DEFAULT NULL,
    p_term VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    total_billed DECIMAL,
    total_collected DECIMAL,
    total_pending DECIMAL,
    total_outstanding DECIMAL,
    collection_rate DECIMAL,
    payment_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    WITH invoice_totals AS (
        SELECT
            COALESCE(SUM(total_amount), 0) AS billed,
            COALESCE(SUM(CASE WHEN status NOT IN ('paid', 'cancelled') THEN balance ELSE 0 END), 0) AS outstanding
        FROM payments_invoice
        WHERE school_id = p_school_id
          AND (p_academic_year IS NULL OR academic_year = p_academic_year)
          AND (p_term IS NULL OR term = p_term)
    ),
    payment_totals AS (
        SELECT
            COALESCE(SUM(CASE WHEN p.status = 'success' THEN p.amount ELSE 0 END), 0) AS collected,
            COALESCE(SUM(CASE WHEN p.status = 'pending' THEN p.amount ELSE 0 END), 0) AS pending_amt,
            COUNT(CASE WHEN p.status = 'success' THEN 1 END) AS pay_count
        FROM payments_payment p
        JOIN payments_invoice i ON p.invoice_id = i.id
        WHERE p.school_id = p_school_id
          AND (p_academic_year IS NULL OR i.academic_year = p_academic_year)
          AND (p_term IS NULL OR i.term = p_term)
    )
    SELECT
        it.billed::DECIMAL,
        pt.collected::DECIMAL,
        pt.pending_amt::DECIMAL,
        it.outstanding::DECIMAL,
        CASE WHEN it.billed > 0
             THEN ROUND((pt.collected / it.billed * 100), 2)
             ELSE 0
        END::DECIMAL,
        pt.pay_count
    FROM invoice_totals it, payment_totals pt;
END;
$$ LANGUAGE plpgsql;


-- =====================================================================================================================
-- SECTION 7: DATABASE VIEWS FOR REPORTING
-- =====================================================================================================================

-- 7.1 Student Paystack Balance View — shows each student's invoice balance
CREATE OR REPLACE VIEW vw_student_paystack_balance AS
SELECT
    i.student_id,
    u.first_name || ' ' || u.last_name AS student_name,
    i.school_id,
    s.name AS school_name,
    i.academic_year,
    i.term,
    COUNT(i.id) AS invoice_count,
    SUM(i.total_amount) AS total_billed,
    SUM(i.amount_paid) AS total_paid,
    SUM(i.balance) AS total_balance,
    BOOL_OR(i.status = 'overdue') AS has_overdue
FROM payments_invoice i
JOIN users_user u ON i.student_id = u.id
JOIN schools_school s ON i.school_id = s.id
WHERE i.status NOT IN ('cancelled')
GROUP BY i.student_id, u.first_name, u.last_name, i.school_id, s.name, i.academic_year, i.term;

-- 7.2 School Revenue Summary View — aggregated revenue per school
CREATE OR REPLACE VIEW vw_school_revenue_summary AS
SELECT
    p.school_id,
    s.name AS school_name,
    i.academic_year,
    i.term,
    p.payment_method,
    COUNT(p.id) AS payment_count,
    SUM(p.amount) AS total_amount,
    SUM(COALESCE(p.paystack_fees, 0)) AS total_fees,
    SUM(p.amount) - SUM(COALESCE(p.paystack_fees, 0)) AS net_amount,
    MIN(p.created_at) AS first_payment,
    MAX(p.created_at) AS last_payment
FROM payments_payment p
JOIN payments_invoice i ON p.invoice_id = i.id
JOIN schools_school s ON p.school_id = s.id
WHERE p.status = 'success'
GROUP BY p.school_id, s.name, i.academic_year, i.term, p.payment_method;

-- 7.3 Overdue Invoices View — all overdue invoices with student details
CREATE OR REPLACE VIEW vw_overdue_invoices AS
SELECT
    i.id AS invoice_id,
    i.invoice_number,
    i.student_id,
    u.first_name || ' ' || u.last_name AS student_name,
    u.email AS student_email,
    i.school_id,
    s.name AS school_name,
    i.academic_year,
    i.term,
    i.total_amount,
    i.amount_paid,
    i.balance,
    i.due_date,
    CURRENT_DATE - i.due_date AS days_overdue,
    i.created_at
FROM payments_invoice i
JOIN users_user u ON i.student_id = u.id
JOIN schools_school s ON i.school_id = s.id
WHERE i.status IN ('sent', 'partially_paid', 'overdue')
  AND i.due_date < CURRENT_DATE
  AND i.balance > 0
ORDER BY (CURRENT_DATE - i.due_date) DESC;

-- 7.4 Academic Fee Summary View — student fee status across academic fee system
CREATE OR REPLACE VIEW vw_academic_fee_summary AS
SELECT
    sif.student_id,
    u.first_name || ' ' || u.last_name AS student_name,
    sif.school_id,
    s.name AS school_name,
    sif.class_obj_id,
    c.name AS class_name,
    ft.name AS fee_type_name,
    sif.amount AS fee_amount,
    sif.due_date,
    sif.status,
    COALESCE(pay_totals.total_paid, 0) AS total_paid,
    sif.amount - COALESCE(pay_totals.total_paid, 0) AS balance,
    COALESCE(waiver_info.waiver_percentage, 0) AS waiver_percentage,
    waiver_info.waiver_status
FROM academics_studentindividualfee sif
JOIN users_user u ON sif.student_id = u.id
JOIN schools_school s ON sif.school_id = s.id
JOIN academics_class c ON sif.class_obj_id = c.id
JOIN academics_feetype ft ON sif.fee_type_id = ft.id
LEFT JOIN (
    SELECT individual_fee_id, SUM(amount_paid) AS total_paid
    FROM academics_feepayment
    GROUP BY individual_fee_id
) pay_totals ON pay_totals.individual_fee_id = sif.id
LEFT JOIN (
    SELECT DISTINCT ON (individual_fee_id)
        individual_fee_id,
        waiver_percentage,
        status AS waiver_status
    FROM academics_feewaiver
    ORDER BY individual_fee_id, created_at DESC
) waiver_info ON waiver_info.individual_fee_id = sif.id
ORDER BY sif.school_id, sif.student_id, sif.due_date;

-- 7.5 Daily Payment Report View — payments grouped by day
CREATE OR REPLACE VIEW vw_daily_payment_report AS
SELECT
    p.school_id,
    s.name AS school_name,
    DATE(p.created_at) AS payment_date,
    p.payment_method,
    COUNT(p.id) AS transaction_count,
    SUM(p.amount) AS total_amount,
    SUM(COALESCE(p.paystack_fees, 0)) AS total_paystack_fees,
    SUM(p.amount) - SUM(COALESCE(p.paystack_fees, 0)) AS net_amount
FROM payments_payment p
JOIN schools_school s ON p.school_id = s.id
WHERE p.status = 'success'
GROUP BY p.school_id, s.name, DATE(p.created_at), p.payment_method
ORDER BY DATE(p.created_at) DESC, p.school_id;

-- 7.6 Webhook Activity View — recent webhook events with processing status
CREATE OR REPLACE VIEW vw_webhook_activity AS
SELECT
    wl.id,
    wl.event_type,
    wl.reference,
    wl.processed,
    wl.processing_error,
    wl.ip_address,
    wl.created_at,
    p.id AS payment_id,
    p.status AS payment_status,
    p.amount AS payment_amount
FROM payments_paystackwebhooklog wl
LEFT JOIN payments_payment p ON (
    p.paystack_reference = wl.reference
    OR p.transaction_reference = wl.reference
)
ORDER BY wl.created_at DESC;

-- 7.7 Combined Fee Overview — unified view across billing + academic + paystack fees for a student
CREATE OR REPLACE VIEW vw_student_combined_fees AS
-- Academic individual fees
SELECT
    'academic' AS fee_source,
    sif.student_id,
    u.first_name || ' ' || u.last_name AS student_name,
    sif.school_id,
    ft.name AS fee_name,
    sif.amount,
    COALESCE(ap.total_paid, 0) AS amount_paid,
    sif.amount - COALESCE(ap.total_paid, 0) AS balance,
    sif.due_date,
    sif.status,
    sif.created_at
FROM academics_studentindividualfee sif
JOIN users_user u ON sif.student_id = u.id
JOIN academics_feetype ft ON sif.fee_type_id = ft.id
LEFT JOIN (
    SELECT individual_fee_id, SUM(amount_paid) AS total_paid
    FROM academics_feepayment GROUP BY individual_fee_id
) ap ON ap.individual_fee_id = sif.id

UNION ALL

-- Paystack invoices
SELECT
    'paystack' AS fee_source,
    i.student_id,
    u.first_name || ' ' || u.last_name AS student_name,
    i.school_id,
    'Invoice ' || i.invoice_number AS fee_name,
    i.total_amount AS amount,
    i.amount_paid,
    i.balance,
    i.due_date,
    i.status,
    i.created_at
FROM payments_invoice i
JOIN users_user u ON i.student_id = u.id
WHERE i.status != 'cancelled'

UNION ALL

-- Billing student fee assignments
SELECT
    'billing' AS fee_source,
    bsfa.student_id,
    u.first_name || ' ' || u.last_name AS student_name,
    bf.school_id,
    bf.name AS fee_name,
    bsfa.amount,
    CASE WHEN bsfa.paid THEN bsfa.amount ELSE 0 END AS amount_paid,
    CASE WHEN bsfa.paid THEN 0 ELSE bsfa.amount END AS balance,
    bsfa.due_date,
    CASE WHEN bsfa.paid THEN 'paid' ELSE 'pending' END AS status,
    bsfa.created_at
FROM billing_studentfeeassignment bsfa
JOIN users_user u ON bsfa.student_id = u.id
JOIN billing_fee bf ON bsfa.fee_id = bf.id;


-- =====================================================================================================================
-- SECTION 8: TABLE & COLUMN COMMENTS
-- =====================================================================================================================

-- Billing tables
COMMENT ON TABLE billing_invoice IS 'Platform-level invoices for school subscription/plan payments';
COMMENT ON TABLE billing_payment IS 'Payments against platform billing invoices';
COMMENT ON TABLE billing_fee IS 'Predefined fee types for a school (academic, administrative, other)';
COMMENT ON TABLE billing_schoolfeeassignment IS 'Fees assigned to an entire school';
COMMENT ON TABLE billing_classfeeassignment IS 'Fees assigned to entire classes';
COMMENT ON TABLE billing_studentfeeassignment IS 'Individual billing fees assigned to specific students';

-- Academic fee tables
COMMENT ON TABLE academics_feetype IS 'School-level fee type definitions (School Fees, PTA, Transport, etc.)';
COMMENT ON TABLE academics_studentfeeassignment IS 'Bulk assignment of academic fees to classes';
COMMENT ON TABLE academics_studentindividualfee IS 'Individual academic fee assignments to specific students with status tracking';
COMMENT ON TABLE academics_feepayment IS 'Payment records for academic student fees with receipt tracking';
COMMENT ON TABLE academics_feewaiver IS 'Fee waiver/discount requests and approvals for students';

-- Paystack payment tables
COMMENT ON TABLE payments_feestructure IS 'Fee structures for different classes/terms — used to generate Paystack invoices';
COMMENT ON TABLE payments_invoice IS 'Student invoices for Paystack payment processing';
COMMENT ON TABLE payments_invoiceitem IS 'Individual line items on a Paystack invoice';
COMMENT ON TABLE payments_payment IS 'Payment records — Paystack online and offline payments with full transaction details';
COMMENT ON TABLE payments_paystackwebhooklog IS 'Audit log for all incoming Paystack webhook events';
COMMENT ON TABLE payments_paymentreceipt IS 'Auto-generated receipts for successful payments';

-- Key column comments
COMMENT ON COLUMN payments_payment.paystack_reference IS 'Paystack-assigned transaction reference';
COMMENT ON COLUMN payments_payment.paystack_access_code IS 'Paystack access code for inline payment widget';
COMMENT ON COLUMN payments_payment.paystack_authorization_url IS 'Redirect URL for Paystack hosted payment page';
COMMENT ON COLUMN payments_payment.paystack_fees IS 'Paystack processing fees in Naira (converted from kobo)';
COMMENT ON COLUMN payments_payment.transaction_reference IS 'System-generated unique transaction reference (TXN-...)';
COMMENT ON COLUMN payments_payment.metadata IS 'Arbitrary JSON metadata attached to the payment';
COMMENT ON COLUMN payments_invoice.balance IS 'Computed: total_amount - amount_paid';
COMMENT ON COLUMN academics_feewaiver.waiver_percentage IS 'Percentage of fee to waive (0-100)';
COMMENT ON COLUMN academics_feepayment.receipt_number IS 'Unique receipt number for this payment record';

-- View comments
COMMENT ON VIEW vw_student_paystack_balance IS 'Per-student Paystack invoice balance summary by academic year/term';
COMMENT ON VIEW vw_school_revenue_summary IS 'Aggregated school revenue by academic year, term, and payment method';
COMMENT ON VIEW vw_overdue_invoices IS 'All overdue Paystack invoices with days overdue calculation';
COMMENT ON VIEW vw_academic_fee_summary IS 'Student academic fee status with payment and waiver details';
COMMENT ON VIEW vw_daily_payment_report IS 'Daily payment totals grouped by school and payment method';
COMMENT ON VIEW vw_webhook_activity IS 'Paystack webhook events with linked payment status';
COMMENT ON VIEW vw_student_combined_fees IS 'Unified view of all fees (academic + paystack + billing) for each student';

-- Function comments
COMMENT ON FUNCTION fn_update_timestamp() IS 'Generic trigger function to auto-set updated_at to CURRENT_TIMESTAMP';
COMMENT ON FUNCTION fn_generate_invoice_number() IS 'Generate unique invoice number in format INV-YYYYMMDD-XXXXXX';
COMMENT ON FUNCTION fn_generate_transaction_reference() IS 'Generate unique transaction reference in format TXN-YYYYMMDDHHmmSS-XXXXXXXX';
COMMENT ON FUNCTION fn_generate_receipt_number() IS 'Generate unique receipt number in format RCT-YYYYMMDD-XXXXXX';
COMMENT ON FUNCTION fn_recalculate_invoice_balance(UUID) IS 'Recalculate and update a Paystack invoice balance from its successful payments';
COMMENT ON FUNCTION fn_recalculate_individual_fee_status(INTEGER) IS 'Recalculate academic individual fee status considering payments and waivers';
COMMENT ON FUNCTION fn_get_student_total_fees(INTEGER, INTEGER) IS 'Get total academic fees summary (assigned, paid, waived, outstanding) for a student';
COMMENT ON FUNCTION fn_get_school_paystack_totals(INTEGER, VARCHAR, VARCHAR) IS 'Get school-level Paystack collection totals with optional year/term filter';

COMMIT;

-- =====================================================================================================================
-- USAGE EXAMPLES
-- =====================================================================================================================
--
-- 1. Recalculate a Paystack invoice balance:
--    SELECT fn_recalculate_invoice_balance('a1b2c3d4-...');
--
-- 2. Get student total academic fees:
--    SELECT * FROM fn_get_student_total_fees(42, 1);
--
-- 3. Get school Paystack totals for a specific term:
--    SELECT * FROM fn_get_school_paystack_totals(1, '2025/2026', 'first');
--
-- 4. View all overdue invoices:
--    SELECT * FROM vw_overdue_invoices WHERE school_id = 1;
--
-- 5. View combined fees for a student:
--    SELECT * FROM vw_student_combined_fees WHERE student_id = 42 ORDER BY due_date;
--
-- 6. Daily payment report:
--    SELECT * FROM vw_daily_payment_report WHERE school_id = 1 AND payment_date >= CURRENT_DATE - INTERVAL '30 days';
--
-- 7. Generate references:
--    SELECT fn_generate_invoice_number();    -- e.g. INV-20260302-A3F1B2
--    SELECT fn_generate_transaction_reference(); -- e.g. TXN-20260302143022-B7C4D1E9
--    SELECT fn_generate_receipt_number();    -- e.g. RCT-20260302-E8F2A1
--
-- =====================================================================================================================
