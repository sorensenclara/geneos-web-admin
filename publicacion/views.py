from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from django.views.static import serve

from contenidos.models import Plan
from sitios.models import SitioWeb
from sitios.permisos import puede, sitios_permitidos

from . import despliegue
from .models import Despliegue
from .motor import ErrorGeneracion, NoConectado
from .servicio import PREVIEWS, estado_sitio, publicar_sitio, vista_previa_sitio, volver_atras


def _staff(request):
    if not (request.user.is_authenticated and request.user.has_perm("wagtailadmin.access_admin")):
        raise PermissionDenied


def archivo_previa(request, ruta):
    """Archivos de las vistas previas: solo para usuarios del administrador."""
    _staff(request)
    if ruta.endswith("/") or ruta == "":
        ruta += "index.html"
    return serve(request, ruta, document_root=PREVIEWS)


def archivo_publico(request, clave, ruta=""):
    """Web publicada localmente (destino «carpeta»), para revisarla en http://localhost:8000/web-local/<sitio>/."""
    _staff(request)
    carpeta = despliegue.raiz(get_object_or_404(SitioWeb, clave=clave)) / "actual"
    if not carpeta.exists():
        raise Http404("Este sitio todavía no se publicó.")
    if ruta.endswith("/") or ruta == "":
        ruta += "index.html"
    return serve(request, ruta, document_root=carpeta.resolve())


def _sitios_usuario(user, nivel=1):
    ids = sitios_permitidos(user, nivel)
    qs = SitioWeb.objects.all()
    return qs if ids is None else qs.filter(pk__in=ids)


def estado(request):
    estados = [estado_sitio(s) for s in _sitios_usuario(request.user)]
    return render(request, "publicacion/estado.html", {"estados": estados, "page_title": "Estado de las webs"})


def sitio_detalle(request, clave):
    sitio = get_object_or_404(SitioWeb, clave=clave)
    if not puede(request.user, sitio.pk):
        raise PermissionDenied
    return render(request, "publicacion/sitio.html", {"e": estado_sitio(sitio), "despliegues": sitio.despliegues.all()[:20],
                                                      "versiones": [v.name for v in despliegue.versiones(sitio)],
                                                      "puede_publicar": puede(request.user, sitio.pk, nivel=2), "page_title": sitio.nombre})


@require_POST
def publicar(request, clave):
    sitio = get_object_or_404(SitioWeb, clave=clave)
    if not puede(request.user, sitio.pk, nivel=2):
        raise PermissionDenied
    d = publicar_sitio(sitio, request.user, request.POST.get("motivo") or "Publicación manual")
    if d.estado == "ok":
        messages.success(request, f"La web de {sitio.nombre} se actualizó (versión {d.version}).")
    else:
        messages.error(request, f"No se publicó: la web de {sitio.nombre} sigue con la versión anterior. Revisá el detalle del error.")
    return redirect("gwa_sitio", clave=clave)


@require_POST
def previa_sitio(request, clave):
    sitio = get_object_or_404(SitioWeb, clave=clave)
    if not puede(request.user, sitio.pk):
        raise PermissionDenied
    try:
        url, errores = vista_previa_sitio(sitio)
    except (ErrorGeneracion, NoConectado) as e:
        messages.error(request, str(e))
        return redirect("gwa_sitio", clave=clave)
    for e in errores:
        messages.warning(request, e)
    return redirect(url)


@require_POST
def volver(request, clave):
    sitio = get_object_or_404(SitioWeb, clave=clave)
    if not puede(request.user, sitio.pk, nivel=2):
        raise PermissionDenied
    d = volver_atras(sitio, request.user)
    (messages.success if d.estado == "ok" else messages.error)(request, "Se volvió a la versión anterior." if d.estado == "ok" else d.registro)
    return redirect("gwa_sitio", clave=clave)


def despliegue_detalle(request, pk):
    d = get_object_or_404(Despliegue, pk=pk)
    if not puede(request.user, d.sitio_id):
        raise PermissionDenied
    return render(request, "publicacion/despliegue.html", {"d": d, "page_title": "Detalle de la publicación"})


def precios(request):
    """Actualización trimestral: todos los precios en una sola pantalla."""
    ids = sitios_permitidos(request.user, 1)
    planes = Plan.objects.select_related("sitio").order_by("sitio__orden", "orden")
    if ids is not None:
        planes = planes.filter(sitio_id__in=ids)
    if request.method == "POST":
        accion = request.POST.get("accion")
        cambiados, sin_permiso = [], []
        for p in planes:
            campos = {"precio": request.POST.get(f"precio_{p.pk}", p.precio).strip(), "implementacion": request.POST.get(f"impl_{p.pk}", p.implementacion).strip()}
            hasta = request.POST.get(f"hasta_{p.pk}", "").strip()
            campos["vigente_hasta"] = parse_date(hasta) if hasta else None
            actual = p.get_latest_revision_as_object() if p.has_unpublished_changes else p
            antes = (actual.precio, actual.implementacion, str(actual.vigente_hasta or ""))
            if antes == (campos["precio"], campos["implementacion"], hasta):
                if not (accion == "aprobar" and p.has_unpublished_changes):
                    continue
                rev = p.latest_revision  # aprobar un borrador guardado antes, sin cambios nuevos
            else:
                for k, v in campos.items():
                    setattr(actual, k, v)
                rev = actual.save_revision(user=request.user, log_action=True)
            if accion == "aprobar":
                if puede(request.user, p.sitio_id, nivel=2):
                    rev.publish(user=request.user)
                else:
                    sin_permiso.append(str(p))
            cambiados.append(p)
        if cambiados:
            msg = f"{len(cambiados)} plan(es) actualizado(s) " + ("y aprobados." if accion == "aprobar" else "como borrador.")
            messages.success(request, msg + " Revisá la vista previa y publicá cada web desde «Estado de las webs».")
        else:
            messages.info(request, "No hubo cambios de precio.")
        for s in sin_permiso:
            messages.warning(request, f"{s}: quedó como borrador porque no tenés permiso para aprobar en ese sitio.")
        return redirect("gwa_precios")
    filas = []
    for p in planes:
        borrador = p.get_latest_revision_as_object() if p.has_unpublished_changes else None
        filas.append({"p": p, "b": borrador, "v": borrador or p})
    return render(request, "publicacion/precios.html", {"filas": filas, "page_title": "Actualizar precios"})


@require_POST
def elegir_sitio(request):
    clave = request.POST.get("sitio", "")
    request.session["gwa_sitio"] = clave if SitioWeb.objects.filter(clave=clave).exists() else ""
    return redirect(request.POST.get("volver") or reverse("wagtailadmin_home"))
