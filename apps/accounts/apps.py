from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Accounts (Users, Students, Teachers)"

    def ready(self):
        try:
            import apps.accounts.signals  # noqa
            from apps.accounts.signals import ensure_default_admin
            post_migrate.connect(ensure_default_admin, sender=self)
        except Exception:
            pass
