"""PoC del circuito de publicación de GENEOS Web Admin.

Plan (snippet de Wagtail con borrador, revisiones, vista previa y aprobación) → al publicarse,
se regenera el sitio estático con el exportador actual y se cambia la versión pública de forma atómica.
"""
from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.models import (DraftStateMixin, LockableMixin, PreviewableMixin, RevisionMixin, WorkflowMixin)


class Plan(WorkflowMixin, DraftStateMixin, LockableMixin, RevisionMixin, PreviewableMixin, models.Model):
    site = models.CharField("Sitio", max_length=20, default="gerp")
    key = models.SlugField("Clave", max_length=20)
    name = models.CharField("Nombre", max_length=40)
    price = models.CharField("Abono mensual", max_length=20, help_text="Formato de la web, p. ej. 178.500")
    impl = models.CharField("Implementación", max_length=20)
    sort_order = models.PositiveSmallIntegerField("Orden", default=0)

    panels = [FieldPanel("name"), FieldPanel("price"), FieldPanel("impl"), FieldPanel("sort_order")]

    class Meta:
        ordering = ["sort_order"]
        verbose_name = "plan"

    def __str__(self):
        return f"{self.site.upper()} {self.name}"

    @property
    def price_num(self):
        return int(self.price.replace(".", ""))

    # Vista previa: el mismo sitio estático, generado con el borrador en una carpeta temporal
    preview_modes = [("home", "Home de GERP"), ("landing", "Landing del plan")]

    def serve_preview(self, request, mode_name):
        from .publisher import render_preview
        return render_preview(self, mode_name)


class PublishJob(models.Model):
    STATUS = [("running", "En curso"), ("ok", "Publicado"), ("failed", "Falló")]
    site = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=STATUS, default="running")
    trigger = models.CharField("Origen", max_length=200)
    release = models.CharField("Versión", max_length=40, blank=True)
    started = models.DateTimeField(auto_now_add=True)
    finished = models.DateTimeField(null=True, blank=True)
    log = models.TextField(blank=True)

    class Meta:
        ordering = ["-started"]
        verbose_name = "publicación"
        verbose_name_plural = "publicaciones"

    def __str__(self):
        return f"{self.site} · {self.get_status_display()} · {self.started:%d/%m %H:%M}"
