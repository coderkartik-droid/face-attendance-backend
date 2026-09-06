from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.academics.views import ClassViewSet, SectionViewSet, SubjectViewSet

router = DefaultRouter()
router.register(r"classes-list", ClassViewSet, basename="class-detail")
router.register(r"sections-list", SectionViewSet, basename="section-detail")
router.register(r"subjects-list", SubjectViewSet, basename="subject-detail")

urlpatterns = [
    path("", include(router.urls)),
]
