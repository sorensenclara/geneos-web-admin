from django.utils.timezone import localtime
from wagtail.admin.ui.tables import Column
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

from sitios.permisos import ProtegerObjetos, SitioPermissionPolicy

from .models import CategoriaBlog, Funcionalidad, Plan, PreguntaFrecuente, Recurso, Redireccion, Sector, Testimonio


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
    list_display = ["__str__", "sitio", "precio", "implementacion", "visible", "live",
                    Column("ultima_modificacion", label="Última modificación", accessor=lambda p: p.ultima_modificacion and localtime(p.ultima_modificacion).strftime("%d/%m/%Y %H:%M")),
                    Column("modificado_por", label="Modificado por")]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("latest_revision__user", "sitio")


class FuncionalidadViewSet(PorSitio):
    model = Funcionalidad
    icon = "tasks"
    menu_label = "Comparador"
    list_display = ["etiqueta", "sitio", "grupo", "resumen", "orden"]
    list_filter = ["sitio", "grupo"]


class SectorViewSet(PorSitio):
    model = Sector
    icon = "group"
    menu_label = "Sectores"
    list_display = ["titulo", "sitio", "orden"]


class ComercialGroup(SnippetViewSetGroup):
    menu_label = "Oferta comercial"
    menu_icon = "tag"
    menu_order = 210
    items = (PlanViewSet, FuncionalidadViewSet, SectorViewSet)


class FAQViewSet(PorSitio):
    model = PreguntaFrecuente
    icon = "help"
    menu_label = "Preguntas frecuentes"
    list_display = ["pregunta", "sitio", "ubicacion", "orden", "visible", "live"]
    list_filter = ["sitio", "ubicacion"]


class TestimonioViewSet(PorSitio):
    model = Testimonio
    icon = "openquote"
    menu_label = "Testimonios"
    list_display = ["empresa", "sitio", "estado", "visible", "live"]
    list_filter = ["sitio", "estado"]


class RecursoViewSet(PorSitio):
    model = Recurso
    icon = "doc-full"
    menu_label = "Recursos descargables"
    list_display = ["titulo", "sitio", "tipo", "visible"]


class CategoriaViewSet(PorSitio):
    model = CategoriaBlog
    icon = "folder-open-inverse"
    menu_label = "Categorías del blog"
    list_display = ["nombre", "sitio", "linea"]


class RedireccionViewSet(PorSitio):
    model = Redireccion
    icon = "redirect"
    menu_label = "Redirecciones 301"
    list_display = ["origen", "destino", "sitio"]


class ContenidosGroup(SnippetViewSetGroup):
    menu_label = "Contenidos"
    menu_icon = "folder-inverse"
    menu_order = 220
    items = (FAQViewSet, TestimonioViewSet, RecursoViewSet, CategoriaViewSet, RedireccionViewSet)


register_snippet(ComercialGroup)
register_snippet(ContenidosGroup)
