from django.db import models


class Class(models.Model):
    name = models.CharField(max_length=50, unique=True)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Classes"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Section(models.Model):
    name = models.CharField(max_length=20)
    class_obj = models.ForeignKey(
        Class, on_delete=models.CASCADE, related_name="sections"
    )
    room_number = models.CharField(max_length=30, blank=True)
    capacity = models.PositiveIntegerField(default=40)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("name", "class_obj")
        ordering = ["class_obj__name", "name"]

    def __str__(self):
        return f"{self.class_obj.name} - Section {self.name}"


class Subject(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    department = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.code})"
