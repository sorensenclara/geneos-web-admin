from django.apps import AppConfig


class PublicacionConfig(AppConfig):
    name = "publicacion"
    verbose_name = "Publicación"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import signals  # noqa: F401
