from rest_framework import serializers
from apps.academics.models import Class, Section, Subject


class SectionSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source="class_obj.name", read_only=True)

    class Meta:
        model = Section
        fields = ("id", "name", "class_obj", "class_name", "room_number", "capacity", "created_at")


class ClassSerializer(serializers.ModelSerializer):
    sections = SectionSerializer(many=True, read_only=True)

    class Meta:
        model = Class
        fields = ("id", "name", "code", "description", "sections", "created_at")


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ("id", "name", "code", "department", "created_at")
