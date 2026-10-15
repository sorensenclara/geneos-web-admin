"""«Oferta comercial → Sectores»: listado del snippet Sector (contenidos/wagtail_hooks.py).

Muestra cada sector con su producto (isologo oficial), línea, estado editorial y si está efectivamente en la web.
La edición es la de Wagtail (pestañas Contenido web, Información interna y Configuración), con borrador,
aprobación e historial. La web solo recibe título, texto e ícono de las tarjetas que ya existen (GERP y GEMA)."""
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.urls import reverse

from contenidos.models import Sector
from contenidos.sectores import SECCION_WEB, seccion_web
from sitios.models import LineaProducto, SitioWeb
from sitios.permisos import SitioPermissionPolicy, puede, sitios_permitidos


def _en_la_web(f, v, ultimo_ok):
    """Situación del sector en la web publicada: (clave, texto)."""
    if f.sitio.clave not in SECCION_WEB:
        return "interno", "Solo interno"
    if not f.live:
        return "no_publicado", "No publicado"
    if not (f.visible and f.mostrar_tarjeta):
        return "oculto", "Oculto"
    if ultimo_ok and (f.last_published_at is None or f.last_published_at <= ultimo_ok.finalizado):
        return "en_web", "En la web"
    return "falta", "Aprobado, falta publicar"


def sectores(request):
    politica = SitioPermissionPolicy(Sector)
    if not politica.user_has_any_permission(request.user, ["view", "change"]):
        raise PermissionDenied
    ids = sitios_permitidos(request.user)
    sitios = [s for s in SitioWeb.objects.filter(motor="comercial").order_by("orden") if ids is None or s.pk in ids]
    if not sitios:
        raise PermissionDenied
    visibles = (politica.instances_user_has_any_permission_for(request.user, ["view", "change"])
                .filter(sitio__in=sitios).select_related("sitio", "linea", "latest_revision__user", "locked_by")
                .prefetch_related("funcionalidades"))
    ultimos = {s.pk: s.despliegues.filter(estado="ok").exclude(tipo="vista_previa").first() for s in sitios}
    filas = []
    for f in visibles:
        v = f.get_latest_revision_as_object() if f.has_unpublished_changes and f.latest_revision_id else f
        web, web_texto = _en_la_web(f, v, ultimos.get(f.sitio_id))
        if f.workflow_in_progress:
            estado, estado_texto = "revision", "En revisión"
        elif f.has_unpublished_changes:
            estado, estado_texto = "borrador", "Borrador"
        elif f.live:
            estado, estado_texto = "aprobado", "Aprobado"
        else:
            estado, estado_texto = "sin_aprobar", "Sin aprobar"
        filas.append({"f": f, "v": v, "marca": f.sitio.marca, "web": web, "web_texto": web_texto, "estado": estado, "estado_texto": estado_texto,
                      "funcs": f.funcionalidades.count(), "editable": puede(request.user, f.sitio_id, f.linea_id),
                      "previa": reverse("wagtailsnippets_contenidos_sector:revisions_view", args=[f.pk, f.latest_revision_id]) if f.latest_revision_id else ""})
    orden_sitio = {s.pk: i for i, s in enumerate(sitios)}
    filas.sort(key=lambda r: (orden_sitio.get(r["f"].sitio_id, 99), r["v"].orden, r["f"].pk))
    productos = [{"sitio": s, "marca": s.marca, "n": sum(1 for r in filas if r["f"].sitio_id == s.pk), "seccion": seccion_web(s),
                  "con_seccion": s.clave in SECCION_WEB} for s in sitios]
    activo = request.GET.get("sitio") or ""
    return render(request, "publicacion/sectores.html", {
        "page_title": "Sectores", "filas": filas, "productos": productos, "activo": activo,
        "lineas": LineaProducto.objects.filter(sitio__in=sitios).select_related("sitio").order_by("sitio__orden", "orden"),
        "puede_agregar": politica.user_has_permission(request.user, "add"),
    })
