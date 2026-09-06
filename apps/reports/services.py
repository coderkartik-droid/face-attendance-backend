import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from django.db.models import Count, Q
from django.utils import timezone

from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.academics.models import Class, Section
from apps.accounts.models import StudentProfile, TeacherProfile
from core.attendance_queries import (
    active_attendance_records,
    filtered_attendance_records,
    historical_attendance_records,
)


class DashboardService:
    @staticmethod
    def _distinct_people(records_qs):
        """Number of distinct people represented by a record queryset.

        Deleted users have a NULL student FK; they are counted individually via
        the frozen snapshot name so they still appear in historical stats.
        """
        return (
            records_qs.filter(student__isnull=False)
            .values("student_id")
            .distinct()
            .count()
            + records_qs.filter(student__isnull=True)
            .values("student_name")
            .distinct()
            .count()
        )

    @staticmethod
    def _static_summary(range_start, range_end):
        """Immutable summary for a fully PAST date/range.

        Computed from ALL stored records (historical_attendance_records) so
        deleting or editing a user later can never change the numbers for a
        past day. Deleted / deactivated people are counted through the frozen
        snapshot columns on AttendanceRecord.
        """
        records = historical_attendance_records().filter(
            session__date__range=(range_start, range_end)
        )

        present_statuses = [
            AttendanceRecord.Status.PRESENT,
            AttendanceRecord.Status.LATE,
        ]
        present = DashboardService._distinct_people(
            records.filter(status__in=present_statuses)
        )
        late = DashboardService._distinct_people(
            records.filter(status=AttendanceRecord.Status.LATE)
        )
        marked = DashboardService._distinct_people(records)

        # Roster for the period = everyone active NOW plus every OTHER person
        # who still has a stored record in the period (users deleted or
        # deactivated since, identified through the snapshot columns). This
        # keeps past-day totals stable after roster changes.
        active_student_ids = set(
            StudentProfile.objects.filter(user__is_active=True).values_list(
                "user_id", flat=True
            )
        )
        active_teacher_ids = set(
            TeacherProfile.objects.filter(user__is_active=True).values_list(
                "user_id", flat=True
            )
        )
        record_ids_by_role = {}
        for row in (
            records.filter(student__isnull=False)
            .values("student_id", "student__role")
            .distinct()
        ):
            record_ids_by_role.setdefault(row["student__role"], set()).add(
                row["student_id"]
            )
        null_counts_by_role = {
            row["student_role"]: row["n"]
            for row in records.filter(student__isnull=True)
            .values("student_role")
            .annotate(n=Count("student_name", distinct=True))
        }
        active_ids = active_student_ids | active_teacher_ids

        def extra_for_role(role):
            extra_ids = record_ids_by_role.get(role, set()) - active_ids
            return len(extra_ids) + null_counts_by_role.get(role, 0)

        total_students = len(active_student_ids) + extra_for_role("student")
        total_teachers = len(active_teacher_ids) + extra_for_role("teacher")
        total_roster = total_students + total_teachers
        absent = max(total_roster - present, 0)
        attendance_rate = (
            round((present / total_roster) * 100, 1) if total_roster > 0 else 0.0
        )

        today_sessions = AttendanceSession.objects.filter(
            date__range=(range_start, range_end)
        ).count()

        class_analytics = list(
            Class.objects.annotate(
                student_count=Count(
                    "students", filter=Q(students__user__is_active=True)
                )
            ).values("id", "name", "student_count")
        )

        # Class-wise attendance from ALL records (immutable).
        present_map = {
            row["session__class_obj_id"]: row["n"]
            for row in records.filter(
                status__in=present_statuses, student__isnull=False
            )
            .values("session__class_obj_id")
            .annotate(n=Count("student_id", distinct=True))
        }
        present_null_map = {
            row["session__class_obj_id"]: row["n"]
            for row in records.filter(
                status__in=present_statuses, student__isnull=True
            )
            .values("session__class_obj_id")
            .annotate(n=Count("student_name", distinct=True))
        }
        marked_map = {
            row["session__class_obj_id"]: row["n"]
            for row in records.filter(student__isnull=False)
            .values("session__class_obj_id")
            .annotate(n=Count("student_id", distinct=True))
        }
        marked_null_map = {
            row["session__class_obj_id"]: row["n"]
            for row in records.filter(student__isnull=True)
            .values("session__class_obj_id")
            .annotate(n=Count("student_name", distinct=True))
        }
        marked_student_ids_by_class = {}
        for row in records.values(
            "session__class_obj_id", "student_id"
        ).distinct():
            if row["student_id"] is None:
                continue
            marked_student_ids_by_class.setdefault(
                row["session__class_obj_id"], []
            ).append(row["student_id"])

        class_attendance = []
        for cls in Class.objects.annotate(
            student_count=Count("students", filter=Q(students__user__is_active=True))
        ):
            class_attendance.append(
                {
                    "class_id": cls.id,
                    "class_name": cls.name,
                    "student_count": cls.student_count,
                    "present": (
                        present_map.get(cls.id, 0) + present_null_map.get(cls.id, 0)
                    ),
                    "marked": (
                        marked_map.get(cls.id, 0) + marked_null_map.get(cls.id, 0)
                    ),
                    "marked_student_ids": marked_student_ids_by_class.get(cls.id, []),
                }
            )

        section_analytics = list(
            Section.objects.select_related("class_obj")
            .annotate(
                student_count=Count(
                    "students", filter=Q(students__user__is_active=True)
                )
            )
            .values("id", "name", "class_obj__name", "student_count")
        )

        recent_records = (
            records.select_related("student", "session", "session__class_obj")
            .order_by("-marked_at")[:10]
        )
        recent_list = DashboardService._recent_list(recent_records)

        return {
            "total_students": total_students,
            "total_teachers": total_teachers,
            "total_classes": Class.objects.count(),
            "face_registered": StudentProfile.objects.filter(
                user__is_active=True, is_registration_complete=True
            ).count(),
            "face_pending": StudentProfile.objects.filter(
                user__is_active=True, is_registration_complete=False
            ).count(),
            "today_sessions": today_sessions,
            "today_attendance": marked,
            "today_marked": marked,
            "today_present": present,
            "today_absent": absent,
            "today_late": late,
            "attendance_rate": attendance_rate,
            "class_analytics": class_analytics,
            "class_attendance": class_attendance,
            "section_analytics": section_analytics,
            "recent_activity": recent_list,
        }

    @staticmethod
    def _recent_list(recent_records):
        return [
            {
                "id": r.id,
                "student_name": r.student_name
                or (r.student.full_name if r.student else "Deleted User"),
                "role": r.student_role or (r.student.get_role_display() if r.student else ""),
                "class_name": (
                    r.class_name
                    or (r.session.class_obj.name if r.session and r.session.class_obj else "N/A")
                ),
                "status": r.status,
                "method": r.verification_method,
                "marked_at": r.marked_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for r in recent_records
        ]

    @staticmethod
    def get_dashboard_summary(user, selected_date=None, start_date=None, end_date=None):
        today = timezone.localdate()
        try:
            report_date = (
                timezone.datetime.strptime(selected_date, "%Y-%m-%d").date()
                if selected_date
                else today
            )
            range_start = (
                timezone.datetime.strptime(start_date, "%Y-%m-%d").date()
                if start_date
                else report_date
            )
            range_end = (
                timezone.datetime.strptime(end_date, "%Y-%m-%d").date()
                if end_date
                else report_date
            )
        except (TypeError, ValueError):
            range_start = today
            range_end = today

        # A range that touches today (or is today) is LIVE and reflects the
        # current active roster. A fully-past range is immutable history.
        if range_end >= today:
            return DashboardService._live_summary(range_start, range_end)
        return DashboardService._static_summary(range_start, range_end)

    @staticmethod
    def _live_summary(range_start, range_end):
        today = timezone.localdate()

        total_students = StudentProfile.objects.filter(user__is_active=True).count()
        total_teachers = TeacherProfile.objects.filter(user__is_active=True).count()
        total_classes = Class.objects.count()

        face_registered = StudentProfile.objects.filter(
            user__is_active=True, is_registration_complete=True
        ).count()
        face_pending = StudentProfile.objects.filter(
            user__is_active=True, is_registration_complete=False
        ).count()

        today_sessions = AttendanceSession.objects.filter(
            date__range=(range_start, range_end)
        )
        today_records = active_attendance_records().filter(
            session__date__range=(range_start, range_end),
            student__role__in=["student", "teacher"],
            status=AttendanceRecord.Status.PRESENT,
        )

        total_marked_today = today_records.values("student_id").distinct().count()
        present_today = total_marked_today
        absent_today = max(total_students + total_teachers - present_today, 0)
        late_today = today_records.filter(status=AttendanceRecord.Status.LATE).count()

        attendance_rate = (
            round((present_today / (total_students + total_teachers)) * 100, 1)
            if total_students + total_teachers > 0
            else 0.0
        )

        class_analytics = list(
            Class.objects.annotate(
                student_count=Count(
                    "students", filter=Q(students__user__is_active=True)
                )
            ).values("id", "name", "student_count")
        )

        # Class-wise attendance for today (single set of aggregate queries
        # instead of one query per class).
        class_attendance = []
        today_stats = (
            active_attendance_records()
            .filter(
                session__date__range=(range_start, range_end),
                student__role__in=["student", "teacher"],
                status=AttendanceRecord.Status.PRESENT,
            )
            .values("session__class_obj_id", "session__class_obj__name")
            .annotate(
                marked=Count("student_id", distinct=True),
                present=Count("student_id", distinct=True),
            )
        )
        stats_by_class = {row["session__class_obj_id"]: row for row in today_stats}
        marked_student_ids_by_class = {}
        for row in today_records.values(
            "session__class_obj_id", "student_id"
        ).distinct():
            marked_student_ids_by_class.setdefault(
                row["session__class_obj_id"], []
            ).append(row["student_id"])
        for cls in Class.objects.annotate(
            student_count=Count("students", filter=Q(students__user__is_active=True))
        ):
            row = stats_by_class.get(cls.id)
            class_attendance.append(
                {
                    "class_id": cls.id,
                    "class_name": cls.name,
                    "student_count": cls.student_count,
                    "present": row["present"] if row else 0,
                    "marked": row["marked"] if row else 0,
                    # A badge is present when a record exists for the selected
                    # date range; no stored per-student attendance flag is used.
                    "marked_student_ids": marked_student_ids_by_class.get(cls.id, []),
                }
            )

        section_analytics = list(
            Section.objects.select_related("class_obj")
            .annotate(
                student_count=Count(
                    "students", filter=Q(students__user__is_active=True)
                )
            )
            .values("id", "name", "class_obj__name", "student_count")
        )

        recent_records = (
            active_attendance_records()
            .filter(session__date__range=(range_start, range_end))
            .select_related("student", "session", "session__class_obj")
            .order_by("-marked_at")[:10]
        )

        recent_list = DashboardService._recent_list(recent_records)

        return {
            "total_students": total_students,
            "total_teachers": total_teachers,
            "total_classes": total_classes,
            "face_registered": face_registered,
            "face_pending": face_pending,
            "today_sessions": today_sessions.count(),
            "today_attendance": total_marked_today,
            "today_marked": total_marked_today,
            "today_present": present_today,
            "today_absent": absent_today,
            "today_late": late_today,
            "attendance_rate": attendance_rate,
            "class_analytics": class_analytics,
            "class_attendance": class_attendance,
            "section_analytics": section_analytics,
            "recent_activity": recent_list,
        }


class ReportExportService:
    # Shared column set so PDF and Excel always contain the same filtered rows.
    EXPORT_HEADERS = [
        "Date",
        "Name",
        "Role",
        "Roll / Employee ID",
        "Class",
        "Section",
        "Status",
        "Method",
        "Marked At",
    ]

    @staticmethod
    def get_filtered_queryset(request, *, default_to_today=True):
        """Build a FRESH filtered queryset for this request.

        Never reuse a class-level / global queryset. Every export hits the DB
        with the caller's current filters.
        """
        return filtered_attendance_records(
            request, default_to_today=default_to_today
        )

    @staticmethod
    def _records_list(queryset):
        """Evaluate the queryset once so PDF and Excel iterate the same rows.

        Snapshot fields (student_name, class_name, …) are read as stored.
        """
        if isinstance(queryset, list):
            return queryset
        return list(queryset)

    @staticmethod
    def _row_from_record(rec):
        session_date = ""
        if rec.session and rec.session.date:
            session_date = rec.session.date.isoformat()
        c_name = rec.class_name or (
            rec.session.class_obj.name
            if rec.session and rec.session.class_obj
            else ""
        )
        s_name = rec.section_name or (
            rec.session.section_obj.name
            if rec.session and rec.session.section_obj
            else ""
        )
        roll_or_emp = rec.roll_number or rec.employee_id or ""
        marked = rec.marked_at.strftime("%Y-%m-%d %H:%M:%S") if rec.marked_at else ""
        return [
            session_date,
            rec.student_name
            or (rec.student.full_name if rec.student else "Deleted User"),
            rec.student_role
            or (rec.student.get_role_display() if rec.student else ""),
            roll_or_emp,
            c_name,
            s_name,
            rec.status,
            rec.verification_method,
            marked,
        ]

    @staticmethod
    def generate_excel_report(queryset):
        records = ReportExportService._records_list(queryset)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Attendance Report"

        # Headers styling
        header_fill = PatternFill(
            start_color="1F2937", end_color="1F2937", fill_type="solid"
        )
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        align_center = Alignment(horizontal="center", vertical="center")

        headers = ReportExportService.EXPORT_HEADERS
        ws.append(headers)

        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = align_center

        for rec in records:
            ws.append(ReportExportService._row_from_record(rec))

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output.getvalue()

    @staticmethod
    def generate_pdf_report(queryset):
        records = ReportExportService._records_list(queryset)
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=24,
            leftMargin=24,
            topMargin=30,
            bottomMargin=30,
        )
        elements = []

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Heading1"],
            fontSize=18,
            textColor=colors.HexColor("#1E3A8A"),
            spaceAfter=12,
        )
        subtitle_style = ParagraphStyle(
            "ReportSub",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#4B5563"),
            spaceAfter=20,
        )

        elements.append(Paragraph("AI Face Attendance Report", title_style))
        elements.append(
            Paragraph(
                f"Generated on: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')} | "
                f"Total Records: {len(records)}",
                subtitle_style,
            )
        )

        table_data = [ReportExportService.EXPORT_HEADERS]
        for rec in records:
            table_data.append(ReportExportService._row_from_record(rec))

        t = Table(table_data, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F9FAFB")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 7),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        elements.append(t)
        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()
