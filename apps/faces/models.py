from django.conf import settings
from django.db import models


class FaceEmbedding(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="face_embeddings",
    )
    embedding = models.JSONField(
        help_text="512-dimensional vector embedding stored as a JSON array"
    )
    quality_score = models.FloatField(default=1.0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"FaceEmbedding for {self.user.username} (ID: {self.id})"


class FaceImage(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="face_images",
    )
    image = models.ImageField(upload_to="faces/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"FaceImage for {self.user.username} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
