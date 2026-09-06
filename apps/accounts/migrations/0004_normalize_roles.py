from django.db import migrations


def normalize_roles(apps, schema_editor):
    """Migrate legacy roles and guarantee super admins are never students.

    - Legacy ``admin`` role (from the pre-0003 choices) -> ``super_admin``.
    - Any superuser/staff user whose role is not an explicit teacher/student
      is promoted to ``super_admin``.
    - The canonical ``admin`` username is always ``super_admin``.
    """
    User = apps.get_model("accounts", "User")

    # Legacy "admin" role value no longer exists in the choices.
    User.objects.filter(role="admin").update(role="super_admin")

    # Promote elevated accounts that are not explicit teachers/students.
    User.objects.filter(is_superuser=True).exclude(
        role__in=["teacher", "student"]
    ).update(role="super_admin")

    User.objects.filter(is_staff=True).exclude(
        role__in=["super_admin", "school_admin", "teacher", "student"]
    ).update(role="super_admin")

    # The default admin account must always be a super admin.
    User.objects.filter(username="admin").update(
        role="super_admin", is_staff=True, is_superuser=True, is_active=True
    )


def reverse_normalize_roles(apps, schema_editor):
    # Best-effort reverse: no destructive action needed.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_school_alter_user_role_user_school"),
    ]

    operations = [
        migrations.RunPython(normalize_roles, reverse_normalize_roles),
    ]
