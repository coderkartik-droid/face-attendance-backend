from django.contrib import admin
from apps.faces.models import FaceEmbedding, FaceImage


@admin.register(FaceEmbedding)
class FaceEmbeddingAdmin(admin.ModelAdmin):
    list_display = ("user", "quality_score", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("user__username", "user__first_name", "user__last_name")


@admin.register(FaceImage)
class FaceImageAdmin(admin.ModelAdmin):
    list_display = ("user", "image", "created_at")
    search_fields = ("user__username",)
