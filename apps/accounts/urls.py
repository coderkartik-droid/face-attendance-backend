from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import (
    RoleTokenObtainPairView,
    MeView,
    RegisterTeacherView,
    RegisterStudentView,
    ChangePasswordView,
    StudentViewSet,
    TeacherViewSet,
)

router = DefaultRouter()
router.register(r"students", StudentViewSet, basename="student-detail")
router.register(r"teachers", TeacherViewSet, basename="teacher-detail")

urlpatterns = [
    path("login/", RoleTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", MeView.as_view(), name="user_me"),
    path("register/teacher/", RegisterTeacherView.as_view(), name="register_teacher"),
    path("register/student/", RegisterStudentView.as_view(), name="register_student"),
    path("change-password/", ChangePasswordView.as_view(), name="change_password"),
    path("", include(router.urls)),
]
