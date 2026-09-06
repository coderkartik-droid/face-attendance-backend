"""Role-based permission classes."""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsSuperAdmin(BasePermission):
    message = "Only Super Administrators can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.role == "super_admin" or request.user.is_superuser)
        )


class IsSchoolAdmin(BasePermission):
    """Allows SUPER_ADMIN and SCHOOL_ADMIN (plus Django superusers)."""

    message = "Only School Administrators can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (
                request.user.role in ["super_admin", "school_admin"]
                or request.user.is_superuser
            )
        )


class IsAdmin(IsSchoolAdmin):
    """Alias for backwards compatibility."""
    pass


class IsTeacher(BasePermission):
    message = "Only teachers can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == "teacher"
        )


class IsStudent(BasePermission):
    message = "Only students can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == "student"
        )


class IsAdminOrTeacher(BasePermission):
    message = "Only administrators or teachers can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (
                request.user.role in ["super_admin", "school_admin", "teacher"]
                or request.user.is_superuser
            )
        )


class IsSelfOrAdminOrTeacher(BasePermission):
    """Object-level: users may read/update their own profile; admins & teachers may access any."""

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.role in ["super_admin", "school_admin"] or user.is_superuser:
            return True
        if getattr(obj, "user_id", None) == user.id:
            return True
        return user.role == "teacher" and getattr(obj, "role", None) == "student"


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS
