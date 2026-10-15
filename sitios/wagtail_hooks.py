from django.db.models import Q
from wagtail.permission_policies.base import BasePermissionPolicy
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

from .columnas import columna_sitio
from .models import AccesoSitio, LineaProducto, SitioWeb
from .permisos import ProtegerObjetos, accesos


class SitioWebPolicy(BasePermissionPolicy):
    """Configuración de un sitio: la ven sus integrantes y la cambian sus administradores."""

    def user_has_permission(self, user, action):
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if action in ("add", "delete"):
            return False
        return any(n >= (1 if action == "view" else 3) for _s, _l, n in accesos(user))

    def user_has_permission_for_instance(self, user, action, instance):
        if user.is_superuser:
            return True
        if action in ("add", "delete"):
            return False
        return any(s == instance.pk and n >= (1 if action == "view" else 3) for s, _l, n in accesos(user))

    def instances_user_has_any_permission_for(self, user, actions):
        if user.is_superuser:
            return SitioWeb.objects.all()
        return SitioWeb.objects.filter(pk__in={s for s, _l, _n in accesos(user)})

    def users_with_any_permission(self, actions):
        from django.contrib.auth import get_user_model
        return get_user_model().objects.filter(Q(is_superuser=True) | Q(groups__accesos_sitio__isnull=False)).distinct()


class SoloAdmin(BasePermissionPolicy):
    def user_has_permission(self, user, action):
        return user.is_authenticated and user.is_superuser

    def users_with_any_permission(self, actions):
        from django.contrib.auth import get_user_model
        return get_user_model().objects.filter(is_superuser=True)


class SitioWebViewSet(ProtegerObjetos, SnippetViewSet):
    model = SitioWeb
    icon = "site"
    menu_label = "Sitios y contacto"
    list_display = ["nombre", "dominio", "dominio_confirmado", "whatsapp_visible", "email_pedidos"]

    @property
    def permission_policy(self):
        return SitioWebPolicy(SitioWeb)


class LineaViewSet(SnippetViewSet):
    model = LineaProducto
    icon = "list-ul"
    menu_label = "Líneas de producto"
    list_display = ["nombre", columna_sitio(), "ruta"]

    @property
    def permission_policy(self):
        return SoloAdmin(LineaProducto)


class AccesoViewSet(SnippetViewSet):
    model = AccesoSitio
    icon = "key"
    menu_label = "Accesos por sitio"
    list_display = ["grupo", columna_sitio(), "linea", "rol"]
    list_filter = ["sitio", "rol"]

    @property
    def permission_policy(self):
        return SoloAdmin(AccesoSitio)


class ConfiguracionGroup(SnippetViewSetGroup):
    menu_label = "Sitios y accesos"
    menu_icon = "network"
    menu_order = 900
    items = (SitioWebViewSet, LineaViewSet, AccesoViewSet)


register_snippet(ConfiguracionGroup)
