"""Unified API exception handling with consistent error payloads."""

import logging

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class BusinessValidationError(exceptions.APIException):
    """Raised by services when a business rule is violated."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Business rule violation."
    default_code = "business_error"


class FaceNotDetectedError(BusinessValidationError):
    default_detail = "No face detected in the uploaded image."
    default_code = "face_not_detected"


class FaceNotMatchedError(exceptions.APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Face not recognized."
    default_code = "face_not_matched"


class DuplicateAttendanceError(BusinessValidationError):
    default_detail = "Attendance has already been marked for today."
    default_code = "duplicate_attendance"


def api_exception_handler(exc, context):
    """Wrap all errors into {success, message, errors} JSON shape."""
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)

    if response is None:
        logger.exception("Unhandled server error", exc_info=exc)
        return Response(
            {
                "success": False,
                "message": "Internal server error. Please try again later.",
                "errors": None,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    detail = response.data
    message = "Request failed."
    errors = None

    if isinstance(detail, dict):
        if "detail" in detail:
            message = str(detail.pop("detail"))
            errors = detail or None
        else:
            first_field = next(iter(detail), None)
            if first_field is not None:
                message = f"{first_field}: {detail[first_field]}"
            errors = detail
    elif isinstance(detail, list) and detail:
        message = str(detail[0])
        errors = detail

    response.data = {
        "success": False,
        "message": message,
        "errors": errors,
    }
    return response
