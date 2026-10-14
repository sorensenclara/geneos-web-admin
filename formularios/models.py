from django.db import models
from wagtail.admin.panels import FieldPanel, FieldRowPanel, MultiFieldPanel

from sitios.models import SitioWeb


class SolicitudDemo(models.Model):
    """Pedido de demo recibido desde el formulario de una web. Los datos personales solo se usan para responder."""
    ESTADOS = [("nuevo", "Nuevo"), ("contactado", "Contactado"), ("demo", "Demo agendada"), ("cliente", "Cliente"), ("cerrado", "Cerrado"), ("descartado", "Descartado")]
    sitio = models.ForeignKey(SitioWeb, on_delete=models.PROTECT, related_name="solicitudes")
    producto = models.CharField("Producto", max_length=60, blank=True)
    plan = models.CharField("Plan o versión", max_length=60, blank=True)
    nombre = models.CharField(max_length=120)
    empresa = models.CharField(max_length=120, blank=True)
    email = models.EmailField()
    telefono = models.CharField("Teléfono", max_length=40, blank=True)
    localidad = models.CharField(max_length=120, blank=True)
    superficie = models.CharField("Superficie (ha)", max_length=20, blank=True)
    mensaje = models.TextField(blank=True)
    pagina = models.CharField("Página de origen", max_length=200, blank=True)
    estado = models.CharField(max_length=12, choices=ESTADOS, default="nuevo")
    notas = models.TextField("Notas internas", blank=True)
    consentimiento = models.DateTimeField("Consentimiento otorgado")
    email_enviado = models.BooleanField("Aviso por email enviado", default=False)
    ip_hash = models.CharField(max_length=64, blank=True, help_text="Huella anónima de la IP (no se guarda la IP).")
    creado = models.DateTimeField("Recibido", auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    panels = [
        MultiFieldPanel([FieldRowPanel([FieldPanel("estado")]), FieldPanel("notas")], "Seguimiento"),
        MultiFieldPanel([FieldRowPanel([FieldPanel("sitio", read_only=True), FieldPanel("producto", read_only=True), FieldPanel("plan", read_only=True)]),
                         FieldRowPanel([FieldPanel("nombre", read_only=True), FieldPanel("empresa", read_only=True)]),
                         FieldRowPanel([FieldPanel("email", read_only=True), FieldPanel("telefono", read_only=True)]),
                         FieldRowPanel([FieldPanel("localidad", read_only=True), FieldPanel("superficie", read_only=True)]),
                         FieldPanel("mensaje", read_only=True), FieldRowPanel([FieldPanel("pagina", read_only=True), FieldPanel("creado", read_only=True)])],
                        "Pedido recibido"),
    ]

    class Meta:
        ordering = ["-creado"]
        verbose_name = "pedido de demo"
        verbose_name_plural = "pedidos de demo"

    def __str__(self):
        return f"{self.nombre} · {self.producto or self.sitio} · {self.creado:%d/%m/%Y}"
