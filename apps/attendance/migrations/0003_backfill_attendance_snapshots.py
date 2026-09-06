"""Backfill the immutable attendance-history snapshot columns.

Existing AttendanceRecord rows are captured from the CURRENT live relations
(user, profile, class/section). Running this once at deploy time gives every
already-marked record a frozen copy of the person's name, role and
class/section so historical reports never change when users are edited,
moved between classes, deactivated or deleted later.
"""

from django.db import migrations


def backfill_snapshots(apps, schema_editor):
    AttendanceRecord = apps.get_model("attendance", "AttendanceRecord")

    for record in (
        AttendanceRecord.objects.select_related(
            "student",
            "student__student_profile",
            "student__teacher_profile",
            "session",
            "session__class_obj",
            "session__section_obj",
        ).iterator()
    ):
        student = record.student
        session = record.session
        full_name = ""
        if student:
            full_name = f"{student.first_name} {student.last_name}".strip()
            if not full_name:
                full_name = student.username
        updates = {
            "student_name": full_name,
            "student_role": student.role if student else "",
            "roll_number": (
                student.student_profile.roll_number
                if student and hasattr(student, "student_profile")
                else ""
            ),
            "employee_id": (
                student.teacher_profile.employee_id
                if student and hasattr(student, "teacher_profile")
                else ""
            ),
            "class_name": (
                session.class_obj.name if session and session.class_obj else ""
            ),
            "section_name": (
                session.section_obj.name if session and session.section_obj else ""
            ),
        }
        # Avoid flagging already-identical rows as dirty.
        changed = any(
            getattr(record, field) != value for field, value in updates.items()
        )
        if changed:
            for field, value in updates.items():
                setattr(record, field, value)
            record.save(update_fields=list(updates))


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0002_attendancerecord_class_name_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_snapshots, migrations.RunPython.noop),
    ]