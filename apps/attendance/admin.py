from django.contrib import admin
from apps.attendance.models import AttendanceSession, AttendanceRecord


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ("class_obj", "section_obj", "teacher", "date", "session_name", "is_active")
    list_filter = ("class_obj", "section_obj", "date", "is_active")
    search_fields = ("session_name", "teacher__username")


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("session", "student", "status", "verification_method", "confidence_score", "marked_at")
    list_filter = ("status", "verification_method", "session__date")
    search_fields = ("student__username", "student__first_name", "student__last_name")
