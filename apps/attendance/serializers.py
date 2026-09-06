from rest_framework import serializers
from apps.attendance.models import AttendanceSession, AttendanceRecord


class AttendanceRecordSerializer(serializers.ModelSerializer):
    # Identifiers are read from the frozen snapshot columns so history stays
    # correct and readable even after a person is edited, moved or deleted.
    student_name = serializers.CharField(read_only=True)
    roll_number = serializers.CharField(read_only=True)
    employee_id = serializers.CharField(read_only=True)
    class_name = serializers.CharField(read_only=True)
    section_name = serializers.CharField(read_only=True)
    session_name = serializers.CharField(
        source="session.session_name", read_only=True, default=""
    )

    class Meta:
        model = AttendanceRecord
        fields = (
            "id",
            "session",
            "session_name",
            "student",
            "student_name",
            "roll_number",
            "employee_id",
            "class_name",
            "section_name",
            "status",
            "verification_method",
            "confidence_score",
            "marked_at",
            "remarks",
        )


class AttendanceSessionSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source="class_obj.name", read_only=True)
    section_name = serializers.CharField(source="section_obj.name", read_only=True)
    teacher_name = serializers.CharField(source="teacher.full_name", read_only=True)
    records = AttendanceRecordSerializer(many=True, read_only=True)

    class Meta:
        model = AttendanceSession
        fields = (
            "id",
            "class_obj",
            "class_name",
            "section_obj",
            "section_name",
            "teacher",
            "teacher_name",
            "date",
            "session_name",
            "is_active",
            "records",
            "created_at",
        )
        # The teacher is always the authenticated user performing the request.
        read_only_fields = ("teacher",)


class MarkAttendanceRequestSerializer(serializers.Serializer):
    session_id = serializers.IntegerField(required=False, allow_null=True)
    image = serializers.ImageField(required=False, help_text="Camera frame for face recognition")
    student_id = serializers.IntegerField(required=False, help_text="For manual attendance override")
    status = serializers.ChoiceField(
        choices=AttendanceRecord.Status.choices,
        default=AttendanceRecord.Status.PRESENT,
    )
    remarks = serializers.CharField(required=False, allow_blank=True, default="")


class BulkMarkAttendanceSerializer(serializers.Serializer):
    session_id = serializers.IntegerField(required=True)
    records = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
        help_text="List of dicts: {'student_id': int, 'status': 'PRESENT'|'ABSENT'|'LATE'}",
    )
