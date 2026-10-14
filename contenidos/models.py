"""Contenidos de los sitios: páginas, artículos de blog, planes, funcionalidades, FAQ, testimonios y recursos.

Cada dato existe una sola vez. El generador de las webs lo toma de acá: al cambiar un precio se actualizan
la home, la landing del plan, el comparador y los datos estructurados.
"""
from django import forms
from django.db import models
from django.utils.html import strip_tags
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey, ParentalManyToManyField
from modelcluster.models import ClusterableModel
from taggit.models import TaggedItemBase
from wagtail import blocks
from wagtail.admin.forms import WagtailAdminModelForm, WagtailAdminPageForm
from wagtail.admin.panels import (FieldPanel, FieldRowPanel, HelpPanel, InlinePanel, MultiFieldPanel, ObjectList,
                                  TabbedInterface)
from wagtail.contrib.table_block.blocks import TableBlock
from wagtail.fields import RichTextField, StreamField
from wagtail.images.blocks import ImageChooserBlock
from wagtail.models import (Site, DraftStateMixin, LockableMixin, Orderable, Page, PreviewableMixin, RevisionMixin,
                            WorkflowMixin)
from wagtail.search import index

from sitios.models import LineaProducto, SitioWeb

SECCIONES = [("sectores", "Sectores"), ("comparar", "Comparador de planes"), ("clientes", "Logos de clientes"),
             ("testimonios", "Testimonios"), ("faq", "Preguntas frecuentes")]
RICH_BASICO = ["bold", "italic", "link", "ol", "ul"]


def site_de_pagina(page):
    """Sitio de Wagtail que contiene la página (sin pasar por get_site, que usa get_url_parts)."""
    path = getattr(page, "path", "") or ""
    if not path:
        return None
    prefijos = [path[:i] for i in range(Page.steplen, len(path) + 1, Page.steplen)]
    return Site.objects.filter(root_page__path__in=prefijos).select_related("sitio_web").order_by("-root_page__depth").first()


def sitio_de_pagina(page):
    site = site_de_pagina(page)
    return getattr(site, "sitio_web", None) if site else None


class FormPorSitio(WagtailAdminModelForm):
    """Formulario de los contenidos por sitio: solo ofrece los sitios y líneas del usuario, y lo verifica al guardar."""

    def __init__(self, *args, for_user=None, **kwargs):
        super().__init__(*args, for_user=for_user, **kwargs)
        self.usuario = for_user
        if for_user is None or for_user.is_superuser:
            return
        from sitios.permisos import accesos
        acc = accesos(for_user)
        if "sitio" in self.fields:
            self.fields["sitio"].queryset = self.fields["sitio"].queryset.filter(pk__in={s for s, _l, _n in acc})
        if "linea" in self.fields:
            self.fields["linea"].queryset = self.fields["linea"].queryset.filter(
                models.Q(sitio_id__in={s for s, l, _n in acc if l is None}) | models.Q(pk__in={l for _s, l, _n in acc if l}))

    def clean(self):
        datos = super().clean()
        u = self.usuario
        if u is not None and not u.is_superuser:
            from sitios.permisos import puede
            sitio = datos.get("sitio") or getattr(self.instance, "sitio", None)
            linea = datos.get("linea") if "linea" in self.fields else getattr(self.instance, "linea", None)
            if sitio is not None and not puede(u, sitio.pk, linea.pk if linea else None):
                raise forms.ValidationError("No tenés permiso para cargar contenido en ese sitio o línea.")
        return datos


# ---------------------------------------------------------------------------------------------- Páginas
class PaginaForm(WagtailAdminPageForm):
    """Secciones ocultas como casillas (se guardan como lista)."""
    secciones_ocultas_sel = forms.MultipleChoiceField(label="Secciones ocultas", required=False, choices=SECCIONES,
                                                      widget=forms.CheckboxSelectMultiple,
                                                      help_text="Las secciones marcadas no se muestran en esta página (solo las que la página tiene).")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "secciones_ocultas_sel" in self.fields:
            self.fields["secciones_ocultas_sel"].initial = self.instance.secciones_ocultas or []

    def save(self, commit=True):
        self.instance.secciones_ocultas = self.cleaned_data.get("secciones_ocultas_sel") or []
        return super().save(commit)


class SeoMixin(models.Model):
    """Campos de SEO comunes a páginas y artículos (pestaña «SEO»)."""
    ruta_publica = models.CharField("Ruta en la web", max_length=200, blank=True,
                                    help_text="Dirección en el sitio público, sin dominio. Vacío = inicio. Ej.: lite/ o cereales/blog/")
    canonical = models.URLField("URL canónica", blank=True, help_text="Solo si debe apuntar a otra URL. Vacío: la propia página.")
    indexar = models.BooleanField("Indexar en buscadores", default=True)
    imagen_og = models.ForeignKey("wagtailimages.Image", verbose_name="Imagen para redes (Open Graph)", null=True, blank=True,
                                  on_delete=models.SET_NULL, related_name="+")

    seo_panels = [
        MultiFieldPanel([FieldPanel("seo_title"), FieldPanel("search_description")], "Resultado en buscadores",
                        help_text="Título: hasta 60 caracteres. Descripción: hasta 160. No se completan solos: si quedan vacíos, la web usa los textos actuales."),
        FieldPanel("ruta_publica"), FieldRowPanel([FieldPanel("indexar"), FieldPanel("canonical")]), FieldPanel("imagen_og"),
    ]

    class Meta:
        abstract = True

    def get_url_parts(self, request=None):
        """La URL de la página es la de la web pública (también en los enlaces internos de los textos)."""
        site = site_de_pagina(self)
        sw = getattr(site, "sitio_web", None) if site else None
        if site is None:
            return None
        root = sw.dominio_publico if sw else ""
        return (site.id, root or "", "/" + (self.ruta_publica or ""))

    def serve_preview(self, request, mode_name):
        from publicacion.servicio import vista_previa_objeto
        return vista_previa_objeto(request, self, mode_name)


class PaginaWeb(SeoMixin, Page):
    """Página del sitio: inicio, landing de plan, línea de GEAGRO o página institucional."""
    linea = models.ForeignKey(LineaProducto, verbose_name="Línea de producto", null=True, blank=True, on_delete=models.SET_NULL,
                              help_text="Solo GEAGRO: Cereales o Vid.")
    hero_titulo = models.TextField("Título principal", blank=True,
                                   help_text="Un renglón por línea. Encerrá entre **asteriscos dobles** el texto que va resaltado.")
    hero_bajada = models.TextField("Texto debajo del título", blank=True)
    boton1_texto = models.CharField("Botón principal: texto", max_length=60, blank=True)
    boton1_enlace = models.CharField("Botón principal: enlace", max_length=200, blank=True, help_text="#demo, #planes o una URL")
    boton2_texto = models.CharField("Botón secundario: texto", max_length=60, blank=True)
    boton2_enlace = models.CharField("Botón secundario: enlace", max_length=200, blank=True)
    secciones_ocultas = models.JSONField(default=list, blank=True)
    notas = models.TextField("Notas internas", blank=True, help_text="No se publican.")

    base_form_class = PaginaForm
    content_panels = Page.content_panels + [
        HelpPanel("<p>Los campos vacíos mantienen el texto actual de la web. El diseño, los colores y la estructura no cambian.</p>"),
        MultiFieldPanel([FieldPanel("hero_titulo"), FieldPanel("hero_bajada"),
                         FieldRowPanel([FieldPanel("boton1_texto"), FieldPanel("boton1_enlace")]),
                         FieldRowPanel([FieldPanel("boton2_texto"), FieldPanel("boton2_enlace")])], "Encabezado (hero)"),
        FieldPanel("secciones_ocultas_sel"),
        FieldPanel("linea"), FieldPanel("notas"),
    ]
    promote_panels = []
    edit_handler = TabbedInterface([ObjectList(content_panels, heading="Contenido"),
                                    ObjectList(SeoMixin.seo_panels + [FieldPanel("slug")], heading="SEO")])
    search_fields = Page.search_fields + [index.SearchField("hero_titulo"), index.SearchField("hero_bajada")]
    parent_page_types = ["wagtailcore.Page", "contenidos.PaginaWeb"]
    preview_modes = [("", "Página")]

    class Meta:
        verbose_name = "página"
        verbose_name_plural = "páginas"


class BlogIndexPage(SeoMixin, Page):
    linea = models.ForeignKey(LineaProducto, verbose_name="Línea de producto", null=True, blank=True, on_delete=models.SET_NULL)
    intro = models.TextField("Introducción", blank=True)
    reune_lineas = models.BooleanField("Reunir artículos de las líneas", default=False,
                                       help_text="GEAGRO /blog/: muestra también los artículos de Cereales y Vid, enlazados a su dirección original.")
    articulos_por_pagina = models.PositiveSmallIntegerField(default=12)

    content_panels = Page.content_panels + [FieldPanel("intro"), FieldRowPanel([FieldPanel("linea"), FieldPanel("reune_lineas")]),
                                            FieldPanel("articulos_por_pagina")]
    promote_panels = []
    edit_handler = TabbedInterface([ObjectList(content_panels, heading="Contenido"),
                                    ObjectList(SeoMixin.seo_panels + [FieldPanel("slug")], heading="SEO")])
    subpage_types = ["contenidos.ArticuloPage"]
    preview_modes = [("", "Índice del blog")]

    class Meta:
        verbose_name = "blog"
        verbose_name_plural = "blogs"


class CategoriaBlog(models.Model):
    sitio = models.ForeignKey(SitioWeb, on_delete=models.CASCADE)
    linea = models.ForeignKey(LineaProducto, null=True, blank=True, on_delete=models.SET_NULL)
    nombre = models.CharField(max_length=60)
    slug = models.SlugField()
    actualizado = models.DateTimeField(auto_now=True)
    panels = [FieldPanel("sitio"), FieldPanel("linea"), FieldPanel("nombre"), FieldPanel("slug")]
    base_form_class = FormPorSitio

    class Meta:
        verbose_name = "categoría del blog"
        verbose_name_plural = "categorías del blog"
        ordering = ["sitio", "nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.linea or self.sitio})"


class ArticuloTag(TaggedItemBase):
    content_object = ParentalKey("contenidos.ArticuloPage", related_name="tagged_items", on_delete=models.CASCADE)


class ArticuloPage(SeoMixin, Page):
    resumen = models.TextField("Resumen", max_length=300)
    imagen = models.ForeignKey("wagtailimages.Image", verbose_name="Imagen destacada", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    autor = models.CharField("Autor", max_length=80, blank=True)
    fecha = models.DateField("Fecha de publicación")
    categorias = ParentalManyToManyField(CategoriaBlog, verbose_name="Categorías", blank=True)
    tags = ClusterTaggableManager("Etiquetas", through=ArticuloTag, blank=True)
    cuerpo = StreamField([
        ("titulo", blocks.StructBlock([("nivel", blocks.ChoiceBlock(choices=[("h2", "Título (H2)"), ("h3", "Subtítulo (H3)"), ("h4", "Subtítulo menor (H4)")], default="h2")),
                                        ("texto", blocks.CharBlock())], icon="title", label="Título")),
        ("parrafo", blocks.RichTextBlock(features=RICH_BASICO, label="Párrafo")),
        ("imagen", blocks.StructBlock([("imagen", ImageChooserBlock()), ("pie", blocks.CharBlock(required=False, label="Epígrafe")),
                                       ("alt", blocks.CharBlock(required=False, label="Texto alternativo", help_text="Vacío: se usa la descripción de la imagen."))],
                                      icon="image", label="Imagen")),
        ("cita", blocks.StructBlock([("texto", blocks.TextBlock()), ("autor", blocks.CharBlock(required=False))], icon="openquote", label="Cita")),
        ("destacado", blocks.RichTextBlock(features=RICH_BASICO, icon="pick", label="Bloque destacado")),
        ("tabla", TableBlock(label="Tabla", table_options={"contextMenu": ["row_above", "row_below", "col_left", "col_right", "remove_row", "remove_col"]})),
        ("boton", blocks.StructBlock([("texto", blocks.CharBlock()), ("enlace", blocks.CharBlock(help_text="#demo, /lite/ o una URL"))], icon="link", label="Botón (CTA)")),
        ("video", blocks.URLBlock(icon="media", label="Video de YouTube o Vimeo")),
    ], verbose_name="Contenido", use_json_field=True)
    relacionados = ParentalManyToManyField("self", verbose_name="Artículos relacionados", blank=True, symmetrical=False)
    copia_de = models.ForeignKey("self", verbose_name="Adaptado de", null=True, blank=True, on_delete=models.SET_NULL, related_name="copias",
                                 help_text="Si es una copia adaptada de un artículo de otro sitio. Reescribí el texto: no publiques textos idénticos en dos dominios.")

    content_panels = Page.content_panels + [
        FieldPanel("resumen"), FieldRowPanel([FieldPanel("fecha"), FieldPanel("autor")]), FieldPanel("imagen"), FieldPanel("cuerpo"),
        MultiFieldPanel([FieldPanel("categorias", widget=forms.CheckboxSelectMultiple), FieldPanel("tags"), FieldPanel("relacionados"), FieldPanel("copia_de")], "Organización"),
    ]
    promote_panels = []
    edit_handler = TabbedInterface([ObjectList(content_panels, heading="Contenido"),
                                    ObjectList(SeoMixin.seo_panels[:1] + [FieldPanel("slug"), FieldRowPanel([FieldPanel("indexar"), FieldPanel("canonical")]), FieldPanel("imagen_og")], heading="SEO")])
    parent_page_types = ["contenidos.BlogIndexPage"]
    search_fields = Page.search_fields + [index.SearchField("resumen"), index.SearchField("cuerpo")]
    preview_modes = [("", "Artículo")]

    class Meta:
        verbose_name = "artículo"
        verbose_name_plural = "artículos"

    @property
    def ruta(self):
        padre = self.get_parent().specific
        return f"{padre.ruta_publica}{self.slug}/"

    def get_url_parts(self, request=None):
        site = site_de_pagina(self)
        if site is None:
            return None
        sw = getattr(site, "sitio_web", None)
        return (site.id, sw.dominio_publico if sw else "", "/" + self.ruta)

    def save(self, *args, **kwargs):
        self.ruta_publica = self.ruta if self.get_parent() else self.ruta_publica
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------------------------- Oferta comercial
class ContenidoSitio(models.Model):
    """Base de los contenidos que pertenecen a un sitio (y opcionalmente a una línea)."""
    sitio = models.ForeignKey(SitioWeb, verbose_name="Sitio", on_delete=models.CASCADE)
    linea = models.ForeignKey(LineaProducto, verbose_name="Línea", null=True, blank=True, on_delete=models.SET_NULL,
                              help_text="Solo GEAGRO. Vacío: todo el sitio.")
    actualizado = models.DateTimeField(auto_now=True)
    base_form_class = FormPorSitio

    class Meta:
        abstract = True


MONEDAS = [("ARS", "Pesos argentinos ($)"), ("USD", "Dólares estadounidenses (US$)")]
SIMBOLO = {"ARS": "$", "USD": "US$"}
IMPORTE = r"^\d{1,3}(\.\d{3})*(,\d{1,2})?$"


def validar_importe(valor):
    import re
    if valor and not re.match(IMPORTE, valor.strip()):
        raise forms.ValidationError("Escribí el importe con punto de miles y sin símbolo, por ejemplo 178.500")


class Plan(WorkflowMixin, DraftStateMixin, LockableMixin, RevisionMixin, PreviewableMixin, ContenidoSitio):
    clave = models.SlugField("Clave", help_text="lite, core, plus… No se cambia: identifica el plan en las plantillas.")
    nombre = models.CharField("Nombre", max_length=60)
    etiqueta = models.CharField("Nombre completo", max_length=80, blank=True, help_text="Ej.: GERP Lite")
    moneda = models.CharField("Moneda", max_length=3, choices=MONEDAS, default="ARS")
    mas_iva = models.BooleanField("Los importes son más IVA", default=True, help_text="Muestra «+ IVA» junto a cada importe.")
    precio = models.CharField("Abono mensual", max_length=20, validators=[validar_importe],
                              help_text="Sin símbolo, con punto de miles: 178.500")
    implementacion = models.CharField("Implementación (pago único)", max_length=20, blank=True, validators=[validar_importe])
    leyenda_vigencia = models.CharField("Leyenda de vigencia", max_length=200, blank=True,
        help_text="Texto que se muestra debajo de los planes, con (*). Vacío: no se muestra ninguna leyenda.")
    vigente_hasta = models.DateField("Aviso de vencimiento", null=True, blank=True,
                                     help_text="Opcional. No se publica: te avisamos en el inicio del administrador cuando se acerque la fecha.")
    visible = models.BooleanField("Visible en la web", default=True)
    destacado = models.BooleanField("Destacado", default=False)
    orden = models.PositiveSmallIntegerField("Orden", default=0)
    publico_corto = models.CharField("Público (breve)", max_length=80, blank=True, help_text="Aparece en la cabecera de la tarjeta.")
    publico = models.TextField("Para quién es", blank=True)
    caracteristicas = models.TextField("Características de la tarjeta", blank=True, help_text="Una por renglón.")
    cta_texto = models.CharField("Texto del botón", max_length=40, blank=True, default="Solicitar demo")
    cta_enlace = models.CharField("Enlace del botón", max_length=200, blank=True, default="#demo")
    # Presentación de la landing (GERP)
    ruta = models.CharField("Ruta de la landing", max_length=60, blank=True, help_text="Ej.: lite/")
    titulo_landing = models.TextField("Título de la landing (H1)", blank=True, help_text="Un renglón por línea.")
    titulo_seo = models.CharField("Título SEO de la landing", max_length=100, blank=True, help_text="Ideal: hasta 60 caracteres.")
    descripcion_seo = models.CharField("Descripción SEO de la landing", max_length=220, blank=True, help_text="Ideal: entre 120 y 160 caracteres.")
    color = models.CharField("Color", max_length=7, blank=True)
    color_acento = models.CharField("Color de acento", max_length=7, blank=True)
    color_hover = models.CharField("Color al pasar el mouse", max_length=7, blank=True)
    color_suave = models.CharField("Fondo suave", max_length=7, blank=True)
    icono = models.CharField("Ícono (archivo)", max_length=200, blank=True, help_text="Ruta del ícono original en los recursos de la web.")
    logo_blanco = models.CharField("Logo blanco (archivo)", max_length=200, blank=True)
    modulos = StreamField([("modulo", blocks.StructBlock([("icono", blocks.CharBlock(help_text="Bootstrap Icon, ej.: bi-box-seam")),
                                                          ("titulo", blocks.CharBlock()), ("texto", blocks.TextBlock())], label="Módulo"))],
                          verbose_name="Módulos incluidos", blank=True, use_json_field=True)
    funciones = StreamField([("grupo", blocks.StructBlock([
        ("icono", blocks.CharBlock()), ("titulo", blocks.CharBlock()),
        ("items", blocks.ListBlock(blocks.StructBlock([("titulo", blocks.CharBlock()), ("texto", blocks.CharBlock(required=False))]), label="Funcionalidades"))],
        label="Grupo de funcionalidades"))], verbose_name="Funcionalidades de la landing", blank=True, use_json_field=True)
    nota_funciones = models.CharField("Nota debajo de las funcionalidades", max_length=200, blank=True)

    panels_precio = [
        HelpPanel("<p>Cambiá el precio, guardá el borrador y mirá la vista previa. Al aprobarlo queda listo para «Publicar en la web». "
                  "Para actualizar todos los planes juntos usá <b>Actualizar precios</b> en el menú.</p>"),
        FieldRowPanel([FieldPanel("sitio"), FieldPanel("linea")]),
        FieldRowPanel([FieldPanel("nombre"), FieldPanel("etiqueta"), FieldPanel("clave")]),
        MultiFieldPanel([FieldRowPanel([FieldPanel("precio"), FieldPanel("implementacion")]),
                         FieldRowPanel([FieldPanel("moneda"), FieldPanel("mas_iva")]),
                         FieldRowPanel([FieldPanel("leyenda_vigencia"), FieldPanel("vigente_hasta")])], "Precio (fuente única)"),
        FieldRowPanel([FieldPanel("visible"), FieldPanel("destacado"), FieldPanel("orden")]),
        FieldPanel("publico_corto"), FieldPanel("publico"), FieldPanel("caracteristicas"),
        FieldRowPanel([FieldPanel("cta_texto"), FieldPanel("cta_enlace")]),
    ]
    panels_landing = [
        HelpPanel("<p>Solo para los sitios con una landing por plan (GERP).</p>"),
        FieldPanel("ruta"), FieldPanel("titulo_landing"), FieldPanel("titulo_seo"), FieldPanel("descripcion_seo"),
        FieldPanel("modulos"), FieldPanel("funciones"), FieldPanel("nota_funciones"),
    ]
    panels_identidad = [FieldRowPanel([FieldPanel("color"), FieldPanel("color_acento")]), FieldRowPanel([FieldPanel("color_hover"), FieldPanel("color_suave")]),
                        FieldPanel("icono"), FieldPanel("logo_blanco")]
    edit_handler = TabbedInterface([ObjectList(panels_precio, heading="Precio y presentación"), ObjectList(panels_landing, heading="Landing"),
                                    ObjectList(panels_identidad, heading="Identidad")])
    preview_modes = [("inicio", "Inicio del sitio"), ("landing", "Landing del plan")]

    class Meta:
        ordering = ["sitio__orden", "orden"]
        verbose_name = "plan"
        verbose_name_plural = "planes y precios"

    def __str__(self):
        return self.etiqueta or f"{self.sitio.nombre} {self.nombre}"

    @property
    def precio_num(self):
        try:
            return int(self.precio.replace(".", "").replace(",", "").strip() or 0)
        except ValueError:
            return 0

    # Uso interno (no se exporta a las webs): quién y cuándo modificó el plan por última vez
    @property
    def ultima_modificacion(self):
        return self.latest_revision.created_at if self.latest_revision_id else None

    @property
    def modificado_por(self):
        r = self.latest_revision
        if r is None:
            return "—"
        return (r.user.get_full_name() or r.user.get_username()) if r.user else "Carga inicial"

    @property
    def simbolo(self):
        return SIMBOLO.get(self.moneda, "$")

    def importe(self, valor):
        """Importe completo como se lee en la web: $89.250 + IVA"""
        return f"{self.simbolo}{valor}{' + IVA' if self.mas_iva else ''}" if valor else ""

    def serve_preview(self, request, mode_name):
        from publicacion.servicio import vista_previa_objeto
        return vista_previa_objeto(request, self, mode_name)


ESTADOS_VALOR = [("incluido", "Incluido ✓"), ("no_incluido", "No incluido —"), ("opcional", "Opcional"),
                 ("a_confirmar", "A confirmar"), ("texto", "Texto")]


class Funcionalidad(RevisionMixin, ClusterableModel):
    sitio = models.ForeignKey(SitioWeb, verbose_name="Sitio", on_delete=models.CASCADE)
    linea = models.ForeignKey(LineaProducto, verbose_name="Línea", null=True, blank=True, on_delete=models.SET_NULL)
    etiqueta = models.CharField("Funcionalidad", max_length=120)
    grupo = models.CharField("Grupo", max_length=10, choices=[("basic", "Básica"), ("advanced", "Avanzada")], default="basic")
    resumen = models.BooleanField("Mostrar en el comparador resumido", default=True,
                                  help_text="Las que no están en el resumen aparecen con «Ver comparación completa».")
    orden = models.PositiveSmallIntegerField("Orden", default=0)
    actualizado = models.DateTimeField(auto_now=True)
    base_form_class = FormPorSitio

    panels = [FieldRowPanel([FieldPanel("sitio"), FieldPanel("linea")]), FieldPanel("etiqueta"),
              FieldRowPanel([FieldPanel("grupo"), FieldPanel("resumen"), FieldPanel("orden")]),
              InlinePanel("valores", heading="Qué incluye cada plan", label="Plan",
                          help_text="No asumas que un plan superior incluye todo lo del anterior: cargá cada valor con su fuente.")]

    class Meta:
        ordering = ["sitio", "grupo", "orden"]
        verbose_name = "funcionalidad"
        verbose_name_plural = "funcionalidades (comparador)"

    def __str__(self):
        return self.etiqueta


class ValorFuncionalidad(Orderable):
    funcionalidad = ParentalKey(Funcionalidad, related_name="valores", on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE)
    estado = models.CharField(max_length=20, choices=ESTADOS_VALOR, default="a_confirmar")
    texto = models.CharField("Texto (si el estado es «Texto»)", max_length=60, blank=True)
    fuente = models.CharField("Fuente", max_length=120, blank=True, help_text="De dónde sale el dato. Ej.: gerp.ar, octubre 2026")
    validado_por = models.CharField("Validado por", max_length=80, blank=True)

    panels = [FieldRowPanel([FieldPanel("plan"), FieldPanel("estado"), FieldPanel("texto")]),
              FieldRowPanel([FieldPanel("fuente"), FieldPanel("validado_por")])]


class PreguntaFrecuente(WorkflowMixin, DraftStateMixin, LockableMixin, RevisionMixin, PreviewableMixin, ContenidoSitio):
    pregunta = models.CharField("Pregunta", max_length=200)
    respuesta = RichTextField("Respuesta", features=RICH_BASICO, help_text=(
        "Para mencionar un precio no escribas el importe: usá [precio:clave] o [implementacion:clave] "
        "(por ejemplo [precio:lite]). Se reemplaza por el precio vigente del plan, con moneda e IVA."))
    ubicacion = models.CharField("Página", max_length=60, blank=True, help_text="Ruta de la página donde aparece. Vacío = inicio. Ej.: lite/ o cereales/")
    categoria = models.CharField("Categoría", max_length=60, blank=True)
    orden = models.PositiveSmallIntegerField("Orden", default=0)
    visible = models.BooleanField("Visible", default=True)

    panels = [FieldRowPanel([FieldPanel("sitio"), FieldPanel("linea")]), FieldPanel("pregunta"), FieldPanel("respuesta"),
              FieldRowPanel([FieldPanel("ubicacion"), FieldPanel("categoria"), FieldPanel("orden")]), FieldPanel("visible")]
    preview_modes = [("", "Página donde aparece")]

    class Meta:
        ordering = ["sitio", "ubicacion", "orden"]
        verbose_name = "pregunta frecuente"
        verbose_name_plural = "preguntas frecuentes"

    def __str__(self):
        return self.pregunta

    def clean(self):
        super().clean()
        import re
        from django.core.exceptions import ValidationError
        texto = texto_plano(self.respuesta) + " " + (self.pregunta or "")
        if re.search(r"(US)?\$\s?\d{1,3}(\.\d{3})+|\d+\s*d[oó]lares", texto):
            raise ValidationError({"respuesta": "No escribas importes en la pregunta: usá [precio:clave] o [implementacion:clave] "
                                                "para que el precio salga del plan y se actualice solo."})
        if self.sitio_id:
            claves = set(Plan.objects.filter(sitio_id=self.sitio_id).values_list("clave", flat=True))
            malas = [c for c in re.findall(r"\[(?:precio|implementacion|vigencia):([^\]]+)\]", texto) if c.strip().lower() not in claves]
            if malas:
                raise ValidationError({"respuesta": f"No hay un plan con la clave {', '.join(sorted(set(malas)))} en este sitio. "
                                                    f"Claves disponibles: {', '.join(sorted(claves)) or '(ninguna)'}."})

    def serve_preview(self, request, mode_name):
        from publicacion.servicio import vista_previa_objeto
        return vista_previa_objeto(request, self, mode_name)


class Testimonio(WorkflowMixin, DraftStateMixin, LockableMixin, RevisionMixin, ContenidoSitio):
    ESTADOS = [("pendiente", "Pendiente de autorización"), ("autorizado", "Autorizado"), ("rechazado", "No autorizado")]
    cliente = models.CharField("Autor", max_length=120, blank=True, help_text="Nombre y cargo de quien da el testimonio.")
    empresa = models.CharField("Empresa", max_length=80)
    logo = models.ForeignKey("wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    texto = models.TextField("Testimonio", blank=True, help_text="Texto exacto, tal como lo autorizó el cliente.")
    estado = models.CharField("Autorización", max_length=12, choices=ESTADOS, default="pendiente")
    autorizado_por = models.CharField("Autorizado por", max_length=80, blank=True)
    autorizado_el = models.DateField("Fecha de autorización", null=True, blank=True)
    visible = models.BooleanField("Visible", default=True)
    nota = models.CharField("Nota interna", max_length=200, blank=True)

    panels = [HelpPanel("<p>Solo se publican los testimonios <b>autorizados</b>, con texto, autor, quién autorizó y fecha. "
                        "Mientras estén pendientes no aparecen en la web.</p>"),
              FieldRowPanel([FieldPanel("sitio"), FieldPanel("linea")]), FieldRowPanel([FieldPanel("empresa"), FieldPanel("cliente")]),
              FieldPanel("texto"), FieldPanel("logo"), FieldRowPanel([FieldPanel("estado"), FieldPanel("autorizado_por"), FieldPanel("autorizado_el")]),
              FieldPanel("visible"), FieldPanel("nota")]

    class Meta:
        verbose_name = "testimonio"
        verbose_name_plural = "testimonios"

    def __str__(self):
        return self.empresa

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError
        if self.estado == "autorizado":
            faltan = [n for n, v in (("texto", self.texto.strip()), ("cliente", self.cliente.strip()), ("autorizado_por", self.autorizado_por.strip()),
                                     ("autorizado_el", self.autorizado_el)) if not v]
            if faltan:
                raise ValidationError({f: "Obligatorio para marcarlo como autorizado." for f in faltan})

    @property
    def publicable(self):
        return (self.estado == "autorizado" and bool(self.texto.strip()) and bool(self.cliente.strip())
                and bool(self.autorizado_por.strip()) and self.autorizado_el is not None and self.visible)


class Sector(ContenidoSitio):
    titulo = models.CharField("Sector", max_length=60)
    texto = models.CharField("Texto", max_length=200)
    icono = models.CharField("Ícono (archivo)", max_length=200)
    orden = models.PositiveSmallIntegerField(default=0)
    panels = [FieldPanel("sitio"), FieldPanel("titulo"), FieldPanel("texto"), FieldPanel("icono"), FieldPanel("orden")]

    class Meta:
        ordering = ["sitio", "orden"]
        verbose_name = "sector"
        verbose_name_plural = "sectores"

    def __str__(self):
        return self.titulo


class Redireccion(ContenidoSitio):
    origen = models.CharField("Dirección anterior", max_length=200, help_text="Sin dominio. Ej.: index.php/gerp-lite-odoo/")
    destino = models.CharField("Destino", max_length=200, help_text="Ruta nueva (lite/) o ancla de la home (#planes)")
    panels = [FieldPanel("sitio"), FieldRowPanel([FieldPanel("origen"), FieldPanel("destino")])]

    class Meta:
        verbose_name = "redirección 301"
        verbose_name_plural = "redirecciones 301"

    def __str__(self):
        return f"/{self.origen} → {self.destino}"


class Recurso(ContenidoSitio):
    TIPOS = [("brochure", "Brochure"), ("logo", "Logos"), ("manual", "Manual de marca"), ("otro", "Otro")]
    titulo = models.CharField("Título", max_length=120)
    tipo = models.CharField(max_length=20, choices=TIPOS, default="brochure")
    documento = models.ForeignKey("wagtaildocs.Document", on_delete=models.PROTECT, related_name="+")
    visible = models.BooleanField(default=True)
    panels = [FieldRowPanel([FieldPanel("sitio"), FieldPanel("linea")]), FieldPanel("titulo"), FieldPanel("tipo"), FieldPanel("documento"), FieldPanel("visible")]

    class Meta:
        verbose_name = "recurso descargable"
        verbose_name_plural = "recursos descargables"

    def __str__(self):
        return self.titulo


def texto_plano(html):
    return strip_tags(html or "").strip()
