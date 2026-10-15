from wagtail import hooks
from wagtail.signals import published
from wagtail.snippets.models import register_snippet

from contenidos.wagtail_hooks import PorSitio

from .contexto import fijar_linea
from .models import ConfigBlog


class ConfigBlogViewSet(PorSitio):
    """Configuración del blog de cada sitio. Se abre desde «Blog y noticias → Configurar blog» (no tiene ítem propio en el menú)."""
    model = ConfigBlog
    icon = "cog"
    menu_label = "Configuración de blogs"
    menu_item_is_registered = True
    list_display = ["__str__", "activo", "nombre_menu", "ruta", "live"]

    def get_queryset(self, request):
        return self.permission_policy.instances_user_has_any_permission_for(request.user, ["view", "change"])


register_snippet(ConfigBlogViewSet)


@hooks.register("before_create_page")
def linea_del_blog(request, parent_page, page_class):
    """«Nuevo artículo» desde el blog de GEAGRO con una línea elegida: el formulario la trae marcada."""
    if page_class.__name__ == "ArticuloPage":
        lid = request.session.pop("gwa_linea_nueva", "") if request.method == "GET" else ""
        fijar_linea(int(lid) if str(lid).isdigit() else None)


def _config_publicada(sender, instance, **kwargs):
    """Al aprobar la configuración, el blog general toma la dirección elegida (/blog/ o /noticias/)."""
    if not isinstance(instance, ConfigBlog):
        return
    from .ideas import blog_general
    idx = blog_general(instance.sitio, crear=False)
    ruta = instance.ruta.strip("/") + "/"
    if idx is not None and idx.ruta_publica != ruta:
        idx.ruta_publica = ruta
        idx.save(update_fields=["ruta_publica"])
        from contenidos.models import ArticuloPage
        for a in ArticuloPage.objects.child_of(idx):
            a.save()  # recalcula la dirección (y deja la redirección 301 si ya estaba aprobado)


published.connect(_config_publicada)
