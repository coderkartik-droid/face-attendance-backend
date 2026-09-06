"""Reusable model and serializer field validators."""

import re

from django.core.exceptions import ValidationError
from django.utils import timezone

MOBILE_RE = re.compile(r"^\+?[0-9]{10,15}$")
EMPLOYEE_ID_RE = re.compile(r"^[A-Za-z0-9\-]{3,20}$")
ROLL_NUMBER_RE = re.compile(r"^[A-Za-z0-9\-]{1,20}$")


def validate_mobile_number(value: str) -> None:
    if not MOBILE_RE.match(value):
        raise ValidationError(
            "Enter a valid mobile number (10-15 digits, optional + prefix)."
        )


def validate_employee_id(value: str) -> None:
    if not EMPLOYEE_ID_RE.match(value):
        raise ValidationError("Employee ID must be 3-20 letters, digits or dashes.")


def validate_roll_number(value: str) -> None:
    if not ROLL_NUMBER_RE.match(value):
        raise ValidationError("Roll number must be 1-20 letters, digits or dashes.")


def validate_date_of_birth(value) -> None:
    today = timezone.localdate()
    age = (
        today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    )
    if value > today:
        raise ValidationError("Date of birth cannot be in the future.")
    if age < 3 or age > 100:
        raise ValidationError("Date of birth implies an implausible age.")


def validate_image_extension(value) -> None:
    allowed = ("image/jpeg", "image/png", "image/webp")
    if getattr(value, "content_type", None) not in allowed:
        raise ValidationError("Only JPEG, PNG or WEBP images are allowed.")
