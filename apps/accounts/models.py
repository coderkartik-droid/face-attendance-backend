from django.contrib.auth.models import AbstractUser
from django.db import models
from core.validators import (
    validate_mobile_number,
    validate_employee_id,
    validate_roll_number,
    validate_date_of_birth,
)


class School(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.code})"


class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super Admin"
        SCHOOL_ADMIN = "school_admin", "School Admin"
        TEACHER = "teacher", "Teacher"
        STUDENT = "student", "Student"

    school = models.ForeignKey(
        School,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
        help_text="Role of the user in the attendance system",
    )
    phone = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        validators=[validate_mobile_number],
    )
    profile_picture = models.ImageField(
        upload_to="profiles/", blank=True, null=True
    )

    @property
    def full_name(self):
        name = f"{self.first_name} {self.last_name}".strip()
        return name if name else self.username

    def is_super_admin(self):
        return self.role == self.Role.SUPER_ADMIN or self.is_superuser

    def is_school_admin(self):
        return self.role in [self.Role.SUPER_ADMIN, self.Role.SCHOOL_ADMIN] or self.is_superuser

    def is_teacher(self):
        return self.role == self.Role.TEACHER

    def is_student(self):
        return self.role == self.Role.STUDENT

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class TeacherProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="teacher_profile"
    )
    employee_id = models.CharField(
        max_length=20, unique=True, validators=[validate_employee_id]
    )
    department = models.CharField(max_length=100)
    qualification = models.CharField(max_length=100, blank=True)
    is_registration_complete = models.BooleanField(
        default=False,
        help_text="True only after teacher face embeddings are successfully captured",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Teacher: {self.user.full_name} ({self.employee_id})"


class StudentProfile(models.Model):
    GENDER_CHOICES = (
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
    )

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="student_profile"
    )
    roll_number = models.CharField(
        max_length=20, unique=True, validators=[validate_roll_number]
    )
    admission_number = models.CharField(
        max_length=20, unique=True, blank=True, null=True,
        help_text="School admission number for the student",
    )
    father_name = models.CharField(max_length=100, blank=True)
    mother_name = models.CharField(max_length=100, blank=True)
    class_obj = models.ForeignKey(
        "academics.Class",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )
    section_obj = models.ForeignKey(
        "academics.Section",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )
    date_of_birth = models.DateField(
        null=True, blank=True, validators=[validate_date_of_birth]
    )
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default="male")
    guardian_name = models.CharField(max_length=100, blank=True)
    guardian_phone = models.CharField(
        max_length=15, blank=True, null=True, validators=[validate_mobile_number]
    )
    address = models.TextField(blank=True)
    is_registration_complete = models.BooleanField(
        default=False,
        help_text="True only after student face embeddings are successfully captured",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        status_str = "Complete" if self.is_registration_complete else "Pending Face Registration"
        return f"Student: {self.user.full_name} (Roll: {self.roll_number}) - [{status_str}]"
