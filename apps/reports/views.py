"""Dashboard, system settings, and attendance export endpoints.

Excel/PDF exports always run a fresh database query with the caller's
current filters. They never reuse a cached list, a class-level queryset,
or AttendanceRecord.objects.all() without applying those filters.
"""

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reports.models import SystemSetting
from apps.reports.serializers import SystemSettingSerializer
from apps.reports.services import DashboardService, ReportExportService
from core.permissions import IsAdminOrTeacher


def _no_store_headers(response):
    """Prevent browsers/clients from serving a previously downloaded file."""
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = DashboardService.get_dashboard_summary(
            request.user,
            selected_date=request.query_params.get("date"),
            start_date=request.query_params.get("start_date"),
            end_date=request.query_params.get("end_date"),
        )
        return Response({"success": True, "data": data})


class ExcelExportView(APIView):
    """GET /api/reports/export/excel/ — filtered Excel, fresh DB query."""

    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get(self, request):
        # Fresh queryset per request; default date range is today when omitted.
        queryset = ReportExportService.get_filtered_queryset(
            request, default_to_today=True
        )
        content = ReportExportService.generate_excel_report(queryset)
        response = HttpResponse(
            content,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = 'attachment; filename="attendance_report.xlsx"'
        return _no_store_headers(response)


class PDFExportView(APIView):
    """GET /api/reports/export/pdf/ — same filters/rows as Excel, fresh DB query."""

    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get(self, request):
        queryset = ReportExportService.get_filtered_queryset(
            request, default_to_today=True
        )
        content = ReportExportService.generate_pdf_report(queryset)
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="attendance_report.pdf"'
        return _no_store_headers(response)


class SystemSettingsView(APIView):
    permission_classes = [IsAdminOrTeacher]

    def get(self, request):
        obj = SystemSetting.load()
        return Response(
            {"success": True, "data": SystemSettingSerializer(obj).data}
        )

    def put(self, request):
        obj = SystemSetting.load()
        serializer = SystemSettingSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True, "data": serializer.data})

    def patch(self, request):
        return self.put(request)
