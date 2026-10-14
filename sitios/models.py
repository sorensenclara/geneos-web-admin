"""Sitios web administrados y sus líneas de producto, contacto, publicación y accesos por rol."""
from django.contrib.auth.models import Group
from django.db import models
from wagtail.admin.panels import FieldPanel, FieldRowPanel, HelpPanel, MultiFieldPanel, ObjectList, TabbedInterface

ROLES = [("editor", "Editor"), ("publicador", "Publicador"), ("administrador", "Administrador")]
NIVEL = {"editor": 1, "publicador": 2, "administrador": 3}


class SitioWeb(models.Model):
    MOTORES = [("comercial", "Sitio comercial (GERP, GEAGRO, GEMA)"), ("institucional", "Sitio institucional de GENEOS (conexión en etapa 7)")]
    DESTINOS = [("carpeta", "Carpeta local con versiones (pruebas)"), ("comando", "Comando de despliegue (proveedor a definir)")]

    clave = models.SlugField("Clave", unique=True, help_text="geneos, gerp, geagro o gema. Coincide con el motor de sitios.")
    nombre = models.CharField("Nombre", max_length=60)
    site = models.OneToOneField("wagtailcore.Site", verbose_name="Sitio de Wagtail", null=True, blank=True, on_delete=models.SET_NULL, related_name="sitio_web")
    dominio = models.URLField("Dominio público", blank=True, help_text="Ej.: https://gerp.ar. Puede quedar vacío si todavía no está definido.")
    dominio_confirmado = models.BooleanField("Dominio confirmado", default=False,
                                             help_text="Mientras no esté confirmado, la web se genera sin URL canónica ni sitemap.")
    color = models.CharField("Color del sitio", max_length=7, default="#178943")
    motor = models.CharField("Generador", max_length=20, choices=MOTORES, default="comercial")
    orden = models.PositiveSmallIntegerField(default=0)

    usa_blog = models.BooleanField("Blog", default=True)
    usa_planes = models.BooleanField("Planes y precios", default=False)
    usa_comparador = models.BooleanField("Comparador de funcionalidades", default=False)
    usa_testimonios = models.BooleanField("Testimonios", default=False)
    usa_formularios = models.BooleanField("Formulario de demo conectado", default=True)

    whatsapp = models.CharField("WhatsApp (solo números)", max_length=20, default="5492494521418")
    whatsapp_visible = models.CharField("WhatsApp como se muestra", max_length=30, default="+54 9 2494 521418")
    telefono = models.CharField("Teléfono", max_length=30, default="+54 9 249 452-1418")
    email = models.EmailField("Email de contacto", default="info@geneos.com.ar")
    email_pedidos = models.EmailField("Email que recibe los pedidos de demo", default="info@geneos.com.ar")
    direccion = models.CharField("Dirección", max_length=120, blank=True, default="Alem 1015, Tandil")
    instagram = models.URLField(blank=True)
    facebook = models.URLField(blank=True)
    linkedin = models.URLField(blank=True)
    texto_consentimiento = models.CharField("Consentimiento del formulario", max_length=300,
        default="Acepto que GENEOS use estos datos solo para responder esta consulta. Puedo pedir su baja escribiendo a info@geneos.com.ar.")

    destino = models.CharField("Destino de publicación", max_length=20, choices=DESTINOS, default="carpeta")
    comando_despliegue = models.CharField("Comando de despliegue", max_length=500, blank=True,
        help_text="Se ejecuta después de generar y validar la web. {carpeta} se reemplaza por la carpeta generada. "
                  "Ej.: npx wrangler pages deploy {carpeta} --project-name=gerp")
    publicar_al_aprobar = models.BooleanField("Actualizar la web al aprobar cada cambio", default=False,
                                              help_text="Si está apagado, los cambios aprobados se acumulan hasta que tocás «Publicar en la web».")
    actualizado = models.DateTimeField(auto_now=True)

    panels_general = [
        MultiFieldPanel([FieldPanel("nombre"), FieldPanel("clave", read_only=True), FieldRowPanel([FieldPanel("dominio"), FieldPanel("dominio_confirmado")]), FieldPanel("color")], "Sitio"),
        MultiFieldPanel([FieldRowPanel([FieldPanel("usa_blog"), FieldPanel("usa_planes"), FieldPanel("usa_comparador")]),
                         FieldRowPanel([FieldPanel("usa_testimonios"), FieldPanel("usa_formularios")])], "Módulos del sitio"),
        HelpPanel("<p>Los precios, la moneda, el IVA y la leyenda de vigencia se cargan en cada plan (Oferta comercial → Planes y precios).</p>"),
    ]
    panels_contacto = [
        HelpPanel("<p>Estos datos se usan en todos los botones de WhatsApp, el footer, los formularios y los datos estructurados del sitio.</p>"),
        FieldRowPanel([FieldPanel("whatsapp"), FieldPanel("whatsapp_visible")]),
        FieldRowPanel([FieldPanel("telefono"), FieldPanel("email")]),
        FieldPanel("direccion"), FieldRowPanel([FieldPanel("instagram"), FieldPanel("facebook"), FieldPanel("linkedin")]),
        FieldPanel("email_pedidos"), FieldPanel("texto_consentimiento"),
    ]
    panels_publicacion = [FieldPanel("destino"), FieldPanel("comando_despliegue"), FieldPanel("publicar_al_aprobar")]
    edit_handler = TabbedInterface([ObjectList(panels_general, heading="General"), ObjectList(panels_contacto, heading="Contacto y formularios"),
                                    ObjectList(panels_publicacion, heading="Publicación")])

    class Meta:
        ordering = ["orden"]
        verbose_name = "sitio web"
        verbose_name_plural = "sitios web"

    def __str__(self):
        return self.nombre

    @property
    def dominio_publico(self):
        return self.dominio.rstrip("/") if self.dominio and self.dominio_confirmado else ""


class LineaProducto(models.Model):
    sitio = models.ForeignKey(SitioWeb, on_delete=models.CASCADE, related_name="lineas")
    clave = models.SlugField("Clave")
    nombre = models.CharField("Nombre", max_length=60)
    ruta = models.CharField("Ruta en el sitio", max_length=60, help_text="Ej.: cereales/")
    color = models.CharField(max_length=7, blank=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sitio__orden", "orden"]
        unique_together = [("sitio", "clave")]
        verbose_name = "línea de producto"
        verbose_name_plural = "líneas de producto"

    def __str__(self):
        return f"{self.sitio.nombre} {self.nombre}"


class AccesoSitio(models.Model):
    """Qué puede hacer un grupo en un sitio (o en una sola línea de GEAGRO)."""
    grupo = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="accesos_sitio")
    sitio = models.ForeignKey(SitioWeb, on_delete=models.CASCADE, related_name="accesos")
    linea = models.ForeignKey(LineaProducto, null=True, blank=True, on_delete=models.CASCADE,
                              help_text="Vacío: todo el sitio. Con una línea: solo esa línea (y el contenido general del sitio en modo lectura).")
    rol = models.CharField(max_length=20, choices=ROLES)

    class Meta:
        verbose_name = "acceso a sitio"
        verbose_name_plural = "accesos a sitios"

    def __str__(self):
        return f"{self.grupo} → {self.linea or self.sitio} ({self.get_rol_display()})"


from wagtail.models import AbstractGroupApprovalTask  # noqa: E402


class AprobacionSitio(AbstractGroupApprovalTask):
    """Aprobación por grupos que además respeta el sitio y la línea: un publicador de GEMA no ve ni aprueba cambios de GERP."""

    def _ok(self, obj, user):
        from publicacion.servicio import sitio_de
        from .permisos import puede
        sitio = sitio_de(obj)
        linea = getattr(obj, "linea_id", None)
        return sitio is None or puede(user, sitio.pk, linea, nivel=2)

    def user_can_access_editor(self, obj, user):
        return super().user_can_access_editor(obj, user) and self._ok(obj, user)

    def locked_for_user(self, obj, user):
        return super().locked_for_user(obj, user) or not self._ok(obj, user)

    def get_actions(self, obj, user):
        return super().get_actions(obj, user) if self._ok(obj, user) else []

    @classmethod
    def get_description(cls):
        return "Aprobación por un publicador del sitio (o de la línea) del contenido."

    class Meta:
        verbose_name = "aprobación por sitio"
        verbose_name_plural = "aprobaciones por sitio"
