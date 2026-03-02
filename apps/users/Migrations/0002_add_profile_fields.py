from django.db import migrations


class Migration(migrations.Migration):
    """
    Adds extended profile fields to TeacherProfile and StudentProfile.
    Uses IF NOT EXISTS so the migration is safe to run even if the
    student_teacher_profiles_setup.sql script was already executed directly
    against the database.
    """

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        # ── TeacherProfile extra fields ──────────────────────────────────
        migrations.RunSQL(
            sql="""
                ALTER TABLE users_teacherprofile
                    ADD COLUMN IF NOT EXISTS gender          VARCHAR(10)  DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS date_of_birth   DATE         DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS address         TEXT         NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS specialization  VARCHAR(255) NOT NULL DEFAULT '';
            """,
            reverse_sql="""
                ALTER TABLE users_teacherprofile
                    DROP COLUMN IF EXISTS gender,
                    DROP COLUMN IF EXISTS date_of_birth,
                    DROP COLUMN IF EXISTS address,
                    DROP COLUMN IF EXISTS specialization;
            """,
            state_operations=[
                migrations.AddField(
                    model_name='teacherprofile',
                    name='gender',
                    field=__import__('django.db.models', fromlist=['CharField']).CharField(
                        max_length=10,
                        choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')],
                        blank=True,
                        null=True,
                    ),
                ),
                migrations.AddField(
                    model_name='teacherprofile',
                    name='date_of_birth',
                    field=__import__('django.db.models', fromlist=['DateField']).DateField(
                        null=True, blank=True,
                    ),
                ),
                migrations.AddField(
                    model_name='teacherprofile',
                    name='address',
                    field=__import__('django.db.models', fromlist=['TextField']).TextField(blank=True),
                ),
                migrations.AddField(
                    model_name='teacherprofile',
                    name='specialization',
                    field=__import__('django.db.models', fromlist=['CharField']).CharField(
                        max_length=255, blank=True,
                    ),
                ),
            ],
        ),

        # ── StudentProfile extra fields ───────────────────────────────────
        migrations.RunSQL(
            sql="""
                ALTER TABLE users_studentprofile
                    ADD COLUMN IF NOT EXISTS gender           VARCHAR(10)  DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS father_name      VARCHAR(255) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS mother_name      VARCHAR(255) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS religion         VARCHAR(100) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS father_occupation VARCHAR(255) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS address          TEXT         NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS roll_number      VARCHAR(50)  NOT NULL DEFAULT '';
            """,
            reverse_sql="""
                ALTER TABLE users_studentprofile
                    DROP COLUMN IF EXISTS gender,
                    DROP COLUMN IF EXISTS father_name,
                    DROP COLUMN IF EXISTS mother_name,
                    DROP COLUMN IF EXISTS religion,
                    DROP COLUMN IF EXISTS father_occupation,
                    DROP COLUMN IF EXISTS address,
                    DROP COLUMN IF EXISTS roll_number;
            """,
            state_operations=[
                migrations.AddField(
                    model_name='studentprofile',
                    name='gender',
                    field=__import__('django.db.models', fromlist=['CharField']).CharField(
                        max_length=10,
                        choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')],
                        blank=True,
                        null=True,
                    ),
                ),
                migrations.AddField(
                    model_name='studentprofile',
                    name='father_name',
                    field=__import__('django.db.models', fromlist=['CharField']).CharField(
                        max_length=255, blank=True,
                    ),
                ),
                migrations.AddField(
                    model_name='studentprofile',
                    name='mother_name',
                    field=__import__('django.db.models', fromlist=['CharField']).CharField(
                        max_length=255, blank=True,
                    ),
                ),
                migrations.AddField(
                    model_name='studentprofile',
                    name='religion',
                    field=__import__('django.db.models', fromlist=['CharField']).CharField(
                        max_length=100, blank=True,
                    ),
                ),
                migrations.AddField(
                    model_name='studentprofile',
                    name='father_occupation',
                    field=__import__('django.db.models', fromlist=['CharField']).CharField(
                        max_length=255, blank=True,
                    ),
                ),
                migrations.AddField(
                    model_name='studentprofile',
                    name='address',
                    field=__import__('django.db.models', fromlist=['TextField']).TextField(blank=True),
                ),
                migrations.AddField(
                    model_name='studentprofile',
                    name='roll_number',
                    field=__import__('django.db.models', fromlist=['CharField']).CharField(
                        max_length=50, blank=True,
                    ),
                ),
            ],
        ),
    ]
