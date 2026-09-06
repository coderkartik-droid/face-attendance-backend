import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


@receiver(post_save, sender=User)
def log_user_creation(sender, instance, created, **kwargs):
    if created:
        logger.info(
            f"New user registered: Username '{instance.username}', Role '{instance.role}', ID {instance.id}"
        )


def ensure_default_admin(sender, **kwargs):
    """
    Guarantee a Super Admin account exists and can never be demoted.

    - Creates the default Super Admin (admin / admin123) when no superuser exists.
    - If an "admin" user already exists (regardless of its current role), it is
      repaired back to SUPER_ADMIN so a super admin can never silently become a
      student/teacher.
    """
    try:
        admin = User.objects.filter(username="admin").first()

        if admin is not None:
            needs_fix = (
                admin.role != User.Role.SUPER_ADMIN
                or not admin.is_staff
                or not admin.is_superuser
                or not admin.is_active
            )
            if needs_fix:
                admin.role = User.Role.SUPER_ADMIN
                admin.is_staff = True
                admin.is_superuser = True
                admin.is_active = True
                admin.save(update_fields=["role", "is_staff", "is_superuser", "is_active"])
                logger.info("Repaired existing 'admin' account back to Super Admin.")
            return

        # No "admin" user exists — create the default super admin only if none exists.
        if not User.objects.filter(is_superuser=True).exists():
            User.objects.create_user(
                username="admin",
                email="admin@school.com",
                password="admin123",
                first_name="Super",
                last_name="Admin",
                role=User.Role.SUPER_ADMIN,
                is_staff=True,
                is_superuser=True,
            )
            logger.info("Default Super Admin account created successfully (Username: admin, Password: admin123).")
    except Exception as e:
        logger.warning(f"Default admin initialization skipped: {e}")
