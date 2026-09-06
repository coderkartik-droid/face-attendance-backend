from apps.accounts.models import User, TeacherProfile
from apps.accounts.serializers import TeacherProfileSerializer
from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.academics.models import Class, Section
from django.utils import timezone
import datetime

# Create test teacher
teacher_user, created = User.objects.get_or_create(
    username='teacher1',
    defaults={
        'first_name': 'John',
        'last_name': 'Smith',
        'email': 'john@school.com',
        'role': 'teacher'
    }
)
if created:
    teacher_user.set_password('password123')
    teacher_user.save()
    print('Test teacher created:', teacher_user.full_name)

teacher_profile, _ = TeacherProfile.objects.get_or_create(
    user=teacher_user,
    defaults={
        'employee_id': 'EMP001',
        'department': 'Mathematics',
        'qualification': 'M.Sc'
    }
)

# Create test class and session
cls, _ = Class.objects.get_or_create(name='Test Class', code='TC', defaults={'description': 'Test'})
sec, _ = Section.objects.get_or_create(name='A', class_obj=cls, defaults={'room_number': '101'})

today = timezone.localdate()
session, _ = AttendanceSession.objects.get_or_create(
    class_obj=cls,
    section_obj=sec,
    date=today,
    defaults={
        'session_name': 'Daily Attendance',
        'teacher': teacher_user
    }
)

# Test attendance status without record
serializer = TeacherProfileSerializer(teacher_profile)
print('Attendance status (no record):', serializer.data.get('today_attendance_status', 'N/A'))

# Create attendance record
record, _ = AttendanceRecord.objects.get_or_create(
    session=session,
    student=teacher_user,
    defaults={
        'status': 'PRESENT',
        'verification_method': 'FACE_RECOGNITION'
    }
)

# Test attendance status with record
serializer = TeacherProfileSerializer(teacher_profile)
print('Attendance status (with record):', serializer.data.get('today_attendance_status', 'N/A'))

print('Test completed successfully')