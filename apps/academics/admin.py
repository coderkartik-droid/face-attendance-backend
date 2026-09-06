from django.contrib import admin
from apps.academics.models import Class, Section, Subject


@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "created_at")
    search_fields = ("name", "code")


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "class_obj", "room_number", "capacity")
    list_filter = ("class_obj",)
    search_fields = ("name", "room_number")


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "department")
    search_fields = ("name", "code", "department")
