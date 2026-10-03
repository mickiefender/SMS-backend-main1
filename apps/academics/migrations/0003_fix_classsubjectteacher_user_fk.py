from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import migrations


def fix_class_subject_teacher_user_fk(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return

    from apps.academics.models import ClassSubjectTeacher

    class_subject_teacher = ClassSubjectTeacher
    user_model = get_user_model()
    assignment_table = class_subject_teacher._meta.db_table
    user_table = user_model._meta.db_table
    teacher_column = class_subject_teacher._meta.get_field("teacher").column
    user_pk_column = user_model._meta.pk.column

    if assignment_table not in connection.introspection.table_names():
        return

    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, assignment_table)
        teacher_foreign_keys = [
            (name, details["foreign_key"])
            for name, details in constraints.items()
            if details.get("columns") == [teacher_column] and details.get("foreign_key")
        ]
        if any(
            foreign_key == (user_table, user_pk_column)
            for _, foreign_key in teacher_foreign_keys
        ):
            return

        quote = connection.ops.quote_name
        cursor.execute(
            f"""
            SELECT assignment.{quote(teacher_column)}
            FROM {quote(assignment_table)} assignment
            LEFT JOIN {quote(user_table)} account
              ON account.{quote(user_pk_column)} = assignment.{quote(teacher_column)}
            WHERE account.{quote(user_pk_column)} IS NULL
            LIMIT 1
            """
        )
        if cursor.fetchone():
            raise RuntimeError(
                f"Cannot repair the teacher foreign key on {assignment_table}: "
                f"one or more assigned teacher IDs do not exist in {user_table}."
            )

        for constraint_name, _ in teacher_foreign_keys:
            schema_editor.execute(
                f"ALTER TABLE {quote(assignment_table)} "
                f"DROP CONSTRAINT {quote(constraint_name)}"
            )

        schema_editor.execute(
            f"ALTER TABLE {quote(assignment_table)} "
            f"ADD CONSTRAINT {quote('academics_classsubjectteacher_teacher_id_fkey')} "
            f"FOREIGN KEY ({quote(teacher_column)}) "
            f"REFERENCES {quote(user_table)} ({quote(user_pk_column)}) "
            "ON DELETE CASCADE"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0002_userprofilepicture_supabase"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(
            fix_class_subject_teacher_user_fk,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
