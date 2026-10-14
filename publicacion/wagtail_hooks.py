from django.templatetags.static import static
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.ui.components import Component

from formularios.models import SolicitudDemo
from sitios.models import SitioWeb
from sitios.permisos import sitios_permitidos

from . import views
from .servicio import estado_sitio


@hooks.register("register_admin_urls")
def urls():
    return [
        path("web/", views.estado, name="gwa_estado"),
        path("web/<slug:clave>/", views.sitio_detalle, name="gwa_sitio"),
        path("web/<slug:clave>/publicar/", views.publicar, name="gwa_publicar"),
        path("web/<slug:clave>/vista-previa/", views.previa_sitio, name="gwa_previa_sitio"),
        path("web/<slug:clave>/volver/", views.volver, name="gwa_volver"),
        path("web/publicacion/<int:pk>/", views.despliegue_detalle, name="gwa_despliegue"),
        path("precios/", views.precios, name="gwa_precios"),
        path("sitio-activo/", views.elegir_sitio, name="gwa_elegir_sitio"),
    ]


@hooks.register("register_admin_menu_item")
def menu_estado():
    return MenuItem("Estado de las webs", reverse("gwa_estado"), icon_name="upload", order=100)


@hooks.register("register_admin_menu_item")
def menu_precios():
    return MenuItem("Actualizar precios", reverse("gwa_precios"), icon_name="tag", order=110)


@hooks.register("insert_global_admin_css")
def css():
    return format_html('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Titillium+Web:wght@400;600;700&display=swap">'
                       '<link rel="stylesheet" href="{}">', static("gwa/admin.css"))


def _sitios(user):
    ids = sitios_permitidos(user)
    qs = SitioWeb.objects.all()
    return qs if ids is None else qs.filter(pk__in=ids)


class PanelResumen(Component):
    name = "gwa_resumen"
    order = 10
    template_name = "publicacion/panel_resumen.html"

    def __init__(self, request):
        self.request = request

    def get_context_data(self, parent_context):
        user = self.request.user
        sitios = list(_sitios(user))
        hoy = timezone.localdate()
        from contenidos.models import Plan
        planes = Plan.objects.filter(sitio__in=sitios, live=True, visible=True).select_related("sitio")
        vencen = [p for p in planes if p.vigente_hasta and (p.vigente_hasta - hoy).days <= 30]
        return {"estados": [estado_sitio(s) for s in sitios], "vencen": vencen, "hoy": hoy,
                "pedidos": SolicitudDemo.objects.filter(sitio__in=sitios, estado="nuevo").count(),
                "activo": self.request.session.get("gwa_sitio", ""), "sitios": sitios}


@hooks.register("construct_homepage_panels")
def paneles(request, panels):
    panels.insert(0, PanelResumen(request))
