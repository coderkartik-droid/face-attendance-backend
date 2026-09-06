
"""System-wide settings, editable from the Django admin panel."""

from django.db import models


class SystemSetting(models.Model):
    """Singleton row holding global (admin-editable) settings."""

    # ☐ Enable Automatic Daily PDF Export (default: Disabled)
    auto_daily_pdf_export = models.BooleanField(
        default=False,
        verbose_name="Enable Automatic Daily PDF Export",
        help_text=(
            "When enabled, a PDF attendance report for the previous day is "
            "generated automatically at the start of every new day and saved "
            "locally in the 'Attendance Reports' folder. Active users only."
        ),
    )

    # Internal bookkeeping so the same day is never exported twice.
    last_exported_report_date = models.DateField(
        null=True,
        blank=True,
        editable=False,
        help_text="Date of the last automatically generated daily report.",
    )

    class Meta:
        verbose_name = "System Setting"
        verbose_name_plural = "System Settings"

    def __str__(self):
        return "System Settings"

    @classmethod
    def load(cls):
        """Get (creating if needed) the single settings row."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
