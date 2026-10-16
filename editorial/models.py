"""Blog y noticias universal: configuración del blog de cada sitio, tendencias e ideas para publicar y consumo de IA.

Los artículos son páginas de Wagtail (contenidos.ArticuloPage) dentro del blog general de cada sitio. Acá vive lo que
cambia de un sitio a otro sin tocar código: si el blog está activo, su nombre en el menú, su dirección y qué muestra.
"""
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from wagtail.admin.panels import FieldPanel, FieldRowPanel, HelpPanel, MultiFieldPanel, ObjectList, TabbedInterface
from wagtail.models import DraftStateMixin, LockableMixin, RevisionMixin, WorkflowMixin

from sitios.models import LineaProducto, SitioWeb

NOMBRES_MENU = [("Blog", "Blog"), ("Noticias", "Noticias")]
RUTA_VALIDA = RegexValidator(r"^[a-z0-9]+(-[a-z0-9]+)*$", "Solo minúsculas, números y guiones. Ej.: blog o noticias")

# Temas por defecto de cada producto (se editan en la configuración). Guían las tendencias y las ideas editoriales.
TEMAS = {
    "geneos": ("Cooperativismo, software libre, tecnología, desarrollo de software y transformación digital.", ""),
    "gerp": ("ERP, gestión empresarial, inventarios, facturación, administración y productividad.", ""),
    "geagro": ("Agricultura, cereales, cosechas, viñedos, vitivinicultura y gestión agrícola.", "ganadería, ganado, hacienda, tambo, feedlot"),
    "gema": ("Talleres de matafuegos, mantenimiento de extintores, vencimientos y seguridad contra incendios.", ""),
}


class ConfigBlog(WorkflowMixin, DraftStateMixin, LockableMixin, RevisionMixin, models.Model):
    """Blog de un sitio. Activarlo no publica nada: la web lo muestra recién con la configuración aprobada
    y después de «Publicar en la web»."""
    sitio = models.OneToOneField(SitioWeb, verbose_name="Sitio", on_delete=models.CASCADE, related_name="config_blog")
    activo = models.BooleanField("Blog activo en la web", default=False,
                                 help_text="Con la configuración aprobada, agrega el enlace al menú y genera la portada y los artículos aprobados.")
    nombre_menu = models.CharField("Nombre público", max_length=20, choices=NOMBRES_MENU, default="Blog")
    titulo = models.CharField("Título de la portada", max_length=90)
    descripcion = models.TextField("Descripción", max_length=300, blank=True, help_text="Se muestra debajo del título y como descripción en buscadores.")
    ruta = models.CharField("Dirección del listado", max_length=40, default="blog", validators=[RUTA_VALIDA],
                            help_text="Sin barras: blog → /blog/. Cambiarla cambia la dirección de todos los artículos.")
    menu_posicion = models.PositiveSmallIntegerField("Ubicación en el menú", default=0,
                                                     help_text="0: al final, antes de «Solicitar demo». 1: primer lugar; 2: segundo…")
    articulos_por_pagina = models.PositiveSmallIntegerField("Artículos por página", default=9)
    mostrar_categorias = models.BooleanField("Categorías", default=True)
    mostrar_autor = models.BooleanField("Autor", default=True)
    mostrar_fecha = models.BooleanField("Fecha", default=True)
    mostrar_relacionados = models.BooleanField("Artículos relacionados", default=True)
    mostrar_destacado = models.BooleanField("Artículo destacado en la portada", default=True)
    mostrar_buscador = models.BooleanField("Buscador y filtros", default=True)
    listados_por_linea = models.BooleanField("Listados por línea", default=True,
                                             help_text="GEAGRO: /cereales/blog/ y /vid/blog/ muestran los artículos de cada línea, enlazados a su única dirección.")
    temas = models.TextField("Temas del blog", blank=True, help_text="Orientan las tendencias y las ideas para publicar.")
    excluir = models.CharField("Temas que no corresponden", max_length=300, blank=True,
                               help_text="Separados por coma. Las ideas que los mencionen no se muestran. Ej.: ganadería en GEAGRO.")
    actualizado = models.DateTimeField(auto_now=True)

    panels_general = [
        HelpPanel("<p>Activar el blog no publica nada por sí solo: hace falta aprobar esta configuración y después usar «Publicar en la web».</p>"),
        FieldPanel("sitio", read_only=True), FieldPanel("activo"),
        FieldRowPanel([FieldPanel("nombre_menu"), FieldPanel("ruta")]),
        FieldPanel("titulo"), FieldPanel("descripcion"),
        FieldRowPanel([FieldPanel("menu_posicion"), FieldPanel("articulos_por_pagina")]),
    ]
    panels_mostrar = [
        MultiFieldPanel([FieldRowPanel([FieldPanel("mostrar_categorias"), FieldPanel("mostrar_autor"), FieldPanel("mostrar_fecha")]),
                         FieldRowPanel([FieldPanel("mostrar_relacionados"), FieldPanel("mostrar_destacado"), FieldPanel("mostrar_buscador")])],
                        "Qué se muestra"),
        FieldPanel("listados_por_linea"),
    ]
    panels_temas = [FieldPanel("temas"), FieldPanel("excluir")]
    edit_handler = TabbedInterface([ObjectList(panels_general, heading="Blog"), ObjectList(panels_mostrar, heading="Portada y artículos"),
                                    ObjectList(panels_temas, heading="Temas e ideas")])

    class Meta:
        verbose_name = "configuración del blog"
        verbose_name_plural = "configuraciones del blog"

    def __str__(self):
        return f"{self.nombre_menu} de {self.sitio.nombre}"

    @classmethod
    def nueva(cls, sitio):
        temas, excluir = TEMAS.get(sitio.clave, ("", ""))
        nombre = "Noticias" if sitio.motor == "institucional" else "Blog"
        return cls(sitio=sitio, nombre_menu=nombre, ruta=nombre.lower(), titulo=f"{nombre} de {sitio.nombre}", descripcion=temas,
                   temas=temas, excluir=excluir, live=False)

    @property
    def terminos_excluidos(self):
        return [t.strip().lower() for t in self.excluir.split(",") if t.strip()]


def config_aprobada(sitio):
    """Configuración vigente (la aprobada). None si nunca se aprobó."""
    c = ConfigBlog.objects.filter(sitio=sitio).first()
    if c is None or not c.live:
        return None
    return c


def config_actual(sitio):
    """La versión con la que se trabaja: el borrador si hay cambios sin aprobar."""
    c = ConfigBlog.objects.filter(sitio=sitio).first()
    if c is None:
        return None
    return c.get_latest_revision_as_object() if c.has_unpublished_changes and c.latest_revision_id else c


def ruta_blog(sitio):
    """Ruta pública del blog general del sitio («blog/»). La aprobada manda; si nunca se aprobó, la del borrador."""
    c = config_aprobada(sitio) or config_actual(sitio)
    if c is not None:
        return c.ruta.strip("/") + "/"
    from contenidos.models import BlogIndexPage
    if sitio.site:
        idx = BlogIndexPage.objects.descendant_of(sitio.site.root_page).filter(linea__isnull=True).first()
        if idx and idx.ruta_publica:
            return idx.ruta_publica
    return "blog/"


# ------------------------------------------------------------------------------------------------ Tendencias e ideas
# Qué es cada tarjeta de «Actualidad e ideas para publicar». Nunca se presenta una cosa como otra:
TIPOS_IDEA = [
    ("noticia", "Noticia"),                   # publicada por una fuente identificable, con enlace y fecha
    ("evento", "Evento"),                     # actividad real con fecha, lugar y organizador verificables
    ("tendencia", "Tendencia de búsqueda"),   # respaldada por datos reales (Google Trends: RSS oficial o archivo exportado)
    ("idea", "Idea editorial"),               # sugerencia propia: de noticias, funcionalidades, sectores, preguntas frecuentes o IA
]
TIPOS_FUENTE = [("medio", "Medio periodístico"), ("oficial", "Organismo o institución"), ("gdelt", "Búsqueda de noticias (GDELT)"),
                ("evento", "Organizador de eventos"), ("red_social", "Red social"), ("trends", "Google Trends"), ("interno", "Contenidos propios"),
                ("ia", "Inteligencia artificial")]
# Naturaleza de lo que se muestra, para no confundir una publicación oficial con una nota que la menciona.
NATURALEZAS = [("oficial", "Publicación oficial"),             # publicada por el organismo o la institución en su propio canal
               ("periodistica", "Noticia periodística"),       # medio o búsqueda de noticias; puede mencionar una norma, pero no es la norma
               ("evento", "Evento"), ("tendencia", "Tendencia de búsqueda"), ("idea", "Idea editorial")]
ESTADOS_IDEA = [("sugerida", "Sugerida"), ("guardada", "Guardada"), ("descartada", "Descartada"), ("usada", "Con borrador")]


class ImportacionTendencias(models.Model):
    """Archivo de Google Trends (u otra fuente) importado a mano, con la fecha y la región de la consulta."""
    sitio = models.ForeignKey(SitioWeb, on_delete=models.CASCADE, related_name="importaciones_tendencias")
    linea = models.ForeignKey(LineaProducto, null=True, blank=True, on_delete=models.SET_NULL)
    fuente = models.CharField(max_length=80, default="Google Trends (CSV)")
    archivo = models.CharField("Nombre del archivo", max_length=200, blank=True)
    termino = models.CharField("Término consultado", max_length=120, blank=True)
    region = models.CharField("Región", max_length=60, default="Argentina")
    periodo = models.CharField("Período", max_length=60, blank=True)
    consultado = models.DateField("Fecha de la consulta")
    filas = models.PositiveIntegerField(default=0)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado"]
        verbose_name = "importación de tendencias"
        verbose_name_plural = "importaciones de tendencias"


class IdeaEditorial(models.Model):
    """Tarjeta de «Actualidad e ideas para publicar»: una noticia, un evento, una tendencia de búsqueda o una idea editorial,
    con la propuesta de artículo que podríamos escribir. Se guarda la fecha original y la de consulta; nunca se copia el contenido."""
    sitio = models.ForeignKey(SitioWeb, on_delete=models.CASCADE, related_name="ideas")
    linea = models.ForeignKey(LineaProducto, null=True, blank=True, on_delete=models.SET_NULL)
    tipo = models.CharField(max_length=12, choices=TIPOS_IDEA)
    fuente_tipo = models.CharField("Tipo de fuente", max_length=12, choices=TIPOS_FUENTE, default="interno")
    titulo = models.CharField("Título de la noticia, evento o tema", max_length=200)
    resumen = models.TextField("Resumen breve", blank=True)
    descripcion = models.TextField("Por qué es relevante", blank=True)
    propuesta = models.CharField("Artículo que podríamos escribir", max_length=200, blank=True)
    palabras_clave = models.CharField(max_length=250, blank=True)
    intencion = models.CharField("Intención de búsqueda", max_length=40, blank=True)
    fuente = models.CharField("Fuente original", max_length=120)
    fuente_url = models.URLField(blank=True, max_length=600)
    publicado = models.DateField("Fecha de publicación original", null=True, blank=True)
    dato = models.CharField("Dato de la fuente", max_length=60, blank=True,
                            help_text="Valor tal como figura en la fuente (p. ej. «Aumento puntual» o «+250 %»). Nunca se calcula ni se estima.")
    consultado = models.DateField("Fecha de consulta")
    evento_fecha = models.DateField("Fecha del evento", null=True, blank=True)
    evento_lugar = models.CharField("Lugar", max_length=120, blank=True)
    organizador = models.CharField(max_length=120, blank=True)
    imagen_url = models.URLField("Imagen", blank=True, max_length=600,
                                 help_text="Solo si la fuente permite usarla (licencia libre o imagen propia). Por defecto no se muestran fotos de terceros.")
    imagen_credito = models.CharField(max_length=160, blank=True)
    generada_ia = models.BooleanField(default=False)
    grupo = models.CharField(max_length=80, blank=True, help_text="Agrupa noticias sobre el mismo tema.")
    enlace_comercial = models.CharField("Página comercial relacionada", max_length=200, blank=True)
    estado = models.CharField(max_length=12, choices=ESTADOS_IDEA, default="sugerida")
    clave = models.CharField(max_length=200, blank=True, help_text="Evita repetir la misma noticia o idea al actualizar.")
    importacion = models.ForeignKey(ImportacionTendencias, null=True, blank=True, on_delete=models.CASCADE, related_name="ideas")
    articulo = models.ForeignKey("contenidos.ArticuloPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    # Lectura automática y carga manual
    fuente_actualidad = models.ForeignKey("FuenteActualidad", null=True, blank=True, on_delete=models.SET_NULL, related_name="items",
                                          verbose_name="Fuente leída")
    naturaleza = models.CharField(max_length=12, choices=NATURALEZAS, blank=True)
    menciona_normativa = models.BooleanField(default=False, help_text="Menciona una ley, resolución o norma: verificar el documento oficial.")
    relacion = models.CharField("Relación con el producto", max_length=300, blank=True)
    prioritaria = models.BooleanField(default=False)
    cargada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    # Eventos
    evento_fin = models.DateField("Finaliza", null=True, blank=True)
    modalidad = models.CharField(max_length=20, blank=True, help_text="Presencial, virtual o híbrido.")
    fecha_confirmada = models.BooleanField("Fecha confirmada", default=False,
                                           help_text="Solo los eventos con fecha confirmada por una fuente confiable se muestran como próximos.")
    fecha_fuente = models.CharField("De dónde sale la fecha", max_length=160, blank=True)
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creada"]
        verbose_name = "actualidad o idea para publicar"
        verbose_name_plural = "actualidad e ideas para publicar"

    def __str__(self):
        return self.titulo

    @property
    def verificada(self):
        """Noticias, eventos y tendencias vienen de una fuente externa identificable; las ideas no."""
        return self.tipo in ("noticia", "evento", "tendencia")

    @property
    def fecha(self):
        return self.publicado or self.consultado

    @property
    def es_oficial(self):
        return self.naturaleza == "oficial"

    @property
    def etiqueta(self):
        """Lo que dice la tarjeta arriba: nunca presenta una nota periodística como publicación oficial."""
        if self.tipo == "noticia":
            return "Publicación oficial" if self.naturaleza == "oficial" else "Noticia periodística"
        return self.get_tipo_display()


# ------------------------------------------------------------------------------------------------ Lectura automática
PRODUCTOS = [("geneos", "GENEOS"), ("gerp", "GERP"), ("geagro", "GEAGRO"), ("gema", "GEMA"), ("todos", "Todos los productos")]
METODOS = [("rss", "RSS / Atom"), ("gdelt", "GDELT (API de búsqueda de noticias)"), ("youtube", "YouTube Data API"),
           ("trends", "Google Trends (RSS)"), ("google_news", "Google News RSS (experimental)"), ("ninguno", "Sin canal legible")]
ESTADOS_FUENTE = [("prueba", "En prueba"), ("activa", "Activa"), ("pausada", "Pausada"), ("descartada", "Descartada"),
                  ("sin_canal", "Sin canal automático"), ("experimental", "Experimental, desactivada")]


class FuenteActualidad(models.Model):
    """Fuente pública que lee «Actualidad e ideas para publicar». Solo se muestran resultados de fuentes verificadas:
    accesibles desde el servidor, permitidas (robots.txt y condiciones), con publicaciones reales (título, fecha y enlace)
    y con contenido relacionado con el producto."""
    clave = models.SlugField(max_length=60, unique=True)
    producto = models.CharField(max_length=8, choices=PRODUCTOS)
    linea = models.CharField("Línea", max_length=20, blank=True, help_text="GEAGRO: cereales o vid. Vacío: se clasifica por tema.")
    nombre = models.CharField(max_length=120)
    organizacion = models.CharField("Organización", max_length=120, blank=True)
    fuente_tipo = models.CharField(max_length=12, choices=TIPOS_FUENTE, default="medio")
    naturaleza = models.CharField(max_length=12, choices=NATURALEZAS, default="periodistica")
    tipo = models.CharField(max_length=12, choices=TIPOS_IDEA, default="noticia")
    metodo = models.CharField(max_length=12, choices=METODOS, default="rss")
    url = models.URLField("Dirección del feed o canal", max_length=600, blank=True)
    consulta = models.CharField(max_length=400, blank=True, help_text="GDELT: términos de búsqueda. YouTube: id del canal (UC…).")
    sitio_web = models.URLField(blank=True, max_length=300)
    relacion = models.CharField("Relación con el producto", max_length=300)
    terminos = models.TextField("Términos de relevancia", blank=True,
                                help_text="Separados por coma. Vacío: los del producto. Una publicación sin ninguno no se muestra.")
    filtrar = models.BooleanField("Filtrar por términos", default=True)
    condiciones = models.CharField("Condiciones de uso", max_length=300, blank=True)
    estado = models.CharField(max_length=12, choices=ESTADOS_FUENTE, default="prueba")
    prioritaria = models.BooleanField(default=False, help_text="Sus novedades actuales y relevantes aparecen antes que las demás.")
    orden = models.PositiveSmallIntegerField(default=0)
    # Resultado de la verificación y de la última lectura
    verificada = models.DateTimeField(null=True, blank=True, help_text="Cuándo pasó por primera vez todos los controles.")
    motivo = models.CharField("Resultado", max_length=300, blank=True)
    ultima_lectura = models.DateTimeField(null=True, blank=True)
    ultimo_ok = models.DateTimeField(null=True, blank=True)
    ultimo_error = models.CharField(max_length=300, blank=True)
    items_leidos = models.PositiveIntegerField(default=0)
    items_relevantes = models.PositiveIntegerField(default=0)
    items_nuevos = models.PositiveIntegerField(default=0)
    ultimo_item = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["producto", "orden", "nombre"]
        verbose_name = "fuente de actualidad"
        verbose_name_plural = "fuentes de actualidad"

    def __str__(self):
        return self.nombre

    @property
    def muestra_resultados(self):
        return self.estado == "activa" and self.verificada is not None

    @property
    def estado_legible(self):
        if self.estado == "activa" and self.ultimo_error:
            return "Activa · última lectura con error"
        if self.estado == "prueba" and self.ultima_lectura:
            return "En prueba · no pasó los controles"
        return self.get_estado_display()


ORIGENES_ACTUALIZACION = [("ingreso", "Al ingresar al administrador"), ("boton", "«Actualizar ahora»"), ("comando", "Comando o tarea programada")]


class ActualizacionActualidad(models.Model):
    """Cada lectura de fuentes. Se muestra la fecha de la última y su resultado."""
    inicio = models.DateTimeField(auto_now_add=True)
    fin = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=10, default="corriendo")  # corriendo, ok, parcial, error
    origen = models.CharField(max_length=8, choices=ORIGENES_ACTUALIZACION)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    fuentes_ok = models.PositiveSmallIntegerField(default=0)
    fuentes_error = models.PositiveSmallIntegerField(default=0)
    nuevos = models.PositiveIntegerField(default=0)
    detalle = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-inicio"]
        verbose_name = "actualización de fuentes"
        verbose_name_plural = "actualizaciones de fuentes"


class CerrojoActualidad(models.Model):
    """Una sola fila: evita dos lecturas al mismo tiempo (UPDATE atómico sobre «hasta»)."""
    hasta = models.DateTimeField()


class ConsumoIA(models.Model):
    """Registro de cada pedido a un proveedor de IA, para respetar el límite mensual."""
    sitio = models.ForeignKey(SitioWeb, null=True, blank=True, on_delete=models.SET_NULL)
    proveedor = models.CharField(max_length=40)
    modelo = models.CharField(max_length=80)
    tarea = models.CharField(max_length=40)
    tokens_entrada = models.PositiveIntegerField(default=0)
    tokens_salida = models.PositiveIntegerField(default=0)
    busquedas = models.PositiveIntegerField(default=0)
    costo_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    ok = models.BooleanField(default=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado"]
        verbose_name = "consumo de IA"
        verbose_name_plural = "consumos de IA"
