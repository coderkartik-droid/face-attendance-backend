from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.faces.views import RegisterFaceView, VerifyFaceView, FaceEmbeddingViewSet

router = DefaultRouter()
router.register(r"embeddings", FaceEmbeddingViewSet, basename="face-embedding")

urlpatterns = [
    path("register/", RegisterFaceView.as_view(), name="face_register"),
    path("verify/", VerifyFaceView.as_view(), name="face_verify"),
    path("", include(router.urls)),
]
