"""Reusable viewset mixins."""

from rest_framework import status
from rest_framework.response import Response


import logging

from apps.faces.models import FaceEmbedding, FaceImage

logger = logging.getLogger(__name__)


def _purge_face_data(user):
    """Delete all stored face data (embeddings, images and media files) for a
    user so a deleted person can never be recognised again."""
    embeddings = FaceEmbedding.objects.filter(user=user)
    images = FaceImage.objects.filter(user=user)
    for image in images:
        if image.image:
            image.image.delete(save=False)
    embeddings.delete()
    images.delete()
    logger.info("Purged face data for deleted user %s.", user.username)


class StandardResponseMixin:
    """Wraps list/retrieve/create/update payloads into a {success, message, data} envelope."""

    message = "Success."

    def _envelope(self, data, message=None, status_code=None, meta=None):
        body = {
            "success": status_code is None or status_code < 400,
            "message": message or self.message,
            "data": data,
        }
        if meta is not None:
            body["meta"] = meta
        return Response(body, status=status_code or status.HTTP_200_OK)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        # DRF pagination replaces response.data with a dict containing
        # "results". Unwrap it so clients always receive a plain list in
        # "data", and expose pagination metadata under "meta".
        if isinstance(response.data, dict) and "results" in response.data:
            meta = {
                k: response.data[k]
                for k in ("count", "total_pages", "current_page", "next", "previous")
                if k in response.data
            }
            return self._envelope(response.data["results"], meta=meta)
        return self._envelope(response.data)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return self._envelope(response.data)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return self._envelope(
            response.data, "Created successfully.", status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return self._envelope(response.data, "Updated successfully.")

    def partial_update(self, request, *args, **kwargs):
        response = super().partial_update(request, *args, **kwargs)
        return self._envelope(response.data, "Updated successfully.")

    def perform_destroy(self, instance):
        # Remove all face data before the profile (and its user, via CASCADE)
        # is deleted so the person is never recognised by Live Attendance.
        _purge_face_data(instance.user)
        instance.delete()

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return self._envelope(None, "Deleted successfully.", status.HTTP_200_OK)
