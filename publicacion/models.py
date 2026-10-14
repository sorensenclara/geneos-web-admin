from django.conf import settings
from django.db import models

from sitios.models import SitioWeb


class Despliegue(models.Model):
    """Cada generación de una web: vista previa del sitio completo o publicación."""
    TIPOS = [("publicacion", "Publicación"), ("vista_previa", "Vista previa"), ("vuelta_atras", "Vuelta a una versión anterior")]
    ESTADOS = [("en_curso", "En curso"), ("ok", "Publicado"), ("fallo", "Falló")]
    sitio = models.ForeignKey(SitioWeb, on_delete=models.CASCADE, related_name="despliegues")
    tipo = models.CharField(max_length=20, choices=TIPOS, default="publicacion")
    estado = models.CharField(max_length=10, choices=ESTADOS, default="en_curso")
    version = models.CharField("Versión", max_length=40, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    motivo = models.CharField(max_length=200, blank=True)
    iniciado = models.DateTimeField(auto_now_add=True)
    finalizado = models.DateTimeField(null=True, blank=True)
    registro = models.TextField(blank=True)
    carpeta = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-iniciado"]
        verbose_name = "publicación en la web"
        verbose_name_plural = "publicaciones en la web"

    def __str__(self):
        return f"{self.sitio} · {self.get_estado_display()} · {self.iniciado:%d/%m/%Y %H:%M}"
