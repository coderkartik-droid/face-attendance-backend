from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from apps.accounts.models import TeacherProfile, StudentProfile
from apps.academics.models import Class, Section

User = get_user_model()


class RoleTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["username"] = user.username
        token["full_name"] = user.full_name
        token["email"] = user.email
        return token

    def validate(self, attrs):
        credentials = {"password": attrs.get("password")}
        identifier = str(attrs.get("username", "")).strip().lower()
        if not identifier:
            raise serializers.ValidationError(
                {"username": "Provide your username, roll number or employee ID."}
            )

        # Resolve the identifier to a user allowing username / email / roll
        # number / employee ID (the minimal-login requirement).
        user = None
        db_user = User.objects.filter(username__iexact=identifier).first()
        if db_user is None:
            db_user = User.objects.filter(email__iexact=identifier).first()
        if db_user is None:
            db_user = (
                StudentProfile.objects.filter(roll_number__iexact=identifier)
                .select_related("user")
                .first()
            )
            if db_user is not None:
                db_user = db_user.user
        if db_user is None:
            db_user = (
                TeacherProfile.objects.filter(employee_id__iexact=identifier)
                .select_related("user")
                .first()
            )
            if db_user is not None:
                db_user = db_user.user

        if db_user is None or not db_user.is_active:
            raise serializers.ValidationError("No active account with that identifier.")

        self.user = authenticate(
            request=self.context.get("request"),
            username=db_user.username,
            password=credentials.get("password"),
        )
        if self.user is None:
            raise serializers.ValidationError("Incorrect login credentials.")

        data = {}
        refresh = self.get_token(self.user)
        data["refresh"] = str(refresh)
        data["access"] = str(refresh.access_token)
        data["role"] = self.user.role
        data["username"] = self.user.username
        data["full_name"] = self.user.full_name
        data["email"] = self.user.email
        data["user_id"] = self.user.id
        return data


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "phone",
            "profile_picture",
        )
        read_only_fields = ("id", "role")


class TeacherProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    # These fields are deliberately kept flat so the management client can
    # update a profile and its related user in a single existing PATCH call.
    first_name = serializers.CharField(write_only=True, required=False)
    last_name = serializers.CharField(write_only=True, required=False)
    phone = serializers.CharField(write_only=True, required=False, allow_blank=True)
    email = serializers.EmailField(write_only=True, required=False)
    subject = serializers.CharField(
        source="qualification", required=False, allow_blank=True
    )
    face_registered = serializers.BooleanField(
        source="is_registration_complete", read_only=True
    )
    today_attendance_status = serializers.SerializerMethodField()

    class Meta:
        model = TeacherProfile
        fields = (
            "id",
            "user",
            "employee_id",
            "department",
            "qualification",
            "subject",
            "first_name",
            "last_name",
            "phone",
            "email",
            "is_registration_complete",
            "face_registered",
            "today_attendance_status",
            "created_at",
        )
        read_only_fields = ("is_registration_complete",)

    def get_today_attendance_status(self, obj):
        """Get today's attendance status for the teacher (Present/Absent)."""
        try:
            from apps.attendance.models import AttendanceRecord
            from core.attendance_queries import active_attendance_records
            from django.utils import timezone

            today = timezone.localdate()
            # Check if teacher has attendance record for today
            record = active_attendance_records().filter(
                student=obj.user_id,
                session__date=today
            ).first()

            if record:
                return record.status  # 'PRESENT', 'ABSENT', 'LATE', etc.
            else:
                return 'ABSENT'  # Default to absent if no record for today
        except Exception:
            return 'ABSENT'

    @transaction.atomic
    def update(self, instance, validated_data):
        user_data = {
            field: validated_data.pop(field)
            for field in ("first_name", "last_name", "phone", "email")
            if field in validated_data
        }
        for field, value in user_data.items():
            setattr(instance.user, field, value)
        if user_data:
            instance.user.save(update_fields=list(user_data))
        return super().update(instance, validated_data)


class TeacherRegisterSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    email = serializers.EmailField(write_only=True, required=False, allow_blank=True)
    first_name = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    last_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    phone = serializers.CharField(write_only=True, required=False, allow_blank=True)
    employee_id = serializers.CharField(write_only=True)
    department = serializers.CharField(write_only=True)
    qualification = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )

    class Meta:
        model = User
        fields = (
            "username",
            "password",
            "email",
            "first_name",
            "last_name",
            "phone",
            "employee_id",
            "department",
            "qualification",
        )

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(
                "A user with this username already exists."
            )
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_employee_id(self, value):
        if TeacherProfile.objects.filter(employee_id=value).exists():
            raise serializers.ValidationError(
                "A teacher with this employee ID already exists."
            )
        return value

    @transaction.atomic
    def create(self, validated_data):
        emp_id = validated_data.pop("employee_id")
        dept = validated_data.pop("department")
        qualification = validated_data.pop("qualification", "")
        phone = validated_data.pop("phone", "")

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            phone=phone,
            role=User.Role.TEACHER,
        )
        TeacherProfile.objects.create(
            user=user,
            employee_id=emp_id,
            department=dept,
            qualification=qualification,
        )
        return user


class StudentProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    first_name = serializers.CharField(write_only=True, required=False)
    last_name = serializers.CharField(write_only=True, required=False)
    phone = serializers.CharField(write_only=True, required=False, allow_blank=True)
    class_id = serializers.PrimaryKeyRelatedField(
        source="class_obj",
        queryset=Class.objects.all(),
        write_only=True,
        required=False,
    )
    section_id = serializers.PrimaryKeyRelatedField(
        source="section_obj",
        queryset=Section.objects.all(),
        write_only=True,
        required=False,
    )
    class_name = serializers.CharField(source="class_obj.name", read_only=True)
    section_name = serializers.CharField(source="section_obj.name", read_only=True)
    face_registered = serializers.BooleanField(
        source="is_registration_complete", read_only=True
    )
    attendance_percentage = serializers.SerializerMethodField()
    today_attendance_status = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = (
            "id",
            "user",
            "roll_number",
            "admission_number",
            "father_name",
            "mother_name",
            "class_obj",
            "class_id",
            "class_name",
            "section_obj",
            "section_id",
            "section_name",
            "date_of_birth",
            "gender",
            "guardian_name",
            "guardian_phone",
            "address",
            "is_registration_complete",
            "face_registered",
            "attendance_percentage",
            "today_attendance_status",
            "created_at",
            "first_name",
            "last_name",
            "phone",
        )
        read_only_fields = ("is_registration_complete",)

    def validate(self, attrs):
        class_obj = attrs.get(
            "class_obj", self.instance.class_obj if self.instance else None
        )
        section_obj = attrs.get(
            "section_obj", self.instance.section_obj if self.instance else None
        )
        if class_obj and section_obj and section_obj.class_obj_id != class_obj.id:
            raise serializers.ValidationError(
                {
                    "section_id": "Selected section does not belong to the selected class."
                }
            )
        return attrs

    @transaction.atomic
    def update(self, instance, validated_data):
        user_data = {
            field: validated_data.pop(field)
            for field in ("first_name", "last_name", "phone")
            if field in validated_data
        }
        for field, value in user_data.items():
            setattr(instance.user, field, value)
        if user_data:
            instance.user.save(update_fields=list(user_data))
        return super().update(instance, validated_data)

    def get_attendance_percentage(self, obj):
        # Optional lightweight summary. Kept lazy to avoid heavy queries.
        try:
            from apps.attendance.models import AttendanceRecord
            from core.attendance_queries import active_attendance_records

            # Reuse the shared "active users only" base queryset.
            base = active_attendance_records().filter(student=obj.user_id)
            total = base.count()
            if total == 0:
                return 0.0
            present = base.filter(status=AttendanceRecord.Status.PRESENT).count()
            return round(present / total * 100, 1)
        except Exception:
            return 0.0

    def get_today_attendance_status(self, obj):
        """Get today's attendance status for the student (Present/Absent)."""
        try:
            from apps.attendance.models import AttendanceRecord
            from core.attendance_queries import active_attendance_records
            from django.utils import timezone

            today = timezone.localdate()
            # Check if student has attendance record for today
            record = active_attendance_records().filter(
                student=obj.user_id,
                session__date=today
            ).first()

            if record:
                return record.status  # 'PRESENT', 'ABSENT', 'LATE', etc.
            else:
                return 'ABSENT'  # Default to absent if no record for today
        except Exception:
            return 'ABSENT'


class StudentRegisterSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    email = serializers.EmailField(write_only=True, required=False, allow_blank=True)
    first_name = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    last_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    father_name = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    mother_name = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    phone = serializers.CharField(write_only=True, required=False, allow_blank=True)
    roll_number = serializers.CharField(write_only=True)
    admission_number = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    class_id = serializers.IntegerField(
        write_only=True, required=False, allow_null=True
    )
    section_id = serializers.IntegerField(
        write_only=True, required=False, allow_null=True
    )
    date_of_birth = serializers.DateField(
        write_only=True, required=False, allow_null=True
    )
    gender = serializers.CharField(write_only=True, default="male")
    guardian_name = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    guardian_phone = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    address = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = (
            "username",
            "password",
            "email",
            "first_name",
            "last_name",
            "phone",
            "father_name",
            "mother_name",
            "roll_number",
            "admission_number",
            "class_id",
            "section_id",
            "date_of_birth",
            "gender",
            "guardian_name",
            "guardian_phone",
            "address",
        )

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(
                "A user with this username already exists."
            )
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_roll_number(self, value):
        if StudentProfile.objects.filter(roll_number=value).exists():
            raise serializers.ValidationError(
                "A student with this roll number already exists."
            )
        return value

    def validate_admission_number(self, value):
        if value and StudentProfile.objects.filter(admission_number=value).exists():
            raise serializers.ValidationError(
                "A student with this admission number already exists."
            )
        return value

    def validate_class_id(self, value):
        if not Class.objects.filter(id=value).exists():
            raise serializers.ValidationError("Selected class does not exist.")
        return value

    def validate_section_id(self, value):
        if not Section.objects.filter(id=value).exists():
            raise serializers.ValidationError("Selected section does not exist.")
        return value

    def validate(self, attrs):
        class_id = attrs.get("class_id")
        section_id = attrs.get("section_id")
        if (
            class_id
            and section_id
            and not Section.objects.filter(
                id=section_id, class_obj_id=class_id
            ).exists()
        ):
            raise serializers.ValidationError(
                {
                    "section_id": "Selected section does not belong to the selected class."
                }
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        roll_number = validated_data.pop("roll_number")
        admission_number = validated_data.pop("admission_number", "")
        father_name = validated_data.pop("father_name", "")
        mother_name = validated_data.pop("mother_name", "")
        class_id = validated_data.pop("class_id")
        section_id = validated_data.pop("section_id")
        dob = validated_data.pop("date_of_birth", None)
        gender = validated_data.pop("gender", "male")
        phone = validated_data.pop("phone", "")
        guardian_name = validated_data.pop("guardian_name", "")
        guardian_phone = validated_data.pop("guardian_phone", "")
        address = validated_data.pop("address", "")

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            phone=phone,
            role=User.Role.STUDENT,
        )
        StudentProfile.objects.create(
            user=user,
            roll_number=roll_number,
            admission_number=admission_number or None,
            father_name=father_name,
            mother_name=mother_name,
            class_obj_id=class_id,
            section_obj_id=section_id,
            date_of_birth=dob,
            gender=gender,
            guardian_name=guardian_name,
            guardian_phone=guardian_phone or None,
            address=address,
            is_registration_complete=False,
        )
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
