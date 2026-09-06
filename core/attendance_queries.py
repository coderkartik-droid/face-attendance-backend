"""Single source of truth for attendance queries.

Two views of the same data exist, and both MUST be built from the helpers here
instead of calling ``AttendanceRecord.objects...`` directly:

* ``historical_attendance_records()`` — EVERY stored record, including users
  that were later deactivated or hard deleted. Past-day reports, exports and
  dashboards must stay permanently immutable: they keep showing exactly who
  was marked that day (identity preserved through the snapshot columns on
  AttendanceRecord), regardless of later edits, class changes or deletes.

* ``active_attendance_records()`` — LIVE / TODAY views only. Deleted or
  deactivated users (User.is_active == False) keep their historical rows in
  the database, but those rows are excluded from anything that reflects the
  current day: today's attendance, the today dashboard and per-user
  today-status. This is the ONLY place where the "active users only" rule
  applies.
"""

from django.db.models import Q
from django.utils import timezone

from apps.attendance.models import AttendanceRecord

# Reusable filter fragment for querysets that were built some other way but
# still need the active-user restriction applied.
ACTIVE_STUDENT_FILTER = {"student__is_active": True}

# A user only counts as an ACTIVE member of the school when their account is
# active AND their profile still exists. When a student/teacher is deleted,
# the profile row is removed, so requiring the profile here guarantees a
# deleted user's leftover attendance rows can never be counted or exported.
ACTIVE_USER_CONDITION = Q(student__student_profile__isnull=False) | Q(
    student__teacher_profile__isnull=False
)


def historical_attendance_records():
    """Base queryset of ALL stored attendance records (immutable history).

    Intentionally does NOT filter by active users: past attendance must never
    be recalculated from "today's active users".
    """
    return AttendanceRecord.objects.all()


def active_attendance_records():
    """Base queryset of attendance records belonging to ACTIVE users only
    (active account AND existing student/teacher profile).

    Use ONLY for live/today views.
    """
    return AttendanceRecord.objects.filter(
        ACTIVE_USER_CONDITION,
        **ACTIVE_STUDENT_FILTER,
    )


def _parse_iso_date(value):
    """Parse YYYY-MM-DD from a query param. Returns None if missing/invalid."""
    if not value:
        return None
    try:
        return timezone.datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def parse_report_date_range(query_params, *, default_to_today=False):
    """Resolve date / start_date / end_date query params into a closed range.

    - ``start_date`` + ``end_date`` win when either is present.
    - otherwise ``date`` is a single-day range.
    - otherwise, if default_to_today, use local today (export safety net so
      callers never accidentally dump the entire history).
    - otherwise (None, None) meaning "no date constraint".
    """
    date_param = _parse_iso_date(query_params.get("date"))
    start = _parse_iso_date(query_params.get("start_date"))
    end = _parse_iso_date(query_params.get("end_date"))
    if start or end:
        range_start = start or end
        range_end = end or start
        if range_start > range_end:
            range_start, range_end = range_end, range_start
        return range_start, range_end
    if date_param:
        return date_param, date_param
    if default_to_today:
        today = timezone.localdate()
        return today, today
    return None, None


def attendance_records_in_range(range_start, range_end):
    """Fresh DB queryset for attendance rows in ``[range_start, range_end]``.

    Built from scratch on every call (no module/global cache). Past days use
    historical records so snapshot identity stays immutable; today uses the
    live/active roster only.
    """
    today = timezone.localdate()
    if range_end < today:
        return historical_attendance_records().filter(
            session__date__range=(range_start, range_end)
        )
    if range_start >= today:
        return active_attendance_records().filter(
            session__date__range=(range_start, range_end)
        )
    # Mixed range (e.g. Last 7 Days): immutable past + live today.
    return historical_attendance_records().filter(
        session__date__range=(range_start, range_end)
    ).filter(
        Q(session__date__lt=today)
        | (
            Q(session__date__gte=today)
            & ACTIVE_USER_CONDITION
            & Q(**ACTIVE_STUDENT_FILTER)
        )
    )


def filtered_attendance_records(request, *, default_to_today=False):
    """Apply every active report filter to a freshly queried queryset.

    Supported query params (aliases in parentheses):
      date, start_date, end_date, class_id (class_obj), section_id
      (section_obj), student_id (student), teacher_id (teacher), status,
      search (q).
    """
    params = request.query_params
    range_start, range_end = parse_report_date_range(
        params, default_to_today=default_to_today
    )
    if range_start and range_end:
        queryset = attendance_records_in_range(range_start, range_end)
    else:
        queryset = historical_attendance_records()

    class_id = params.get("class_id") or params.get("class_obj")
    section_id = params.get("section_id") or params.get("section_obj")
    student_id = params.get("student_id") or params.get("student")
    teacher_id = params.get("teacher_id") or params.get("teacher")
    status_param = (params.get("status") or "").strip()
    search = (params.get("search") or params.get("q") or "").strip()

    if class_id:
        queryset = queryset.filter(session__class_obj_id=class_id)
    if section_id:
        queryset = queryset.filter(session__section_obj_id=section_id)
    if student_id:
        queryset = queryset.filter(student_id=student_id)
    if teacher_id:
        queryset = queryset.filter(session__teacher_id=teacher_id)
    if status_param:
        queryset = queryset.filter(status=status_param.upper())

    if search:
        queryset = queryset.filter(
            Q(student_name__icontains=search)
            | Q(roll_number__icontains=search)
            | Q(employee_id__icontains=search)
            | Q(class_name__icontains=search)
            | Q(section_name__icontains=search)
            | Q(student__first_name__icontains=search)
            | Q(student__last_name__icontains=search)
            | Q(student__username__icontains=search)
        )

    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        if user.is_school_admin():
            pass  # Admins/superusers see all records regardless of role field.
        elif user.is_student():
            queryset = queryset.filter(student=user)
        elif user.is_teacher():
            queryset = queryset.filter(session__teacher=user)

    # Always return an unevaluated queryset so the caller hits the DB now,
    # not a previously cached result list.
    return queryset.select_related(
        "student",
        "student__student_profile",
        "session",
        "session__class_obj",
        "session__section_obj",
        "session__teacher",
    ).order_by("session__date", "student_name", "id")
