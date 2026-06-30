-- SQL to create the missing messaging_personalnotice table
-- Run this in your PostgreSQL database (psql or pgAdmin)
-- Assumes standard Django naming conventions and existing schools_school and users_user tables

CREATE TABLE IF NOT EXISTS "messaging_personalnotice" (
    "id" serial NOT NULL PRIMARY KEY,
    "school_id" integer NOT NULL REFERENCES "schools_school"("id") DEFERRABLE INITIALLY DEFERRED,
    "student_id" integer NOT NULL REFERENCES "users_user"("id") DEFERRABLE INITIALLY DEFERRED,
    "created_by_id" integer REFERENCES "users_user"("id") DEFERRABLE INITIALLY DEFERRED,
    "title" varchar(255) NOT NULL,
    "content" text NOT NULL,
    "sent_at" timestamp with time zone NOT NULL,
    "created_at" timestamp with time zone NOT NULL,
    "updated_at" timestamp with time zone NOT NULL
);

-- Django ordering index
CREATE INDEX "messaging_personalnotice_sent_at_947f2a7c" ON "messaging_personalnotice" ("sent_at" DESC);

-- Additional useful indexes
CREATE INDEX "messaging_personalnotice_school_id" ON "messaging_personalnotice" ("school_id");
CREATE INDEX "messaging_personalnotice_student_id" ON "messaging_personalnotice" ("student_id");
CREATE INDEX "messaging_personalnotice_created_by_id" ON "messaging_personalnotice" ("created_by_id");

-- Update Django content_type if needed (check django_content_type for messaging.personalnotice)
INSERT INTO django_content_type (app_label, model) 
SELECT 'messaging', 'personalnotice' 
WHERE NOT EXISTS (
    SELECT 1 FROM django_content_type WHERE app_label = 'messaging' AND model = 'personalnotice'
);

-- Grant permissions to your Django DB user if needed
-- GRANT ALL ON "messaging_personalnotice" TO your_django_user;

COMMENT ON TABLE "messaging_personalnotice" IS 'Personal notices/announcements sent to individual students.';

-- Verify creation
-- SELECT * FROM "messaging_personalnotice" LIMIT 1;

