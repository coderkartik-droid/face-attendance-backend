"""Immutability tests for the attendance history snapshot feature.

Verifies that deleting / editing a user after their attendance was marked can
never change the historical attendance data, while today's (live) views keep
excluding deleted users.
"""

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import StudentProfile, TeacherProfile, User
from apps.academics.models import Class, Section
from apps.attendance.models import AttendanceRecord, AttendanceSession
from core.attendance_queries import (
    active_attendance_records,
    historical_attendance_records,
)


class AttendanceImmutabilityTests(TestCase):
    def setUp(self):
        self.cls = Class.objects.create(name="Grade 12", code="G12", description="x")
        self.sec = Section.objects.create(name="B", class_obj=self.cls, room_number="2")

        self.teacher = User.objects.create_user(
            username="t1", first_name="Teacher", last_name="One", role="teacher"
        )
        TeacherProfile.objects.create(
            user=self.teacher, employee_id="T1", department="Science"
        )
        self.teacher_session, _ = AttendanceSession.objects.get_or_create(
            class_obj=self.cls, section_obj=self.sec, date=timezone.localdate(),
            session_name="Daily Attendance", defaults={"teacher": self.teacher},
        )

        self.students = []
        for i, (first, last, roll, status) in enumerate([
            ("Alice", "Student", "R001", AttendanceRecord.Status.PRESENT),
            ("Bob", "Student", "R002", AttendanceRecord.Status.ABSENT),
            ("Carol", "Student", "R003", AttendanceRecord.Status.PRESENT),
        ]):
            user = User.objects.create_user(
                username=f"s{i}", first_name=first, last_name=last, role="student"
            )
            StudentProfile.objects.create(
                user=user, roll_number=roll, class_obj=self.cls, section_obj=self.sec
            )
            self.students.append((user, status))

        # Mark attendance for the day, exactly like MarkAttendanceView does.
        for user, status in self.students:
            AttendanceRecord.objects.update_or_create(
                session=self.teacher_session,
                student=user,
                defaults={
                    "status": status,
                    "verification_method": AttendanceRecord.Method.FACE_RECOGNITION,
                    **self._snapshot(user),
                },
            )
        # The teacher is also part of the daily roster and marked present.
        AttendanceRecord.objects.update_or_create(
            session=self.teacher_session,
            student=self.teacher,
            defaults={
                "status": AttendanceRecord.Status.PRESENT,
                "verification_method": AttendanceRecord.Method.FACE_RECOGNITION,
                **self._snapshot(self.teacher),
            },
        )

    def _snapshot(self, user):
        profile = getattr(user, "student_profile", None) or getattr(
            user, "teacher_profile", None
        )
        return {
            "student_name": user.full_name,
            "student_role": user.role,
            "roll_number": getattr(profile, "roll_number", "") or "",
            "employee_id": getattr(profile, "employee_id", "") or "",
            "class_name": self.cls.name,
            "section_name": self.sec.name,
        }

    def test_history_keeps_deleted_user_records(self):
        bob, _ = self.students[1]
        hist_before = set(
            historical_attendance_records().values_list("student_name", "status")
        )

        bob.delete()

        hist_after = set(
            historical_attendance_records().values_list("student_name", "status")
        )
        self.assertEqual(hist_before, hist_after)
        self.assertIn(("Bob Student", "ABSENT"), hist_after)

        # The row survived with a NULL FK + frozen snapshot.
        bob_record = AttendanceRecord.objects.get(
            session=self.teacher_session, student__isnull=True
        )
        self.assertEqual(bob_record.student_name, "Bob Student")
        self.assertEqual(bob_record.student_role, "student")

    def test_today_view_excludes_deleted_users(self):
        bob, _ = self.students[1]
        bob_active = active_attendance_records().filter(
            session__date=timezone.localdate()
        ).count()
        self.assertEqual(bob_active, 4)

        bob.delete()

        active_count = active_attendance_records().filter(
            session__date=timezone.localdate()
        ).count()
        self.assertEqual(active_count, 3)

    def test_historical_includes_deleted_user_serializer(self):
        from apps.attendance.serializers import AttendanceRecordSerializer

        bob, _ = self.students[1]
        bob.delete()
        record = AttendanceRecord.objects.get(
            session=self.teacher_session, student__isnull=True
        )
        data = AttendanceRecordSerializer(record).data
        self.assertEqual(data["student_name"], "Bob Student")
        self.assertEqual(data["roll_number"], "R002")
        self.assertEqual(data["class_name"], "Grade 12")

    def test_edit_after_marking_does_not_change_history(self):
        alice, _ = self.students[0]
        alice.first_name = "Alicia"
        alice.save()
        alice.student_profile.roll_number = "X999"
        alice.student_profile.save()

        record = AttendanceRecord.objects.get(session=self.teacher_session, student=alice)
        self.assertEqual(record.student_name, "Alice Student")
        self.assertEqual(record.roll_number, "R001")
        self.assertEqual(record.class_name, "Grade 12")

    def test_dashboard_past_date_is_static_and_today_is_live(self):
        from apps.reports.services import DashboardService

        today = timezone.localdate()

        bob, _ = self.students[1]
        bob.delete()

        live = DashboardService.get_dashboard_summary(None, selected_date=str(today))
        # Today is live: Bob is gone from the roster → 2 students + 1 teacher,
        # and only the 3 currently-active people are counted as present.
        self.assertEqual(live["total_students"], 2)
        self.assertEqual(live["total_teachers"], 1)
        self.assertEqual(live["today_present"], 3)
        self.assertEqual(live["today_absent"], 0)

        # A few days ago: immutable history (all four recorded incl. deleted
        # Bob; Bob was absent that day).
        past = today - timezone.timedelta(days=3)
        # Move the session's date into the past to simulate a past day.
        AttendanceSession.objects.filter(id=self.teacher_session.id).update(date=past)
        static = DashboardService.get_dashboard_summary(None, selected_date=str(past))
        self.assertEqual(static["total_students"], 3)
        self.assertEqual(static["total_teachers"], 1)
        self.assertEqual(static["today_present"], 3)
        self.assertEqual(static["today_absent"], 1)