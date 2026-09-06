from rest_framework import viewsets

from core.mixins import StandardResponseMixin
from core.permissions import IsAdminOrTeacher, ReadOnly
from apps.academics.models import Class, Section, Subject
from apps.academics.serializers import (
    ClassSerializer,
    SectionSerializer,
    SubjectSerializer,
)


class ClassViewSet(StandardResponseMixin, viewsets.ModelViewSet):
    permission_classes = [IsAdminOrTeacher | ReadOnly]
    serializer_class = ClassSerializer
    queryset = Class.objects.prefetch_related("sections").all()
    search_fields = ["name", "code"]


class SectionViewSet(StandardResponseMixin, viewsets.ModelViewSet):
    permission_classes = [IsAdminOrTeacher | ReadOnly]
    serializer_class = SectionSerializer
    queryset = Section.objects.select_related("class_obj").all()
    filterset_fields = ["class_obj"]
    search_fields = ["name", "room_number"]


class SubjectViewSet(StandardResponseMixin, viewsets.ModelViewSet):
    permission_classes = [IsAdminOrTeacher | ReadOnly]
    serializer_class = SubjectSerializer
    queryset = Subject.objects.all()
    search_fields = ["name", "code", "department"]
