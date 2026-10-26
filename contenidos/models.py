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
from wagtail.admin.panels import (FieldPanel, FieldRowPanel, HelpPanel, InlinePanel, MultiFieldPanel, ObjectList, TitleFieldPanel,
                                  TabbedInterface)
from wagtail.contrib.table_block.blocks import TableBlock
from wagtail.fields import RichTextField, StreamField
from wagtail.images.blocks import ImageChooserBlock
from wagtail.models import (Site, DraftStateMixin, LockableMixin, Orderable, Page, PreviewableMixin, RevisionMixin,
                            WorkflowMixin)
from wagtail.search import index

from sitios.models import LineaProducto, SitioWeb

from .iconos_funcionalidad import ICONOS as ICONOS_FUNCIONALIDAD

SECCIONES = [("sectores", "Sectores"), ("comparar", "Comparador de planes"), ("clientes", "Logos de clientes"),
             ("testimonios", "Testimonios"), ("faq", "Preguntas frecuentes")]
RICH_BASICO = ["bold", "italic", "link", "ol", "ul"]
RICH_ARTICULO = ["h2", "h3", "bold", "italic", "link", "ol", "ul", "blockquote"]


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
        if "encabezado" in self.fields:  # la apariencia del encabezado solo existe en la web institucional de GENEOS
            ref = self.instance if getattr(self.instance, "path", "") else getattr(self, "parent_page", None)
            sw = sitio_de_pagina(ref) if ref is not None else None
            if sw is not None and sw.clave != "geneos":
                del self.fields["encabezado"]

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
    encabezado = models.CharField("Apariencia predeterminada de esta página", max_length=10, blank=True, default="",
                                  choices=[("", "Heredar configuración global"), ("claro", "Claro (blanco)"), ("oscuro", "Oscuro (negro)")],
                                  help_text="Solo en la web institucional de GENEOS. «Heredar» usa la apariencia predeterminada de Sitios y contacto. La elección del visitante tiene prioridad.")
    notas = models.TextField("Notas internas", blank=True, help_text="No se publican.")

    base_form_class = PaginaForm
    content_panels = Page.content_panels + [
        HelpPanel("<p>Los campos vacíos mantienen el texto actual de la web. El diseño, los colores y la estructura no cambian.</p>"),
        MultiFieldPanel([FieldPanel("hero_titulo"), FieldPanel("hero_bajada"),
                         FieldRowPanel([FieldPanel("boton1_texto"), FieldPanel("boton1_enlace")]),
                         FieldRowPanel([FieldPanel("boton2_texto"), FieldPanel("boton2_enlace")])], "Encabezado (hero)"),
        FieldPanel("secciones_ocultas_sel"),
        MultiFieldPanel([FieldPanel("encabezado")], "Apariencia"),
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
                                       help_text="Sin uso desde el blog universal: el blog general siempre reúne los artículos del sitio.")
    articulos_por_pagina = models.PositiveSmallIntegerField(default=12)

    content_panels = Page.content_panels + [
        HelpPanel("<p>El nombre, la dirección, el menú y las opciones del blog se configuran en <b>Contenidos → Blog y noticias</b>. "
                  "Los artículos se crean siempre en el blog general del sitio; en GEAGRO, la línea se marca en cada artículo.</p>"),
        FieldPanel("intro"), FieldPanel("linea", read_only=True)]
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


class AutorBlog(models.Model):
    """Firma de los artículos de un sitio. Opcional: un artículo sin autor se firma como el producto."""
    sitio = models.ForeignKey(SitioWeb, verbose_name="Sitio", on_delete=models.CASCADE)
    nombre = models.CharField("Nombre", max_length=80)
    cargo = models.CharField("Rol o cargo", max_length=80, blank=True)
    bio = models.TextField("Presentación breve", blank=True, max_length=400)
    foto = models.ForeignKey("wagtailimages.Image", verbose_name="Foto", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    activo = models.BooleanField("Disponible para nuevos artículos", default=True)
    actualizado = models.DateTimeField(auto_now=True)
    panels = [FieldPanel("sitio"), FieldRowPanel([FieldPanel("nombre"), FieldPanel("cargo")]), FieldPanel("bio"), FieldPanel("foto"), FieldPanel("activo")]
    base_form_class = FormPorSitio

    class Meta:
        verbose_name = "autor"
        verbose_name_plural = "autores"
        ordering = ["sitio", "nombre"]

    def __str__(self):
        return self.nombre

    @property
    def iniciales(self):
        partes = self.nombre.split()
        return ((partes[0][0] + partes[-1][0]) if len(partes) > 1 else self.nombre[:2]).upper()


class ArticuloTag(TaggedItemBase):
    content_object = ParentalKey("contenidos.ArticuloPage", related_name="tagged_items", on_delete=models.CASCADE)


class ArticuloForm(WagtailAdminPageForm):
    """Editor del artículo: ofrece solo las líneas, categorías, autores y relacionados del sitio del blog.
    Un artículo nuevo puede llegar con la línea elegida en «Blog y noticias» (editorial.vistas)."""

    def __init__(self, *args, parent_page=None, **kwargs):
        super().__init__(*args, parent_page=parent_page, **kwargs)
        page = self.instance if self.instance.pk else parent_page
        sitio = sitio_de_pagina(page) if page is not None else None
        if sitio is None:
            return
        lineas = LineaProducto.objects.filter(sitio=sitio)
        if "lineas" in self.fields:
            if lineas.exists():
                self.fields["lineas"].queryset = lineas
                if not self.instance.pk and not self.is_bound:
                    from editorial.contexto import linea_inicial
                    lid = linea_inicial()
                    if lid and lineas.filter(pk=lid).exists():
                        self.initial["lineas"] = [lid]
            else:
                del self.fields["lineas"]
        if "categorias" in self.fields:
            self.fields["categorias"].queryset = CategoriaBlog.objects.filter(sitio=sitio)
        if "autor" in self.fields:
            self.fields["autor"].queryset = AutorBlog.objects.filter(sitio=sitio)
        if "relacionados" in self.fields and sitio.site:
            qs = ArticuloPage.objects.descendant_of(sitio.site.root_page)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            self.fields["relacionados"].queryset = qs


class VolverAlBlogPanel(HelpPanel):
    """Arriba del editor: vuelta a «Blog y noticias» del sitio y cómo agregar contenido."""

    class BoundPanel(HelpPanel.BoundPanel):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            from django.urls import reverse
            from django.utils.html import format_html
            page = self.instance if self.instance.pk else None
            sitio = sitio_de_pagina(page) if page else None
            if sitio is None:
                parent = getattr(self.form, "parent_page", None)
                sitio = sitio_de_pagina(parent) if parent is not None else None
            url = reverse("blog:index") + (f"?sitio={sitio.clave}" if sitio else "")
            self.content = format_html(
                '<p class="gwa-volver-blog"><a href="{}">← Volver al Blog de {}</a></p>'
                '<p class="gwa-ayuda-bloques">Escribí en los bloques «Texto» (admiten subtítulos, listas, enlaces y citas) y tocá <b>+</b> '
                'para sumar imágenes, citas destacadas, tablas, videos o botones. Usá la vista previa (ícono del ojo) para ver cómo queda en la web.</p>',
                url, sitio.nombre if sitio else "")


class EstadoArticuloPanel(HelpPanel):
    """Pestaña «Publicación»: estado editorial y si el artículo está efectivamente en la web."""

    class BoundPanel(HelpPanel.BoundPanel):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            from editorial.estado import estado_articulo_html
            self.content = estado_articulo_html(self.instance)


ORIGENES = [("", "Escrito desde cero"), ("noticia", "Desde una noticia"), ("evento", "Desde un evento"),
            ("tendencia", "Desde una tendencia de búsqueda"), ("idea", "Desde una idea editorial"), ("ia", "Con ayuda de IA")]


class ArticuloPage(SeoMixin, Page):
    resumen = models.TextField("Resumen o bajada", max_length=300)
    imagen = models.ForeignKey("wagtailimages.Image", verbose_name="Imagen destacada", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    autor = models.ForeignKey(AutorBlog, verbose_name="Autor", null=True, blank=True, on_delete=models.SET_NULL, related_name="articulos",
                              help_text="Opcional. Se cargan en Contenidos → Autores.")
    fecha = models.DateField("Fecha de publicación")
    lineas = ParentalManyToManyField(LineaProducto, verbose_name="Líneas de producto", blank=True,
                                     help_text="Solo GEAGRO. El artículo tiene una sola dirección (/blog/…) y aparece también en el listado de cada línea marcada.")
    origen = models.CharField("Origen", max_length=12, choices=ORIGENES, blank=True, default="")
    fuentes = models.TextField("Fuentes consultadas", blank=True,
                               help_text="Uso interno: de dónde salen los datos del artículo. No se publica.")
    palabras_clave = models.CharField("Palabras clave sugeridas", max_length=250, blank=True, help_text="Uso interno, separadas por coma. No se publican.")
    categorias = ParentalManyToManyField(CategoriaBlog, verbose_name="Categorías", blank=True)
    tags = ClusterTaggableManager("Etiquetas", through=ArticuloTag, blank=True)
    cuerpo = StreamField([
        # Bloques en el orden en que se ofrecen al tocar «+». «Texto» es el bloque principal (como en WordPress):
        # admite subtítulos, negrita, cursiva, enlaces, listas y citas sin cambiar de bloque.
        ("parrafo", blocks.RichTextBlock(features=RICH_ARTICULO, label="Texto", icon="pilcrow")),
        ("h2", blocks.CharBlock(label="Subtítulo", icon="h2", form_classname="gwa-bloque-h2")),
        ("h3", blocks.CharBlock(label="Subtítulo menor", icon="h3", form_classname="gwa-bloque-h3")),
        ("imagen", blocks.StructBlock([("imagen", ImageChooserBlock(label="Imagen", help_text="Elegí una de la biblioteca o subí una nueva desde la ventana.")),
                                       ("pie", blocks.CharBlock(required=False, label="Epígrafe")),
                                       ("alt", blocks.CharBlock(required=False, label="Texto alternativo", help_text="Qué muestra la imagen. Vacío: se usa la descripción de la imagen."))],
                                      icon="image", label="Imagen")),
        ("cita", blocks.StructBlock([("texto", blocks.TextBlock(label="Cita")), ("autor", blocks.CharBlock(required=False, label="Autor de la cita"))], icon="openquote", label="Cita destacada")),
        ("destacado", blocks.RichTextBlock(features=RICH_BASICO, icon="pick", label="Recuadro destacado")),
        ("tabla", TableBlock(label="Tabla", table_options={"contextMenu": ["row_above", "row_below", "col_left", "col_right", "remove_row", "remove_col"]})),
        ("video", blocks.URLBlock(icon="media", label="Video", help_text="Enlace de YouTube o Vimeo.")),
        ("boton", blocks.StructBlock([("texto", blocks.CharBlock(label="Texto del botón")), ("enlace", blocks.CharBlock(label="Enlace", help_text="#demo, /lite/ o una URL"))], icon="link", label="Botón")),
    ], verbose_name="Contenido", use_json_field=True)
    relacionados = ParentalManyToManyField("self", verbose_name="Artículos relacionados", blank=True, symmetrical=False)
    copia_de = models.ForeignKey("self", verbose_name="Adaptado de", null=True, blank=True, on_delete=models.SET_NULL, related_name="copias",
                                 help_text="Si es una copia adaptada de un artículo de otro sitio. Reescribí el texto: no publiques textos idénticos en dos dominios.")

    content_panels = [
        VolverAlBlogPanel(),
        TitleFieldPanel("title", heading="Título", placeholder="Título del artículo", help_text="Claro y concreto: es lo primero que se ve en la portada y en Google."),
        FieldPanel("resumen", heading="Bajada", help_text="Dos o tres líneas que cuentan de qué trata. También se usa en las tarjetas y en Google."),
        FieldPanel("imagen", heading="Imagen destacada", help_text="Horizontal, idealmente 1600×900 o más. Se recorta sola para la portada y las redes."),
        FieldRowPanel([FieldPanel("autor"), FieldPanel("fecha")]),
        FieldPanel("cuerpo", heading="Contenido"),
    ]
    organizacion_panels = [
        FieldPanel("lineas", widget=forms.CheckboxSelectMultiple), FieldPanel("categorias", widget=forms.CheckboxSelectMultiple),
        FieldPanel("tags", help_text="Palabras sueltas, separadas por coma."),
        FieldPanel("relacionados", widget=forms.CheckboxSelectMultiple, help_text="Opcional. Si no elegís ninguno, se muestran los de la misma categoría o línea."),
        MultiFieldPanel([FieldPanel("origen"), FieldPanel("fuentes"), FieldPanel("palabras_clave"), FieldPanel("copia_de")],
                        "Origen y fuentes (uso interno)", classname="collapsed"),
    ]
    seo_panels_articulo = [
        MultiFieldPanel([FieldPanel("seo_title", heading="Título para Google", help_text="Hasta 60 caracteres. Vacío: se usa el título del artículo."),
                         FieldPanel("search_description", heading="Descripción para Google", help_text="Hasta 160 caracteres. Vacío: se usa la bajada.")],
                        "Resultado en buscadores"),
        HelpPanel(template="editorial/panel_google.html", heading="Así podría verse en Google"),
        FieldPanel("slug", heading="Dirección (URL)", help_text="Se completa sola con el título. Cambiarla en un artículo publicado deja una redirección 301."),
        FieldPanel("imagen_og", help_text="Vacío: se usa la imagen destacada."),
        MultiFieldPanel([FieldRowPanel([FieldPanel("indexar"), FieldPanel("canonical")])], "Opciones avanzadas", classname="collapsed"),
    ]
    publicacion_panels = [EstadoArticuloPanel(heading="Estado")]
    promote_panels = []
    edit_handler = TabbedInterface([ObjectList(content_panels, heading="Artículo"), ObjectList(organizacion_panels, heading="Organización"),
                                    ObjectList(seo_panels_articulo, heading="SEO"), ObjectList(publicacion_panels, heading="Publicación")])
    base_form_class = ArticuloForm
    parent_page_types = ["contenidos.BlogIndexPage"]
    search_fields = Page.search_fields + [index.SearchField("resumen"), index.SearchField("cuerpo")]
    preview_modes = [("", "Artículo")]

    class Meta:
        verbose_name = "artículo"
        verbose_name_plural = "artículos"

    @classmethod
    def can_create_at(cls, parent):
        """Una sola dirección por artículo: se crean en el blog general del sitio, nunca dentro de un listado de línea."""
        return super().can_create_at(parent) and getattr(parent.specific, "linea_id", None) is None

    @property
    def ruta(self):
        """/blog/<slug>/ (o la ruta elegida en la configuración del blog del sitio)."""
        from editorial.models import ruta_blog
        padre = self.get_parent().specific
        sitio = sitio_de_pagina(padre)
        base = ruta_blog(sitio) if sitio else padre.ruta_publica
        return f"{base}{self.slug}/"

    def get_url_parts(self, request=None):
        site = site_de_pagina(self)
        if site is None:
            return None
        sw = getattr(site, "sitio_web", None)
        return (site.id, sw.dominio_publico if sw else "", "/" + self.ruta)

    def save(self, *args, **kwargs):
        anterior = self.ruta_publica
        self.ruta_publica = self.ruta if self.get_parent() else self.ruta_publica
        if (self.pk and anterior and anterior != self.ruta_publica
                and ArticuloPage.objects.filter(pk=self.pk, live=True).exists()):
            # El artículo ya estaba aprobado con otra dirección: la anterior redirige a la nueva (301)
            sitio = sitio_de_pagina(self)
            if sitio is not None:
                Redireccion.objects.filter(sitio=sitio, origen=self.ruta_publica).delete()  # volver a una dirección anterior
                Redireccion.objects.update_or_create(sitio=sitio, origen=anterior, defaults={"destino": self.ruta_publica})
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
    vigente_hasta = models.DateField("Vigencia hasta", null=True, blank=True,
                                     help_text="Fecha hasta la que valen los precios. No se publica: el inicio del administrador avisa cuando se acerca.")
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
    icono = models.CharField("Ícono (ruta actual)", max_length=200, blank=True, help_text="Ruta del ícono en los recursos de la web. Si elegís una imagen, se usa la imagen.")
    logo_blanco = models.CharField("Logo blanco (ruta actual)", max_length=200, blank=True)
    icono_img = models.ForeignKey("wagtailimages.Image", verbose_name="Ícono del plan", null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+", help_text="SVG recomendado. Reemplaza a la ruta actual.")
    logo_blanco_img = models.ForeignKey("wagtailimages.Image", verbose_name="Logo blanco del plan", null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name="+", help_text="Para la portada de la landing. SVG recomendado.")
    modulos = StreamField([("modulo", blocks.StructBlock([("icono", blocks.CharBlock(help_text="Bootstrap Icon, ej.: bi-box-seam")),
                                                          ("titulo", blocks.CharBlock()), ("texto", blocks.TextBlock())], label="Módulo"))],
                          verbose_name="Módulos incluidos", blank=True, use_json_field=True)
    funciones = StreamField([("grupo", blocks.StructBlock([
        ("icono", blocks.CharBlock()), ("titulo", blocks.CharBlock()),
        ("items", blocks.ListBlock(blocks.StructBlock([("titulo", blocks.CharBlock()), ("texto", blocks.CharBlock(required=False))]), label="Funcionalidades"))],
        label="Grupo de funcionalidades"))], verbose_name="Funcionalidades de la landing", blank=True, use_json_field=True)
    nota_funciones = models.CharField("Nota debajo de las funcionalidades", max_length=200, blank=True)

    # Pestañas de la edición completa (la edición rápida de todos los planes es «Oferta comercial → Planes y precios»)
    panels_precio = [
        HelpPanel("<p>Cambiá el precio, guardá el borrador y mirá la vista previa. Al aprobarlo queda listo para «Publicar en la web». "
                  "Para editar todos los planes juntos usá <b>Oferta comercial → Planes y precios</b>.</p>"),
        MultiFieldPanel([FieldRowPanel([FieldPanel("precio"), FieldPanel("implementacion")]),
                         FieldRowPanel([FieldPanel("moneda"), FieldPanel("mas_iva")])], "Precios (fuente única)"),
        MultiFieldPanel([FieldPanel("vigente_hasta"), FieldPanel("leyenda_vigencia")], "Vigencia"),
    ]
    panels_presentacion = [
        FieldRowPanel([FieldPanel("nombre"), FieldPanel("etiqueta")]),
        FieldPanel("publico_corto"), FieldPanel("publico"), FieldPanel("caracteristicas"),
        FieldRowPanel([FieldPanel("cta_texto"), FieldPanel("cta_enlace")]),
        FieldPanel("destacado"),
    ]
    panels_landing = [
        HelpPanel("<p>Solo para los sitios con una landing por plan (GERP).</p>"),
        FieldPanel("ruta"), FieldPanel("titulo_landing"), FieldPanel("titulo_seo"), FieldPanel("descripcion_seo"),
        FieldPanel("modulos"), FieldPanel("funciones"), FieldPanel("nota_funciones"),
    ]
    panels_identidad = [
        MultiFieldPanel([FieldRowPanel([FieldPanel("sitio"), FieldPanel("linea")]), FieldRowPanel([FieldPanel("clave"), FieldPanel("orden")]),
                         FieldPanel("visible")], "Configuración"),
        MultiFieldPanel([FieldRowPanel([FieldPanel("color"), FieldPanel("color_acento")]), FieldRowPanel([FieldPanel("color_hover"), FieldPanel("color_suave")]),
                         FieldRowPanel([FieldPanel("icono_img"), FieldPanel("logo_blanco_img")])], "Identidad visual"),
        MultiFieldPanel([FieldPanel("icono"), FieldPanel("logo_blanco")], "Rutas actuales (se usan si no elegís una imagen)", classname="collapsed"),
    ]
    edit_handler = TabbedInterface([ObjectList(panels_precio, heading="Precio y vigencia"), ObjectList(panels_presentacion, heading="Presentación"),
                                    ObjectList(panels_landing, heading="Landing"), ObjectList(panels_identidad, heading="Identidad y configuración")])
    preview_modes = [("inicio", "Inicio del sitio"), ("landing", "Landing del plan")]

    class Meta:
        ordering = ["sitio__orden", "orden"]
        verbose_name = "plan"
        verbose_name_plural = "planes y precios"

    def __str__(self):
        return self.etiqueta or f"{self.sitio.nombre} {self.nombre}"

    def clean(self):
        super().clean()
        validar_logo(self.icono_img, "icono_img", minimo=64)
        validar_logo(self.logo_blanco_img, "logo_blanco_img")

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


class Funcionalidad(WorkflowMixin, DraftStateMixin, LockableMixin, RevisionMixin, PreviewableMixin, ClusterableModel):
    """Característica comercial de un producto y su disponibilidad en cada plan (comparador de la web).
    Se edita en «Oferta comercial → Funcionalidades» o en su edición completa, con borrador, aprobación e historial."""
    sitio = models.ForeignKey(SitioWeb, verbose_name="Producto", on_delete=models.CASCADE)
    linea = models.ForeignKey(LineaProducto, verbose_name="Línea", null=True, blank=True, on_delete=models.SET_NULL,
                              help_text="Solo GEAGRO: Cereales o Vid. Vacío: todas las líneas.")
    etiqueta = models.CharField("Funcionalidad", max_length=120)
    descripcion = models.TextField("Descripción comercial", blank=True, help_text="Opcional. Texto breve para presentar la funcionalidad.")
    icono = models.CharField("Ícono", max_length=40, blank=True, choices=ICONOS_FUNCIONALIDAD, help_text="Ícono lineal (Lucide).")
    grupo = models.CharField("Grupo", max_length=10, choices=[("basic", "Básica"), ("advanced", "Avanzada")], default="basic")
    resumen = models.BooleanField("Mostrar en el comparador resumido", default=True,
                                  help_text="Las que no están en el resumen aparecen con «Ver comparación completa».")
    visible = models.BooleanField("Visible en la web", default=True, help_text="Desmarcala para ocultarla sin borrarla.")
    orden = models.PositiveSmallIntegerField("Orden", default=0)
    actualizado = models.DateTimeField(auto_now=True)
    base_form_class = FormPorSitio

    panels = [
        MultiFieldPanel([FieldPanel("etiqueta"), FieldPanel("descripcion"), FieldPanel("icono")], "Funcionalidad"),
        MultiFieldPanel([FieldRowPanel([FieldPanel("sitio"), FieldPanel("linea")]),
                         FieldRowPanel([FieldPanel("grupo"), FieldPanel("orden")]),
                         FieldRowPanel([FieldPanel("resumen"), FieldPanel("visible")])], "Producto y presentación"),
        InlinePanel("valores", heading="Disponibilidad por plan", label="Plan",
                    help_text="No asumas que un plan superior incluye todo lo del anterior: cargá cada valor con su fuente. "
                              "«A confirmar» queda vacío en la web."),
    ]
    preview_modes = [("", "Comparador en la web")]

    class Meta:
        ordering = ["sitio", "grupo", "orden"]
        verbose_name = "funcionalidad"
        verbose_name_plural = "funcionalidades"

    def __str__(self):
        return self.etiqueta

    def serve_preview(self, request, mode_name):
        from publicacion.servicio import vista_previa_objeto
        return vista_previa_objeto(request, self, mode_name)


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


class SectorForm(FormPorSitio):
    """Las funcionalidades que se pueden vincular son las del mismo producto."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        campo = self.fields.get("funcionalidades")
        if campo is not None:
            sitio_id = self.instance.sitio_id or (self.data.get("sitio") if self.is_bound else None) or self.initial.get("sitio")
            campo.queryset = campo.queryset.filter(sitio_id=sitio_id) if sitio_id else campo.queryset.none()

    def clean(self):
        datos = super().clean()
        sitio = datos.get("sitio") or getattr(self.instance, "sitio", None)
        for f in datos.get("funcionalidades") or []:
            if sitio is not None and f.sitio_id != sitio.pk:
                self.add_error("funcionalidades", f"«{f}» es de otro producto.")
        if datos.get("visible") and datos.get("mostrar_tarjeta") and sitio is not None:
            from .sectores import SECCION_WEB
            if sitio.clave in SECCION_WEB:
                for campo in ("titulo", "texto"):
                    if not (datos.get(campo) or "").strip():
                        self.add_error(campo, "Hace falta para mostrar la tarjeta en la web.")
        return datos


class Sector(WorkflowMixin, DraftStateMixin, LockableMixin, RevisionMixin, PreviewableMixin, ClusterableModel, ContenidoSitio):
    """Destinatario comercial de un producto. Lo de «Contenido web» edita las tarjetas que la web ya tiene (GERP, GEMA);
    la «Información interna» y las funcionalidades vinculadas no se publican nunca."""
    # Contenido web
    nombre = models.CharField("Nombre comercial", max_length=80, default="", help_text="Cómo lo llamamos internamente. Ej.: Talleres de matafuegos.")
    titulo = models.CharField("Título", max_length=60, blank=True, help_text="Título de la tarjeta en la web.")
    texto = models.CharField("Descripción breve", max_length=200, blank=True, help_text="Texto de la tarjeta en la web.")
    descripcion = models.TextField("Descripción ampliada", blank=True, help_text="Opcional. Por ahora no se muestra en la web.")
    icono = models.CharField("Ícono de la web", max_length=200, blank=True,
                             help_text="El que usa la web hoy: archivo (img/sectores/…) o Bootstrap Icon (bi-…).")
    imagen = models.ForeignKey("wagtailimages.Image", verbose_name="Imagen", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="+", help_text="Opcional. Por ahora no se muestra en la web.")
    enlace = models.CharField("Enlace o destino", max_length=200, blank=True, help_text="Opcional. Por ahora las tarjetas no llevan enlace.")
    orden = models.PositiveSmallIntegerField("Orden", default=0)
    mostrar_tarjeta = models.BooleanField("Mostrar como tarjeta de sector en la web", default=True,
                                          help_text="Solo si la web del producto tiene sección de sectores (GERP y GEMA). No crea secciones nuevas.")
    # Información interna (no se exporta)
    descripcion_interna = models.TextField("Descripción interna", blank=True)
    necesidades = models.TextField("Necesidades y problemas del sector", blank=True)
    funcionalidades = ParentalManyToManyField("Funcionalidad", verbose_name="Funcionalidades relevantes", blank=True, related_name="sectores",
                                              help_text="De «Oferta comercial → Funcionalidades» del mismo producto. Relación interna: no se publica.")
    observaciones = models.TextField("Observaciones comerciales", blank=True)
    responsable = models.CharField("Responsable o referente", max_length=120, blank=True)
    # Configuración
    visible = models.BooleanField("Visible en la web", default=True, help_text="Desmarcalo para ocultarlo sin borrarlo.")
    base_form_class = SectorForm

    edit_handler = TabbedInterface([
        ObjectList([
            HelpPanel("<p>Estos campos editan las tarjetas de sectores que la web del producto ya tiene. "
                      "En GERP: «Pensado para tu sector»; en GEMA: «¿Para quién es GEMA?». La web de GEAGRO no tiene esa sección.</p>"),
            FieldRowPanel([FieldPanel("nombre"), FieldPanel("titulo")]), FieldPanel("texto"), FieldPanel("descripcion"),
            FieldRowPanel([FieldPanel("icono"), FieldPanel("imagen")]), FieldPanel("enlace"),
            FieldRowPanel([FieldPanel("orden"), FieldPanel("mostrar_tarjeta")]),
        ], heading="Contenido web"),
        ObjectList([
            HelpPanel("<p><b>Privado:</b> nada de esta pestaña se exporta a las webs.</p>"),
            FieldPanel("descripcion_interna"), FieldPanel("necesidades"),
            FieldPanel("funcionalidades", widget=forms.CheckboxSelectMultiple),
            FieldPanel("observaciones"), FieldPanel("responsable"),
        ], heading="Información interna"),
        ObjectList([
            FieldRowPanel([FieldPanel("sitio"), FieldPanel("linea")]), FieldPanel("visible"),
            HelpPanel("<p>El estado editorial (borrador, aprobado) y el historial de cambios están arriba, en la barra de la ficha. "
                      "Lo aprobado se ve en la web después de «Publicar en la web».</p>"),
        ], heading="Configuración"),
    ])

    class Meta:
        ordering = ["sitio", "orden"]
        verbose_name = "sector"
        verbose_name_plural = "sectores"

    def __str__(self):
        return self.nombre or self.titulo

    def serve_preview(self, request, mode_name):
        from publicacion.servicio import vista_previa_objeto
        return vista_previa_objeto(request, self, mode_name)


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


# ---------------------------------------------------------------------------------------------- Identidad visual
FORMATOS_LOGO = (".svg", ".png", ".webp", ".jpg", ".jpeg")


def _ext(imagen):
    return ("." + imagen.file.name.rsplit(".", 1)[-1].lower()) if imagen and imagen.file else ""


def validar_logo(imagen, campo, minimo=300):
    """Logos: SVG (recomendado) o una imagen de al menos `minimo` px de ancho."""
    from django.core.exceptions import ValidationError
    if imagen is None:
        return
    ext = _ext(imagen)
    if ext not in FORMATOS_LOGO:
        raise ValidationError({campo: "Usá un SVG (recomendado), PNG, WebP o JPG."})
    if ext != ".svg" and imagen.width < minimo:
        raise ValidationError({campo: f"La imagen mide {imagen.width} px de ancho; necesita al menos {minimo} px para verse nítida (o subí un SVG)."})


class IdentidadSitio(WorkflowMixin, DraftStateMixin, LockableMixin, RevisionMixin, PreviewableMixin, models.Model):
    """Logos y favicon de cada web. Vacío = se usan los de siempre."""
    base_form_class = FormPorSitio
    sitio = models.OneToOneField(SitioWeb, verbose_name="Sitio", on_delete=models.CASCADE, related_name="identidad")
    logo = models.ForeignKey("wagtailimages.Image", verbose_name="Logo a color (encabezado)", null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="+", help_text="SVG recomendado. PNG o WebP de al menos 300 px de ancho.")
    logo_blanco = models.ForeignKey("wagtailimages.Image", verbose_name="Logo blanco (portada y pie)", null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+", help_text="Versión para fondos oscuros. SVG recomendado.")
    favicon = models.ForeignKey("wagtailimages.Image", verbose_name="Favicon", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="+", help_text="PNG cuadrado de al menos 512 × 512 px. Con él se generan todos los tamaños "
                                                            "(pestaña del navegador, iPhone, Android y accesos directos).")
    favicon_svg = models.ForeignKey("wagtailimages.Image", verbose_name="Favicon en SVG (opcional)", null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+", help_text="Se usa en los navegadores que lo admiten; se ve nítido en cualquier tamaño.")
    actualizado = models.DateTimeField(auto_now=True)

    panels = [
        HelpPanel("<p>Elegí o subí las imágenes desde la biblioteca. Los campos vacíos mantienen los logos y el favicon actuales. "
                  "Guardá el borrador, mirá la vista previa y publicalo: los cambios llegan a la web en la próxima publicación.</p>"),
        FieldPanel("sitio", read_only=True),
        MultiFieldPanel([FieldRowPanel([FieldPanel("logo"), FieldPanel("logo_blanco")])], "Logos"),
        MultiFieldPanel([FieldRowPanel([FieldPanel("favicon"), FieldPanel("favicon_svg")])], "Favicon"),
    ]
    preview_modes = [("", "Inicio del sitio")]

    class Meta:
        verbose_name = "identidad visual"
        verbose_name_plural = "identidad visual"

    def __str__(self):
        return f"Identidad de {self.sitio.nombre}"

    @property
    def linea_id(self):  # la identidad es de todo el sitio
        return None

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError
        validar_logo(self.logo, "logo")
        validar_logo(self.logo_blanco, "logo_blanco")
        if self.favicon:
            if _ext(self.favicon) not in (".png", ".webp", ".jpg", ".jpeg"):
                raise ValidationError({"favicon": "El favicon tiene que ser un PNG (o WebP/JPG) cuadrado. Si tenés un SVG, cargalo en «Favicon en SVG»."})
            w, h = self.favicon.width, self.favicon.height
            if abs(w - h) > max(2, w * 0.02):
                raise ValidationError({"favicon": f"El favicon tiene que ser cuadrado; la imagen mide {w} × {h} px."})
            if w < 512:
                raise ValidationError({"favicon": f"La imagen mide {w} × {h} px; necesita al menos 512 × 512 px para Android y los accesos directos."})
        if self.favicon_svg and _ext(self.favicon_svg) != ".svg":
            raise ValidationError({"favicon_svg": "Este campo es solo para archivos SVG."})

    def serve_preview(self, request, mode_name):
        from publicacion.servicio import vista_previa_objeto
        return vista_previa_objeto(request, self, mode_name)


def texto_plano(html):
    return strip_tags(html or "").strip()
