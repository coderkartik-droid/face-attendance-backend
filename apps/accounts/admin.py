from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from apps.accounts.models import User, TeacherProfile, StudentProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "role", "is_staff")
    list_filter = ("role", "is_staff", "is_superuser", "is_active")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Custom Fields", {"fields": ("role", "phone", "profile_picture")}),
    )


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "employee_id", "department", "created_at")
    search_fields = ("user__username", "user__first_name", "user__last_name", "employee_id")


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "roll_number", "class_obj", "section_obj", "created_at")
    search_fields = ("user__username", "user__first_name", "user__last_name", "roll_number")
    list_filter = ("class_obj", "section_obj", "gender")
