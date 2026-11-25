"""Descargas con dirección fija para las webs estáticas: /descargas/<sitio>/<ruta>/.

La web enlaza siempre a la misma dirección. Esta vista busca en Drive el PDF vigente (nombre exacto, el más reciente)
y redirige a su descarga pública. Si Comunicación sube un archivo nuevo con el mismo nombre, Drive le da otro ID y la
próxima consulta lo encuentra: no hay que cambiar enlaces ni volver a publicar la web.

Si Drive no responde, se usa el último archivo encontrado; si nunca se encontró, el documento subido al administrador.
"""
import hashlib
import logging

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.html import escape
from django.views.decorators.http import require_safe

from contenidos.models import Recurso

from . import drive

log = logging.getLogger(__name__)


def _redirigir(url, segundos):
    r = HttpResponseRedirect(url)
    r["Cache-Control"] = f"public, max-age={segundos}"
    r["X-Robots-Tag"] = "noindex"
    return r


def _sin_archivo(recurso):
    html = (f"<!doctype html><html lang=\"es-AR\"><meta charset=\"utf-8\"><title>{escape(recurso.titulo)}</title>"
            "<body style=\"font-family:system-ui;max-width:560px;margin:15vh auto;padding:0 20px;text-align:center\">"
            f"<h1>{escape(recurso.titulo)}</h1><p>El archivo no está disponible en este momento. Probá de nuevo en unos minutos.</p>"
            "<p><a href=\"javascript:history.back()\">Volver</a></p></body></html>")
    r = HttpResponse(html, status=503)
    r["Cache-Control"] = "no-store"
    r["Retry-After"] = "300"
    r["X-Robots-Tag"] = "noindex"
    return r


@require_safe
def descargar(request, sitio, clave):
    recurso = Recurso.objects.filter(sitio__clave=sitio, clave=clave, visible=True).select_related("documento").first()
    if recurso is None:
        raise Http404("No existe esa descarga.")
    segundos = settings.GWA_DRIVE_CACHE_SEGUNDOS
    if recurso.usa_drive:
        huella = hashlib.sha1(f"{recurso.carpeta_id}/{recurso.drive_nombre}".encode()).hexdigest()[:16]
        llave = f"gwa-descarga-{recurso.pk}-{huella}"  # cambia si se edita la carpeta o el nombre
        archivo_id = cache.get(llave)
        if archivo_id is None:
            try:
                f = drive.ultimo_pdf(recurso.carpeta_id, recurso.drive_nombre, settings.GWA_DRIVE_API_KEY)
                archivo_id = f["id"]
                cache.set(llave, archivo_id, segundos)
                Recurso.objects.filter(pk=recurso.pk).update(drive_archivo_id=archivo_id, drive_modificado=parse_datetime(f.get("modifiedTime") or ""),
                                                             drive_consultado=timezone.now())
            except drive.DriveError as e:
                log.warning("Descarga %s/%s: %s", sitio, clave, e)
                archivo_id = recurso.drive_archivo_id  # último archivo encontrado
                if archivo_id:
                    cache.set(llave, archivo_id, 60)  # se reintenta en un minuto
        if archivo_id:
            return _redirigir(drive.url_descarga(archivo_id), min(segundos, 300))
    if recurso.documento_id:
        return _redirigir(request.build_absolute_uri(recurso.documento.url), 300)
    return _sin_archivo(recurso)
