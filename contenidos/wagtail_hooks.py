from django.utils.timezone import localtime
from wagtail.admin.ui.tables import Column
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import CreateView as SnippetCreateView, SnippetViewSet, SnippetViewSetGroup

from sitios.columnas import columna_sitio
from sitios.permisos import ProtegerObjetos, SitioPermissionPolicy

from django.urls import path
from wagtail.admin.viewsets.base import ViewSet

from .models import AutorBlog, IdentidadSitio, CategoriaBlog, Funcionalidad, Plan, PreguntaFrecuente, Recurso, Redireccion, Sector, Testimonio


class PorSitio(ProtegerObjetos, SnippetViewSet):
    """Listado acotado a los sitios del usuario y al sitio activo elegido en el menú."""
    list_filter = ["sitio"]

    @property
    def permission_policy(self):
        return SitioPermissionPolicy(self.model)

    def get_queryset(self, request):
        qs = self.permission_policy.instances_user_has_any_permission_for(request.user, ["view", "change"])
        activo = request.session.get("gwa_sitio")
        if activo:
            qs = qs.filter(sitio__clave=activo)
        return qs


class PlanViewSet(PorSitio):
    model = Plan
    icon = "tag"
    menu_label = "Planes y precios"
    list_display = ["__str__", columna_sitio(), "precio", "implementacion", "visible", "live",
                    Column("ultima_modificacion", label="Última modificación", accessor=lambda p: p.ultima_modificacion and localtime(p.ultima_modificacion).strftime("%d/%m/%Y %H:%M")),
                    Column("modificado_por", label="Modificado por")]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("latest_revision__user", "sitio")

    @property
    def index_view(self):
        """El listado de planes es la pantalla de precios agrupada por producto (publicacion.views.precios):
        edición directa de abono, implementación y vigencia, con revisiones, permisos y aprobación de Wagtail.
        Las demás vistas del plan (edición completa, vista previa, historial…) son las de Wagtail."""
        from publicacion.views import precios
        return precios


class CrearConProducto(SnippetCreateView):
    """«Añadir funcionalidad» desde la pestaña de un producto: el formulario llega con ese producto elegido."""
    usa_sitio_del_blog = False

    def get_initial_form_instance(self):
        obj = super().get_initial_form_instance()
        clave = self.request.GET.get("sitio") or (self.request.session.get("gwa_blog_sitio") if self.usa_sitio_del_blog else "")
        if clave:
            from sitios.models import SitioWeb
            sitio = SitioWeb.objects.filter(clave=clave).first()
            if sitio is not None:
                obj = obj or self.model()
                obj.sitio = sitio
        return obj


class FuncionalidadViewSet(PorSitio):
    """«Oferta comercial → Funcionalidades» (antes «Comparador»): mismo modelo y mismos datos."""
    model = Funcionalidad
    icon = "package"
    menu_label = "Funcionalidades"
    add_view_class = CrearConProducto
    list_display = ["etiqueta", columna_sitio(), "grupo", "resumen", "orden"]
    list_filter = ["sitio", "grupo"]

    @property
    def index_view(self):
        """El listado es la pantalla por producto con las vistas Comparador y Lista (publicacion/funcionalidades.py).
        Edición completa, historial y vista previa siguen siendo las vistas de Wagtail."""
        from publicacion.funcionalidades import funcionalidades
        return funcionalidades


class SectorViewSet(PorSitio):
    """«Oferta comercial → Sectores»: destinatarios comerciales de cada producto (contenido web e información interna)."""
    model = Sector
    icon = "group"
    menu_label = "Sectores"
    add_view_class = CrearConProducto
    list_display = ["titulo", columna_sitio(), "orden"]

    @property
    def index_view(self):
        """Listado de todos los productos con estado editorial y presencia en la web (publicacion/sectores.py)."""
        from publicacion.sectores import sectores
        return sectores


class ComercialGroup(SnippetViewSetGroup):
    menu_label = "Oferta comercial"
    menu_icon = "megaphone"
    menu_order = 210
    items = (PlanViewSet, FuncionalidadViewSet, SectorViewSet)


class FAQViewSet(PorSitio):
    model = PreguntaFrecuente
    icon = "help"
    menu_label = "Preguntas frecuentes"
    list_display = ["pregunta", columna_sitio(), "ubicacion", "orden", "visible", "live"]
    list_filter = ["sitio", "ubicacion"]


class TestimonioViewSet(PorSitio):
    model = Testimonio
    icon = "openquote"
    menu_label = "Testimonios"
    list_display = ["empresa", columna_sitio(), "estado", "visible", "live"]
    list_filter = ["sitio", "estado"]


class RecursoViewSet(PorSitio):
    model = Recurso
    icon = "doc-full"
    menu_label = "Recursos descargables"
    list_display = ["titulo", columna_sitio(), "tipo", "visible"]


class BlogViewSet(ViewSet):
    """«Contenidos → Blog y noticias»: selector de sitio, tendencias e ideas, y artículos (editorial/vistas.py)."""
    name = "blog"
    url_prefix = "blog"
    icon = "doc-full"
    menu_label = "Blog y noticias"

    def get_urlpatterns(self):
        from editorial import vistas
        return [
            path("", vistas.blog, name="index"),
            path("<slug:clave>/actualizar/", vistas.actualizar, name="actualizar"),
            path("<slug:clave>/importar/", vistas.importar, name="importar"),
            path("<slug:clave>/nuevo/", vistas.nuevo, name="nuevo"),
            path("<slug:clave>/configurar/", vistas.configurar, name="configurar"),
            path("<slug:clave>/actualidad/", vistas.actualidad, name="actualidad"),
            path("idea/<int:pk>/", vistas.idea_detalle, name="idea"),
            path("idea/<int:pk>/<slug:accion>/", vistas.idea_accion, name="idea_accion"),
        ]


class CrearConSitioDelBlog(CrearConProducto):
    usa_sitio_del_blog = True


class PorSitioDelBlog(PorSitio):
    """Categorías y Autores usan el sitio elegido en «Blog y noticias» (o el de «Trabajar en»)."""
    add_view_class = CrearConSitioDelBlog

    def get_queryset(self, request):
        qs = self.permission_policy.instances_user_has_any_permission_for(request.user, ["view", "change"])
        activo = request.session.get("gwa_blog_sitio") or request.session.get("gwa_sitio")
        return qs.filter(sitio__clave=activo) if activo else qs


class CategoriaViewSet(PorSitioDelBlog):
    model = CategoriaBlog
    icon = "tag"
    menu_label = "Categorías"
    list_display = ["nombre", columna_sitio(), "linea"]


class AutorViewSet(PorSitioDelBlog):
    model = AutorBlog
    icon = "user"
    menu_label = "Autores"
    list_display = ["nombre", columna_sitio(), "cargo", "activo"]


class RedireccionViewSet(PorSitio):
    model = Redireccion
    icon = "redirect"
    menu_label = "Redirecciones 301"
    list_display = ["origen", "destino", columna_sitio()]


class IdentidadViewSet(PorSitio):
    model = IdentidadSitio
    icon = "image"
    menu_label = "Logos y favicon"
    list_display = ["__str__", columna_sitio(), "live"]
    list_filter = []


class ContenidosGroup(SnippetViewSetGroup):
    menu_label = "Contenidos"
    menu_icon = "folder-inverse"
    menu_order = 220
    items = (BlogViewSet, CategoriaViewSet, AutorViewSet, IdentidadViewSet, FAQViewSet, TestimonioViewSet, RecursoViewSet, RedireccionViewSet)


register_snippet(ComercialGroup)
register_snippet(ContenidosGroup)
