"""Esqueleto del administrador (sidebar y topbar de GENEOS UI) armado con el menú de Wagtail.

Se usan los mismos ítems, permisos y hooks que el sidebar original de Wagtail
(admin_menu.render_component aplica is_shown y construct_main_menu)."""
from django import template
from django.urls import reverse
from wagtail.admin.menu import admin_menu
from wagtail.admin.ui import sidebar as wsidebar

register = template.Library()


def _activo(url, ruta):
    if not url or url.startswith(("#", "http")):
        return 0
    if url == reverse("wagtailadmin_home"):
        return len(url) if ruta == url else 0
    return len(url) if ruta.startswith(url) else 0


def _item(comp, ruta):
    d = {"name": comp.name, "label": comp.label, "icon": comp.icon_name or "doc-empty", "attrs": comp.attrs or {}}
    if isinstance(comp, wsidebar.SubMenuItem):
        d["children"] = [_item(c, ruta) for c in comp.menu_items]
        d["url"] = ""
    else:
        d["url"] = getattr(comp, "url", "") or ""
        d["externo"] = d["url"].startswith("http")
    d["peso"] = _activo(d["url"], ruta)
    return d


def _marcar(items, mejor):
    for it in items:
        it["active"] = bool(mejor) and it["peso"] == mejor and not it.get("children")
        if it.get("children"):
            _marcar(it["children"], mejor)
            it["has_active"] = any(c["active"] for c in it["children"])


def _ruta_de_menu(ruta):
    """Los artículos se editan con el editor de páginas de Wagtail, pero en el menú pertenecen a «Blog y noticias»."""
    import re
    m = re.match(r"^/admin/pages/(\d+)/", ruta)
    es_articulo = ruta.startswith("/admin/pages/add/contenidos/articulopage/")
    if m and not es_articulo:
        from wagtail.models import Page
        es_articulo = Page.objects.filter(pk=m.group(1), content_type__model="articulopage").exists()
    return reverse("blog:index") if es_articulo else ruta


@register.simple_tag(takes_context=True)
def gwa_menu(context):
    """Menú principal y menú de ayuda, con el ítem activo marcado (la coincidencia de URL más larga)."""
    request = context["request"]
    ruta = _ruta_de_menu(request.path)
    items = [_item(c, ruta) for c in admin_menu.render_component(request)]
    inicio = {"name": "inicio", "label": "Inicio", "icon": "home", "url": reverse("wagtailadmin_home"), "attrs": {}}
    inicio["peso"] = _activo(inicio["url"], ruta)
    items.insert(0, inicio)
    pesos = [it["peso"] for it in items] + [c["peso"] for it in items for c in it.get("children", [])]
    _marcar(items, max(pesos or [0]))
    ayuda = [it for it in items if it["name"] == "help"]
    return {"principal": [it for it in items if it["name"] != "help"], "ayuda": ayuda[0] if ayuda else None}


@register.filter
def gwa_iniciales(user):
    nombre = (user.get_full_name() or user.get_username() or "?").split()
    if len(nombre) > 1:
        return (nombre[0][0] + nombre[-1][0]).upper()
    return nombre[0][:2].upper()


@register.filter
def gwa_rol(user):
    if user.is_superuser:
        return "Administrador"
    grupos = list(user.groups.values_list("name", flat=True)[:1])
    return grupos[0] if grupos else "Usuario"


@register.filter
def gwa_attrs(attrs):
    from django.forms.utils import flatatt
    return flatatt({k: v for k, v in (attrs or {}).items() if k not in ("class", "href")})
