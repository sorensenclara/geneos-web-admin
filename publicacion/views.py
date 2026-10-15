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


CAMPOS_PRECIO = ("precio", "implementacion", "moneda", "mas_iva", "leyenda_vigencia", "vigente_hasta")


def _valores_form(post, p):
    hasta = post.get(f"vigente_hasta_{p.pk}", "").strip()
    return {"precio": post.get(f"precio_{p.pk}", p.precio).strip(),
            "implementacion": post.get(f"implementacion_{p.pk}", p.implementacion).strip(),
            "moneda": post.get(f"moneda_{p.pk}", p.moneda),
            "mas_iva": post.get(f"mas_iva_{p.pk}") == "on",
            "leyenda_vigencia": post.get(f"leyenda_vigencia_{p.pk}", p.leyenda_vigencia).strip(),
            "vigente_hasta": parse_date(hasta) if hasta else None}


def precios(request):
    """Actualización trimestral: todos los precios en una sola pantalla (fuente única de cada importe)."""
    from django.core.exceptions import ValidationError
    from contenidos.models import MONEDAS
    ids = sitios_permitidos(request.user, 1)
    planes = Plan.objects.select_related("sitio").order_by("sitio__orden", "orden")
    if ids is not None:
        planes = planes.filter(sitio_id__in=ids)
    if request.method == "POST":
        accion = request.POST.get("accion")
        cambiados, sin_permiso = [], []
        for p in planes:
            if not puede(request.user, p.sitio_id, p.linea_id):
                continue
            campos = _valores_form(request.POST, p)
            actual = p.get_latest_revision_as_object() if p.has_unpublished_changes else p
            if all(getattr(actual, k) == v for k, v in campos.items()):
                if not (accion == "aprobar" and p.has_unpublished_changes):
                    continue
                rev = p.latest_revision  # aprobar un borrador guardado antes, sin cambios nuevos
            else:
                for k, v in campos.items():
                    setattr(actual, k, v)
                try:
                    rev = actual.save_revision(user=request.user, log_action=True)
                except ValidationError as e:
                    errores = "; ".join(f"{m}" for msgs in e.message_dict.values() for m in msgs) if hasattr(e, "message_dict") else " ".join(e.messages)
                    messages.error(request, f"{p}: no se guardó. {errores}")
                    continue
            if accion == "aprobar":
                if puede(request.user, p.sitio_id, p.linea_id, nivel=2):
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
    return render(request, "publicacion/precios.html", {"filas": filas, "monedas": MONEDAS, "page_title": "Actualizar precios"})


@require_POST
def elegir_sitio(request):
    clave = request.POST.get("sitio", "")
    request.session["gwa_sitio"] = clave if SitioWeb.objects.filter(clave=clave).exists() else ""
    return redirect(request.POST.get("volver") or reverse("wagtailadmin_home"))


def _sin_acentos(texto):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def buscar(request):
    """Buscador del topbar: secciones del administrador, productos, planes, páginas y preguntas frecuentes.
    Cada grupo respeta los permisos del usuario (sitios permitidos y páginas que puede explorar)."""
    from django.http import JsonResponse
    from django.template import Context
    from wagtail.permission_policies.pages import PagePermissionPolicy
    from contenidos.models import PreguntaFrecuente
    from .templatetags.gwa_ui import gwa_menu

    q = request.GET.get("q", "").strip()
    grupos = []
    if len(q) >= 2:
        nq = _sin_acentos(q)
        ids = sitios_permitidos(request.user, 1)

        secciones = []
        for it in gwa_menu(Context({"request": request}))["principal"]:
            for x in [it] + it.get("children", []):
                if x["url"] and not x["url"].startswith(("#", "http")) and nq in _sin_acentos(x["label"]):
                    padre = it["label"] if x is not it else ""
                    secciones.append({"titulo": x["label"], "detalle": padre, "url": x["url"], "icono": x["icon"] if x is it else it["icon"]})
        grupos.append({"titulo": "Secciones", "items": secciones[:6]})

        sitios = SitioWeb.objects.all() if ids is None else SitioWeb.objects.filter(pk__in=ids)
        productos = [{"titulo": s.nombre, "detalle": s.marca["lema"] or "Estado de la web", "url": reverse("gwa_sitio", args=[s.clave]),
                      "imagen": s.marca["isologo_url"]} for s in sitios if nq in _sin_acentos(s.nombre)]
        grupos.append({"titulo": "Productos", "items": productos})

        planes = Plan.objects.select_related("sitio")
        if ids is not None:
            planes = planes.filter(sitio_id__in=ids)
        planes = [p for p in planes if nq in _sin_acentos(f"{p.nombre} {p.clave} {p.sitio.nombre}")][:6]
        grupos.append({"titulo": "Planes y precios", "items": [
            {"titulo": f"{p.sitio.nombre} {p.nombre}", "detalle": f"Abono {p.simbolo}{p.precio}" + (" + IVA" if p.mas_iva else ""),
             "url": reverse("wagtailsnippets_contenidos_plan:edit", args=[p.pk]), "imagen": p.sitio.marca["isologo_url"]} for p in planes]})

        paginas = PagePermissionPolicy().explorable_instances(request.user).filter(depth__gt=1, title__icontains=q).specific()[:8]
        grupos.append({"titulo": "Páginas", "items": [
            {"titulo": p.title, "detalle": p.get_parent().title if p.depth > 2 else "", "url": reverse("wagtailadmin_pages:edit", args=[p.pk]), "icono": "doc-empty"}
            for p in paginas]})

        faq = PreguntaFrecuente.objects.select_related("sitio").filter(pregunta__icontains=q)
        if ids is not None:
            faq = faq.filter(sitio_id__in=ids)
        grupos.append({"titulo": "Preguntas frecuentes", "items": [
            {"titulo": f.pregunta, "detalle": f.sitio.nombre, "url": reverse("wagtailsnippets_contenidos_preguntafrecuente:edit", args=[f.pk]), "icono": "help"}
            for f in faq[:6]]})

    if request.GET.get("formato") == "json":
        return JsonResponse({"q": q, "grupos": grupos})
    total = sum(len(g["items"]) for g in grupos)
    return render(request, "publicacion/buscar.html", {"q": q, "grupos": grupos, "total": total, "page_title": "Buscar"})
