import logging
from rest_framework import generics, status, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.mixins import StandardResponseMixin
from core.permissions import IsAdminOrTeacher
from core.exceptions import BusinessValidationError, FaceNotDetectedError
from core.attendance_queries import (
    active_attendance_records,
    filtered_attendance_records,
    historical_attendance_records,
)
from apps.attendance.models import AttendanceSession, AttendanceRecord
from apps.attendance.serializers import (
    AttendanceSessionSerializer,
    AttendanceRecordSerializer,
    MarkAttendanceRequestSerializer,
    BulkMarkAttendanceSerializer,
)
from apps.faces.services import FaceRecognitionService
from apps.faces.models import FaceImage

logger = logging.getLogger(__name__)
User = get_user_model()


def _attendance_snapshot(student, session):
    """Frozen copy of the person + session identity at mark time.

    Kept permanent so historical reports always show exactly who/what was
    recorded that day, even if the person is later renamed, moved to another
    class, deactivated or hard deleted.
    """
    profile = getattr(student, "student_profile", None) or getattr(
        student, "teacher_profile", None
    )
    return {
        "student_name": student.full_name,
        "student_role": student.role,
        "roll_number": getattr(profile, "roll_number", "") or "",
        "employee_id": getattr(profile, "employee_id", "") or "",
        "class_name": (
            session.class_obj.name if session and session.class_obj else ""
        ),
        "section_name": (
            session.section_obj.name if session and session.section_obj else ""
        ),
    }


class AttendanceSessionViewSet(StandardResponseMixin, viewsets.ModelViewSet):
    permission_classes = [IsAdminOrTeacher]
    serializer_class = AttendanceSessionSerializer
    queryset = (
        AttendanceSession.objects.select_related("class_obj", "section_obj", "teacher")
        .prefetch_related("records__student")
        .all()
    )
    filterset_fields = ["class_obj", "section_obj", "teacher", "date", "is_active"]
    search_fields = ["session_name", "class_obj__name", "section_obj__name"]

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)


class MarkAttendanceView(generics.CreateAPIView):
    permission_classes = [IsAdminOrTeacher]
    serializer_class = MarkAttendanceRequestSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session_id = serializer.validated_data.get("session_id")
        session = None
        if session_id is not None:
            try:
                session = AttendanceSession.objects.get(id=session_id)
            except AttendanceSession.DoesNotExist:
                logger.warning(
                    f"Mark attendance failed: Session ID {session_id} not found."
                )
                raise BusinessValidationError("Attendance session not found.")

        image_file = serializer.validated_data.get("image")
        student_id = serializer.validated_data.get("student_id")
        status_choice = serializer.validated_data.get(
            "status", AttendanceRecord.Status.PRESENT
        )
        remarks = serializer.validated_data.get("remarks", "")

        student = None
        method = AttendanceRecord.Method.MANUAL
        confidence = None

        if image_file:
            # Face recognition path
            face_results = FaceRecognitionService.extract_face_embeddings(image_file)
            if not face_results:
                raise FaceNotDetectedError()
            best_face = max(face_results, key=lambda x: x["score"])

            matched_user, confidence = FaceRecognitionService.match_face(
                best_face["embedding"]
            )
            student = matched_user
            method = AttendanceRecord.Method.FACE_RECOGNITION
        elif student_id:
            try:
                student = User.objects.get(id=student_id, role=User.Role.STUDENT)
            except User.DoesNotExist:
                raise BusinessValidationError("Specified student not found.")
        else:
            raise BusinessValidationError(
                "Either camera image or student_id must be provided."
            )

        if session is not None and session.date != timezone.localdate():
            session = None

        # Teachers use the same attendance record path as students. When the
        # client does not provide a session, use the latest active session.
        if student.is_teacher():
            profile = student.teacher_profile
            if session is None:
                session = (
                    AttendanceSession.objects.filter(
                        date=timezone.localdate(), is_active=True
                    )
                    .order_by("-created_at")
                    .first()
                )
            if session is None:
                raise BusinessValidationError("No active attendance session available.")

            record, _ = AttendanceRecord.objects.update_or_create(
                session=session,
                student=student,
                defaults={
                    "status": status_choice,
                    "verification_method": method,
                    "confidence_score": confidence,
                    "remarks": remarks,
                    **_attendance_snapshot(student, session),
                },
            )
            response_data = AttendanceRecordSerializer(record).data
            face_image = (
                FaceImage.objects.filter(user=student).order_by("-created_at").first()
            )
            response_data.update(
                {
                    "person_type": "teacher",
                    "full_name": student.full_name,
                    "employee_id": profile.employee_id,
                    "subject": profile.qualification,
                    "department": profile.department,
                    "photo": (
                        request.build_absolute_uri(face_image.image.url)
                        if face_image
                        else (
                            request.build_absolute_uri(student.profile_picture.url)
                            if student.profile_picture
                            else None
                        )
                    ),
                    "recognized_at": timezone.now().isoformat(),
                }
            )
            return Response(
                {
                    "success": True,
                    "message": f"Teacher {student.full_name} recognised.",
                    "data": response_data,
                }
            )

        # Auto-resolve the session when the client did not send one: use the
        # student's class/section and today's date. This removes the #1 cause
        # of live attendance failing for properly-registered users (missing /
        # stale session id on the client).
        if session is None:
            profile = getattr(student, "student_profile", None)
            class_obj = getattr(profile, "class_obj", None)
            section_obj = getattr(profile, "section_obj", None)
            today = timezone.localdate()
            if class_obj and section_obj:
                session, _ = AttendanceSession.objects.get_or_create(
                    class_obj=class_obj,
                    section_obj=section_obj,
                    date=today,
                    session_name="Daily Attendance",
                    defaults={"teacher": request.user, "is_active": True},
                )
            else:
                latest = (
                    AttendanceSession.objects.filter(is_active=True)
                    .order_by("-date", "-created_at")
                    .first()
                )
                if latest is None:
                    raise BusinessValidationError(
                        "No attendance session available and the student has no class/section assigned."
                    )
                session = latest

        record, created = AttendanceRecord.objects.update_or_create(
            session=session,
            student=student,
            defaults={
                "status": status_choice,
                "verification_method": method,
                "confidence_score": confidence,
                "remarks": remarks,
                **_attendance_snapshot(student, session),
            },
        )

        logger.info(
            f"Attendance marked for {student.username} (ID: {student.id}) in Session {session.id} as {status_choice} via {method}."
        )

        # Enhance response with user details
        response_data = AttendanceRecordSerializer(record).data
        response_data.update(
            {
                "person_type": "student",
                "full_name": student.full_name,
                "student_name": student.full_name,
                "student_id": student.id,
                "confidence_score": confidence,
                "roll_number": (
                    getattr(student.student_profile, "roll_number", None)
                    if hasattr(student, "student_profile")
                    else None
                ),
                "class_name": (
                    session.class_obj.name if session and session.class_obj else None
                ),
                "section_name": (
                    session.section_obj.name
                    if session and session.section_obj
                    else None
                ),
                "father_name": (
                    getattr(student.student_profile, "father_name", "")
                    if hasattr(student, "student_profile")
                    else ""
                ),
                "photo": (
                    request.build_absolute_uri(
                        FaceImage.objects.filter(user=student)
                        .order_by("-created_at")
                        .first()
                        .image.url
                    )
                    if FaceImage.objects.filter(user=student).exists()
                    else (
                        request.build_absolute_uri(student.profile_picture.url)
                        if student.profile_picture
                        else None
                    )
                ),
                "recognized_at": timezone.now().isoformat(),
            }
        )

        return Response(
            {
                "success": True,
                "message": f"Attendance marked for {student.full_name} as {status_choice}.",
                "data": response_data,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class BulkMarkAttendanceView(generics.CreateAPIView):
    permission_classes = [IsAdminOrTeacher]
    serializer_class = BulkMarkAttendanceSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session_id = serializer.validated_data["session_id"]
        records_data = serializer.validated_data["records"]

        try:
            session = AttendanceSession.objects.get(id=session_id)
        except AttendanceSession.DoesNotExist:
            raise BusinessValidationError("Attendance session not found.")

        updated_records = []
        for item in records_data:
            s_id = item.get("student_id")
            s_status = item.get("status", AttendanceRecord.Status.PRESENT)
            s_remarks = item.get("remarks", "")

            try:
                student_user = User.objects.get(id=s_id)
                rec, _ = AttendanceRecord.objects.update_or_create(
                    session=session,
                    student=student_user,
                    defaults={
                        "status": s_status,
                        "verification_method": AttendanceRecord.Method.MANUAL,
                        "remarks": s_remarks,
                        **_attendance_snapshot(student_user, session),
                    },
                )
                updated_records.append(rec)
            except User.DoesNotExist:
                continue

        logger.info(
            f"Bulk attendance updated for {len(updated_records)} students in Session {session.id}."
        )

        return Response(
            {
                "success": True,
                "message": f"Bulk attendance updated for {len(updated_records)} students.",
                "data": {
                    "session_id": session.id,
                    "updated_count": len(updated_records),
                },
            }
        )


class AttendanceHistoryView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AttendanceRecordSerializer

    def get_queryset(self):
        # Same filter language as PDF/Excel export so the report screen
        # preview matches the downloaded file. History does NOT default to
        # today (omit date params to list all stored records).
        return filtered_attendance_records(self.request, default_to_today=False)


class TodayAttendanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        date_param = request.query_params.get("date")
        start_param = request.query_params.get("start_date")
        end_param = request.query_params.get("end_date")
        try:
            selected_date = (
                timezone.datetime.strptime(date_param, "%Y-%m-%d").date()
                if date_param
                else timezone.localdate()
            )
            start_date = (
                timezone.datetime.strptime(start_param, "%Y-%m-%d").date()
                if start_param
                else selected_date
            )
            end_date = (
                timezone.datetime.strptime(end_param, "%Y-%m-%d").date()
                if end_param
                else selected_date
            )
        except (TypeError, ValueError):
            start_date = timezone.localdate()
            end_date = start_date
        user = request.user
        # Live view: today's attendance always reflects the CURRENT active
        # roster, so deleted/deactivated users are excluded here.
        queryset = (
            active_attendance_records()
            .select_related("session", "student", "session__class_obj")
            .filter(session__date__range=(start_date, end_date))
        )

        class_id = request.query_params.get("class_id")
        status_param = request.query_params.get("status")
        if class_id:
            queryset = queryset.filter(session__class_obj_id=class_id)
        if status_param:
            queryset = queryset.filter(status=status_param)

        if user.is_school_admin():
            pass  # Admins/superusers see all records regardless of role field.
        elif user.is_student():
            queryset = queryset.filter(student=user)
        elif user.is_teacher():
            queryset = queryset.filter(session__teacher=user)

        serializer = AttendanceRecordSerializer(queryset, many=True)
        return Response(
            {
                "success": True,
                "date": str(start_date),
                "count": queryset.count(),
                "data": serializer.data,
            }
        )


class MonthlyAttendanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        now = timezone.localdate()
        year = int(request.query_params.get("year", now.year))
        month = int(request.query_params.get("month", now.month))

        user = request.user
        # Monthly view = historical attendance: keep every stored record so
        # past-month reports are immutable.
        queryset = (
            historical_attendance_records()
            .select_related("session", "student")
            .filter(session__date__year=year, session__date__month=month)
        )

        if user.is_school_admin():
            pass  # Admins/superusers see all records regardless of role field.
        elif user.is_student():
            queryset = queryset.filter(student=user)
        elif user.is_teacher():
            queryset = queryset.filter(session__teacher=user)

        total = queryset.count()
        present = queryset.filter(status=AttendanceRecord.Status.PRESENT).count()
        absent = queryset.filter(status=AttendanceRecord.Status.ABSENT).count()
        late = queryset.filter(status=AttendanceRecord.Status.LATE).count()

        serializer = AttendanceRecordSerializer(queryset[:100], many=True)
        return Response(
            {
                "success": True,
                "year": year,
                "month": month,
                "summary": {
                    "total": total,
                    "present": present,
                    "absent": absent,
                    "late": late,
                    "attendance_percentage": (
                        round((present / total * 100), 1) if total > 0 else 0.0
                    ),
                },
                "records": serializer.data,
            }
        )


class StudentHistoryView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AttendanceRecordSerializer

    def get_queryset(self):
        user = self.request.user
        student_id = self.request.query_params.get("student_id")

        # Immutable history (not "today"): include previously deleted users.
        queryset = historical_attendance_records().select_related("session", "student")
        if user.is_student():
            return queryset.filter(student=user)
        elif student_id:
            return queryset.filter(student_id=student_id)
        return queryset


class TeacherHistoryView(generics.ListAPIView):
    permission_classes = [IsAdminOrTeacher]
    serializer_class = AttendanceRecordSerializer

    def get_queryset(self):
        user = self.request.user
        teacher_id = self.request.query_params.get("teacher_id")

        # Immutable history (not "today"): include previously deleted users.
        queryset = historical_attendance_records().select_related("session", "student")
        if user.is_teacher():
            return queryset.filter(session__teacher=user)
        elif teacher_id:
            return queryset.filter(session__teacher_id=teacher_id)
        return queryset
