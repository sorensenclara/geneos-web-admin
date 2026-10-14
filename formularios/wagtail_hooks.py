from wagtail.snippets.models import register_snippet

from contenidos.wagtail_hooks import PorSitio
from sitios.permisos import SitioPermissionPolicy

from .models import SolicitudDemo


class PedidosPolicy(SitioPermissionPolicy):
    """Los pedidos llegan solo desde las webs: no se crean desde el administrador."""

    def _nivel(self, action):
        return 99 if action == "add" else super()._nivel(action)


class PedidosViewSet(PorSitio):
    model = SolicitudDemo
    icon = "mail"
    menu_label = "Pedidos de demo"
    menu_order = 230
    add_to_admin_menu = True
    list_display = ["nombre", "producto", "plan", "estado", "creado"]
    list_filter = ["sitio", "estado", "producto"]
    inspect_view_enabled = True

    @property
    def permission_policy(self):
        return PedidosPolicy(SolicitudDemo)


register_snippet(PedidosViewSet)
