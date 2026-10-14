from django.apps import AppConfig


class PublishingConfig(AppConfig):
    name = "publishing"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from wagtail.signals import published

        from .models import Plan
        from .publisher import publish_site

        def on_publish(sender, instance, revision=None, **kwargs):
            user = getattr(revision, "user", None)
            publish_site(instance.site, f"Plan {instance.name} publicado por {getattr(user, "username", None) or "sistema"}")

        published.connect(on_publish, sender=Plan, dispatch_uid="publish_site_on_plan")
