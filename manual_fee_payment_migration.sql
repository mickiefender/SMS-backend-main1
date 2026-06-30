-- Manual Fee Payment Migration SQL
-- Run this SQL to add the new billing tables and fields

-- 1. Add new fields to StudentFeeAssignment table
ALTER TABLE billing_studentfeeassignment 
ADD COLUMN IF NOT EXISTS amount_paid DECIMAL(10, 2) DEFAULT 0;

ALTER TABLE billing_studentfeeassignment 
ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'pending';

-- 2. Create ManualPayment table
CREATE TABLE IF NOT EXISTS billing_manualpayment (
    id SERIAL PRIMARY KEY,
    school_id INTEGER NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    fee_assignment_id INTEGER NOT NULL REFERENCES billing_studentfeeassignment(id) ON DELETE CASCADE,
    amount DECIMAL(10, 2) NOT NULL,
    payment_method VARCHAR(20) NOT NULL DEFAULT 'cash',
    receipt_number VARCHAR(100) UNIQUE,
    notes TEXT,
    recorded_by_id INTEGER REFERENCES users_user(id) ON DELETE SET NULL,
    payment_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. Create indexes for ManualPayment
CREATE INDEX IF NOT EXISTS idx_manualpayment_student_payment_date 
ON billing_manualpayment(student_id, payment_date);

CREATE INDEX IF NOT EXISTS idx_manualpayment_receipt_number 
ON billing_manualpayment(receipt_number);

-- 4. Create index for status on StudentFeeAssignment
CREATE INDEX IF NOT EXISTS idx_studentfeeassignment_status 
ON billing_studentfeeassignment(status);

-- 5. Create index for amount_paid
CREATE INDEX IF NOT EXISTS idx_studentfeeassignment_amount_paid 
ON billing_studentfeeassignment(amount_paid);

