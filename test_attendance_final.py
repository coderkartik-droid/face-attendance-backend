from apps.accounts.serializers import TeacherProfileSerializer
from apps.accounts.models import TeacherProfile

teachers = TeacherProfile.objects.all()
print('Total teachers:', teachers.count())
for t in teachers:
    serializer = TeacherProfileSerializer(t)
    print('Teacher:', t.user.full_name, 'Attendance Status:', serializer.data.get('today_attendance_status', 'N/A'))