-- =====================================================
-- PAYSTACK PAYMENT SYSTEM TABLES
-- Run this SQL to add the Paystack payment tables
-- =====================================================

-- Fee Structure Table
CREATE TABLE IF NOT EXISTS payments_feestructure (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id INTEGER NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    class_level_id INTEGER REFERENCES academics_class(id) ON DELETE CASCADE,
    academic_year VARCHAR(20) NOT NULL,
    term VARCHAR(10) NOT NULL CHECK (term IN ('first', 'second', 'third')),
    name VARCHAR(255) NOT NULL,
    description TEXT DEFAULT '',
    amount DECIMAL(12, 2) NOT NULL,
    is_compulsory BOOLEAN DEFAULT TRUE,
    due_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(school_id, class_level_id, academic_year, term, name)
);

-- Invoice Table
CREATE TABLE IF NOT EXISTS payments_invoice (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_number VARCHAR(50) NOT NULL UNIQUE,
    school_id INTEGER NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    academic_year VARCHAR(20) NOT NULL,
    term VARCHAR(10) NOT NULL CHECK (term IN ('first', 'second', 'third')),
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'sent', 'partially_paid', 'paid', 'overdue', 'cancelled')),
    total_amount DECIMAL(12, 2) DEFAULT 0,
    amount_paid DECIMAL(12, 2) DEFAULT 0,
    balance DECIMAL(12, 2) DEFAULT 0,
    due_date DATE,
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Invoice Item Table
CREATE TABLE IF NOT EXISTS payments_invoiceitem (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID NOT NULL REFERENCES payments_invoice(id) ON DELETE CASCADE,
    fee_structure_id UUID REFERENCES payments_feestructure(id) ON DELETE SET NULL,
    description VARCHAR(255) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL
);

-- Payment Table
CREATE TABLE IF NOT EXISTS payments_payment (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID NOT NULL REFERENCES payments_invoice(id) ON DELETE CASCADE,
    school_id INTEGER NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    amount DECIMAL(12, 2) NOT NULL,
    payment_method VARCHAR(20) DEFAULT 'paystack' CHECK (payment_method IN ('paystack', 'bank_transfer', 'cash', 'cheque', 'pos', 'other')),
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'success', 'failed', 'refunded', 'abandoned')),

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
    metadata JSONB DEFAULT '{}',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Paystack Webhook Log Table
CREATE TABLE IF NOT EXISTS payments_paystackwebhooklog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    reference VARCHAR(255),
    processed BOOLEAN DEFAULT FALSE,
    processing_error TEXT DEFAULT '',
    ip_address INET,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Payment Receipt Table
CREATE TABLE IF NOT EXISTS payments_paymentreceipt (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id UUID NOT NULL UNIQUE REFERENCES payments_payment(id) ON DELETE CASCADE,
    receipt_number VARCHAR(50) NOT NULL UNIQUE,
    receipt_data JSONB DEFAULT '{}',
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- INDEXES FOR PERFORMANCE
-- =====================================================

-- Fee Structure indexes
CREATE INDEX IF NOT EXISTS idx_feestructure_school ON payments_feestructure(school_id);
CREATE INDEX IF NOT EXISTS idx_feestructure_class ON payments_feestructure(class_level_id);
CREATE INDEX IF NOT EXISTS idx_feestructure_active ON payments_feestructure(is_active);
CREATE INDEX IF NOT EXISTS idx_feestructure_year_term ON payments_feestructure(academic_year, term);

-- Invoice indexes
CREATE INDEX IF NOT EXISTS idx_invoice_school ON payments_invoice(school_id);
CREATE INDEX IF NOT EXISTS idx_invoice_student ON payments_invoice(student_id);
CREATE INDEX IF NOT EXISTS idx_invoice_status ON payments_invoice(status);
CREATE INDEX IF NOT EXISTS idx_invoice_year_term ON payments_invoice(academic_year, term);
CREATE INDEX IF NOT EXISTS idx_invoice_created ON payments_invoice(created_at DESC);

-- Invoice Item indexes
CREATE INDEX IF NOT EXISTS idx_invoiceitem_invoice ON payments_invoiceitem(invoice_id);
CREATE INDEX IF NOT EXISTS idx_invoiceitem_fee ON payments_invoiceitem(fee_structure_id);

-- Payment indexes
CREATE INDEX IF NOT EXISTS idx_payment_invoice ON payments_payment(invoice_id);
CREATE INDEX IF NOT EXISTS idx_payment_school ON payments_payment(school_id);
CREATE INDEX IF NOT EXISTS idx_payment_student ON payments_payment(student_id);
CREATE INDEX IF NOT EXISTS idx_payment_status ON payments_payment(status);
CREATE INDEX IF NOT EXISTS idx_payment_method ON payments_payment(payment_method);
CREATE INDEX IF NOT EXISTS idx_payment_paystack_ref ON payments_payment(paystack_reference);
CREATE INDEX IF NOT EXISTS idx_payment_txn_ref ON payments_payment(transaction_reference);
CREATE INDEX IF NOT EXISTS idx_payment_created ON payments_payment(created_at DESC);

-- Webhook Log indexes
CREATE INDEX IF NOT EXISTS idx_webhook_event ON payments_paystackwebhooklog(event_type);
CREATE INDEX IF NOT EXISTS idx_webhook_reference ON payments_paystackwebhooklog(reference);
CREATE INDEX IF NOT EXISTS idx_webhook_processed ON payments_paystackwebhooklog(processed);
CREATE INDEX IF NOT EXISTS idx_webhook_created ON payments_paystackwebhooklog(created_at DESC);

-- Receipt indexes
CREATE INDEX IF NOT EXISTS idx_receipt_payment ON payments_paymentreceipt(payment_id);

-- =====================================================
-- TABLE COMMENTS
-- =====================================================

COMMENT ON TABLE payments_feestructure IS 'Defines fee structures for different classes/terms';
COMMENT ON TABLE payments_invoice IS 'Invoices generated for students for specific fees';
COMMENT ON TABLE payments_invoiceitem IS 'Individual line items on an invoice';
COMMENT ON TABLE payments_payment IS 'Records of payments made via Paystack or offline';
COMMENT ON TABLE payments_paystackwebhooklog IS 'Audit log for all Paystack webhook events';
COMMENT ON TABLE payments_paymentreceipt IS 'Generated receipts for successful payments';
