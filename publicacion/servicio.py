"""Circuito de publicación: vista previa, publicación en la web, vuelta atrás y estado de cada sitio.

«Aprobado» = publicado dentro del administrador (versión vigente de Wagtail).
«En la web» = la última publicación que terminó bien. Lo aprobado después de esa fecha figura como pendiente.
"""
import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from contenidos.models import (ArticuloPage, BlogIndexPage, CategoriaBlog, Funcionalidad, IdentidadSitio, PaginaWeb, Plan, PreguntaFrecuente, Recurso,
                               Redireccion, Sector, Testimonio, sitio_de_pagina)
from sitios.models import SitioWeb

from . import despliegue
from .models import Despliegue
from .motor import ErrorGeneracion, NoConectado, generar, validar

PREVIEWS = Path(settings.GWA_VAR_DIR) / "vistas-previas"


def sitio_de(obj):
    if isinstance(obj, SitioWeb):
        return obj
    if hasattr(obj, "sitio_id") and obj.sitio_id:
        return obj.sitio
    if hasattr(obj, "get_site"):
        if obj.pk is None and getattr(obj, "_parent_page", None):  # página nueva en vista previa
            return sitio_de_pagina(obj._parent_page)
        try:
            return sitio_de_pagina(obj)
        except Exception:
            return None
    return None


def _limpiar_previas():
    if not PREVIEWS.exists():
        return
    limite = time.time() - 3600
    for d in PREVIEWS.iterdir():
        if d.is_dir() and d.stat().st_mtime < limite:
            shutil.rmtree(d, ignore_errors=True)


def ruta_de(obj, modo):
    if isinstance(obj, Plan):
        return obj.ruta if modo == "landing" and obj.ruta else ""
    if isinstance(obj, PreguntaFrecuente):
        return obj.ubicacion
    if isinstance(obj, ArticuloPage):
        try:
            return obj.ruta
        except Exception:
            return ""
    return getattr(obj, "ruta_publica", "") or ""


def _pagina_html(carpeta_web, ruta, token, carpeta_nombre):
    f = carpeta_web / ruta / "index.html"
    if not f.exists():
        f, ruta = carpeta_web / "index.html", ""
    html = f.read_text()
    base = reverse("gwa_archivo_previa", args=[f"{token}/{carpeta_nombre}/{ruta}"])
    return re.sub(r"<head>", f'<head><base href="{base}">', html, count=1)


def vista_previa_objeto(request, obj, modo=""):
    """Vista previa de una página o un dato con su borrador, en la web real generada con las plantillas actuales."""
    sitio = sitio_de(obj)
    if sitio is None:
        return HttpResponse("No se pudo identificar el sitio de este contenido.", status=400)
    if sitio.motor != "comercial":
        return HttpResponse(render_to_string("publicacion/previa_institucional.html", {"obj": obj, "sitio": sitio}))
    _limpiar_previas()
    token = uuid.uuid4().hex[:16]
    destino = PREVIEWS / token
    try:
        carpeta, _datos, _reg = generar(sitio, destino, overrides=[obj])
    except (ErrorGeneracion, NoConectado) as e:
        return HttpResponse(render_to_string("publicacion/previa_error.html", {"error": str(e), "sitio": sitio}), status=500)
    return HttpResponse(_pagina_html(carpeta, ruta_de(obj, modo), token, carpeta.name))


def vista_previa_sitio(sitio):
    """Genera la web completa con todo lo aprobado (todavía sin publicar). Devuelve la URL para verla."""
    _limpiar_previas()
    token = uuid.uuid4().hex[:16]
    carpeta, datos, _reg = generar(sitio, PREVIEWS / token)
    errores = validar(sitio, carpeta, datos)
    return reverse("gwa_archivo_previa", args=[f"{token}/{carpeta.name}/"]), errores


def publicar_sitio(sitio, usuario=None, motivo="Publicación manual"):
    """Genera, valida y publica. Si algo falla, la versión pública anterior queda como estaba."""
    d = Despliegue.objects.create(sitio=sitio, usuario=usuario if usuario and usuario.is_authenticated else None, motivo=motivo[:200])
    nombre = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = despliegue.nueva_carpeta(sitio, nombre)
    registro = []
    try:
        carpeta, datos, reg = generar(sitio, destino)
        registro.append(reg)
        errores = validar(sitio, carpeta, datos)
        if errores:
            raise ErrorGeneracion("La web generada no pasó los controles:\n- " + "\n- ".join(errores))
        if sitio.destino == "comando" and sitio.comando_despliegue.strip():
            registro.append(despliegue.ejecutar_comando(sitio, carpeta))
        despliegue.activar(sitio, carpeta)
        despliegue.limpiar(sitio)
        d.estado, d.version, d.carpeta = "ok", nombre, str(carpeta)
    except Exception as e:  # noqa: BLE001 — cualquier error deja la versión anterior intacta
        d.estado = "fallo"
        registro.append(str(e))
        shutil.rmtree(destino, ignore_errors=True)
    d.registro = "\n".join(x for x in registro if x)
    d.finalizado = timezone.now()
    d.save()
    return d


def volver_atras(sitio, usuario=None):
    """Vuelve a la versión publicada anterior a la actual (solo destino carpeta)."""
    actual = despliegue.version_actual(sitio)
    previas = [v for v in despliegue.versiones(sitio) if v.name != actual and (actual is None or v.name < actual)]
    d = Despliegue.objects.create(sitio=sitio, tipo="vuelta_atras", usuario=usuario, motivo="Volver a la versión anterior")
    if not previas:
        d.estado, d.registro = "fallo", "No hay una versión anterior guardada."
    else:
        carpeta = next(previas[0].iterdir())
        despliegue.activar(sitio, carpeta)
        if sitio.destino == "comando" and sitio.comando_despliegue.strip():
            try:
                d.registro = despliegue.ejecutar_comando(sitio, carpeta)
            except Exception as e:  # noqa: BLE001
                d.estado, d.registro = "fallo", str(e)
        if d.estado != "fallo":
            d.estado, d.version, d.carpeta = "ok", previas[0].name, str(carpeta)
    d.finalizado = timezone.now()
    d.save()
    return d


# ------------------------------------------------------------------------------------------------ Estado de cada web
def _paginas_sitio(sitio):
    if not sitio.site:
        return []
    res = []
    for model in (PaginaWeb, BlogIndexPage, ArticuloPage):
        res += list(model.objects.descendant_of(sitio.site.root_page, inclusive=True))
    return res


def estado_sitio(sitio):
    ultimo_ok = sitio.despliegues.filter(estado="ok").exclude(tipo="vista_previa").first()
    ultimo = sitio.despliegues.exclude(tipo="vista_previa").first()
    desde = ultimo_ok.finalizado if ultimo_ok else timezone.make_aware(datetime(2000, 1, 1))
    pendientes, borradores, revision = [], 0, 0
    for p in _paginas_sitio(sitio):
        if p.live and p.last_published_at and p.last_published_at > desde:
            pendientes.append(("Página", p.title, p.last_published_at, reverse("wagtailadmin_pages:edit", args=[p.pk])))
        if p.has_unpublished_changes:
            borradores += 1
        if p.workflow_in_progress:
            revision += 1
    for model, tipo in ((Plan, "Plan"), (Funcionalidad, "Funcionalidad"), (Sector, "Sector"), (PreguntaFrecuente, "Pregunta frecuente"), (Testimonio, "Testimonio"), (IdentidadSitio, "Logos y favicon")):
        for o in model.objects.filter(sitio=sitio):
            if o.live and o.last_published_at and o.last_published_at > desde:
                pendientes.append((tipo, str(o), o.last_published_at, _url_snippet(o)))
            if o.has_unpublished_changes:
                borradores += 1
            if o.workflow_in_progress:
                revision += 1
    for model, tipo in ((Redireccion, "Redirección"), (CategoriaBlog, "Categoría"), (Recurso, "Recurso")):
        for o in model.objects.filter(sitio=sitio, actualizado__gt=desde):
            pendientes.append((tipo, str(o), o.actualizado, _url_snippet(o)))
    if sitio.actualizado > desde:
        pendientes.append(("Configuración", "Datos de contacto y opciones del sitio", sitio.actualizado, _url_snippet(sitio)))
    pendientes.sort(key=lambda x: x[2], reverse=True)
    error = ultimo if ultimo and ultimo.estado == "fallo" and (not ultimo_ok or ultimo.iniciado > ultimo_ok.iniciado) else None
    if sitio.motor != "comercial":
        situacion = "no_conectado"
    elif error:
        situacion = "error"
    elif not ultimo_ok:
        situacion = "sin_publicar"
    elif pendientes:
        situacion = "pendiente"
    else:
        situacion = "al_dia"
    return {"sitio": sitio, "ultimo_ok": ultimo_ok, "error": error, "pendientes": pendientes, "borradores": borradores,
            "revision": revision, "situacion": situacion, "version_local": despliegue.version_actual(sitio)}


def _url_snippet(o):
    from wagtail.admin.admin_url_finder import AdminURLFinder
    return AdminURLFinder().get_edit_url(o) or "#"
