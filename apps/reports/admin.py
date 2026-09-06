from django.contrib import admin

from apps.reports.models import SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("auto_daily_pdf_export", "last_exported_report_date")
