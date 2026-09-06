from django.urls import path
from apps.reports.views import DashboardView, ExcelExportView, PDFExportView, SystemSettingsView

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard_main"),
    path("export/excel/", ExcelExportView.as_view(), name="export_excel"),
    path("export/pdf/", PDFExportView.as_view(), name="export_pdf"),
    path("settings/", SystemSettingsView.as_view(), name="system_settings"),
]
