from rest_framework import serializers

from apps.reports.models import SystemSetting


class SystemSettingSerializer(serializers.ModelSerializer):
    """Serializer for system settings (singleton)."""

    class Meta:
        model = SystemSetting
        fields = [
            'id',
            'auto_daily_pdf_export',
            'last_exported_report_date',
        ]
        read_only_fields = ['id', 'last_exported_report_date']