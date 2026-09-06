from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.attendance.views import (
    AttendanceSessionViewSet,
    MarkAttendanceView,
    BulkMarkAttendanceView,
    AttendanceHistoryView,
    TodayAttendanceView,
    MonthlyAttendanceView,
    StudentHistoryView,
    TeacherHistoryView,
)

router = DefaultRouter()
router.register(r"sessions", AttendanceSessionViewSet, basename="attendance-session")

urlpatterns = [
    path("mark/", MarkAttendanceView.as_view(), name="mark_attendance"),
    path("bulk-mark/", BulkMarkAttendanceView.as_view(), name="bulk_mark_attendance"),
    path("history/", AttendanceHistoryView.as_view(), name="attendance_history"),
    path("today/", TodayAttendanceView.as_view(), name="today_attendance"),
    path("monthly/", MonthlyAttendanceView.as_view(), name="monthly_attendance"),
    path("student-history/", StudentHistoryView.as_view(), name="student_history"),
    path("teacher-history/", TeacherHistoryView.as_view(), name="teacher_history"),
    path("", include(router.urls)),
]
