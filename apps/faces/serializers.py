from rest_framework import serializers
from apps.faces.models import FaceEmbedding, FaceImage
from apps.accounts.serializers import UserSerializer


class FaceImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = FaceImage
        fields = ("id", "user", "image", "created_at")


class FaceEmbeddingSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = FaceEmbedding
        fields = ("id", "user", "quality_score", "is_active", "created_at")


class FaceRegisterRequestSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=True)
    images = serializers.ListField(
        child=serializers.ImageField(),
        allow_empty=False,
        min_length=5,
        max_length=5,
        help_text="Exactly 5 face sample images are required",
    )
    replace_existing = serializers.BooleanField(
        default=True,
        required=False,
        help_text="Deactivate previous face embeddings for this user to avoid duplicates",
    )


class FaceVerifyRequestSerializer(serializers.Serializer):
    image = serializers.ImageField(required=True)
