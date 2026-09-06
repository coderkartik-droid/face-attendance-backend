"""
Django management command to automatically generate daily PDF attendance reports.

This command should be scheduled to run at the beginning of each day (e.g., via cron or Windows Task Scheduler).
It checks if automatic PDF export is enabled and generates reports for the previous day.

Usage:
    python manage.py auto_generate_daily_pdf
"""

import os
import logging
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings

from apps.reports.models import SystemSetting
from apps.reports.services import ReportExportService
from core.attendance_queries import historical_attendance_records

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Automatically generate daily PDF attendance reports for the previous day'

    def handle(self, *args, **options):
        self.stdout.write('Starting automatic daily PDF export check...')

        # Load system settings
        settings_obj = SystemSetting.load()
        
        # Check if automatic PDF export is enabled
        if not settings_obj.auto_daily_pdf_export:
            self.stdout.write(self.style.WARNING('Automatic daily PDF export is DISABLED. Exiting.'))
            return

        # Calculate the date for the previous day
        today = timezone.localdate()
        previous_day = today - timedelta(days=1)
        
        # Check if we already exported this date
        if settings_obj.last_exported_report_date == previous_day:
            self.stdout.write(
                self.style.WARNING(
                    f'PDF for {previous_day} already exists (last_exported_report_date: {settings_obj.last_exported_report_date}). Skipping.'
                )
            )
            return

        self.stdout.write(f'Generating PDF for date: {previous_day}')

        try:
            # Create attendance reports directory if it doesn't exist
            reports_dir = os.path.join(settings.MEDIA_ROOT, 'Attendance Reports')
            os.makedirs(reports_dir, exist_ok=True)

            # Generate filename
            filename = f'Attendance_Report_{previous_day.strftime("%Y-%m-%d")}.pdf'
            filepath = os.path.join(reports_dir, filename)

            # Check if file already exists
            if os.path.exists(filepath):
                self.stdout.write(
                    self.style.WARNING(f'PDF file {filename} already exists. Skipping.')
                )
                return

            # Get attendance records for the previous day. Historical report:
            # include ALL stored records (snapshot identity preserved), so the
            # generated file is identical even if users are later deleted.
            queryset = historical_attendance_records().filter(
                session__date=previous_day
            ).select_related(
                "student", "student__student_profile", 
                "session", "session__class_obj", "session__section_obj"
            ).order_by("-marked_at")

            # Generate PDF
            pdf_bytes = ReportExportService.generate_pdf_report(queryset)

            # Save PDF to file
            with open(filepath, 'wb') as f:
                f.write(pdf_bytes)

            # Update last exported date
            settings_obj.last_exported_report_date = previous_day
            settings_obj.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully generated PDF report: {filename} '
                    f'({queryset.count()} records for {previous_day})'
                )
            )
            logger.info(
                f'Automatic daily PDF export completed: {filename} '
                f'with {queryset.count()} records for {previous_day}'
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to generate PDF for {previous_day}: {str(e)}')
            )
            logger.error(f'Automatic daily PDF export failed for {previous_day}: {str(e)}')
            raise