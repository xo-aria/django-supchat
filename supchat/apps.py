from django.apps import AppConfig


class SupchatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "supchat"
    verbose_name = "Support chat"

    def ready(self):  # pragma: no cover - import side effects only
        from . import signals  # noqa: F401
