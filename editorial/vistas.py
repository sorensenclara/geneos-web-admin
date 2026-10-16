"""«Contenidos → Blog y noticias»: un solo administrador para los blogs de GENEOS, GERP, GEAGRO y GEMA.

Arriba se elige el sitio (queda guardado en la sesión, igual que «Trabajar en», y lo usan Categorías y Autores).
Debajo: encabezado del blog con su estado, «Actualidad e ideas para publicar» y «Mis artículos».
Los artículos son páginas de Wagtail: edición, vista previa, historial, aprobación y permisos son los del editor de páginas.
"""
from datetime import date

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from datetime import timedelta

from django.db.models import Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from contenidos.models import ArticuloPage, CategoriaBlog
from sitios.models import LineaProducto, SitioWeb
from sitios.permisos import puede, sitios_permitidos

from . import ia
from .estado import estado_blog, estado_editorial, estado_web, ultimo_despliegue
from .ideas import ErrorImportacion, actualizar_ideas, blog_general, crear_borrador, importar_trends, url_trends
from .models import TIPOS_FUENTE, ConfigBlog, IdeaEditorial, ImportacionTendencias, config_actual

DESCRIPCION = {"geneos": "Cooperativismo, software libre y tecnología", "gerp": "Gestión empresarial y administración",
               "geagro": "Agricultura, cereales y viñedos", "gema": "Talleres de matafuegos y seguridad"}
ICONO_LINEA = {"cereales": "wheat", "vid": "grape"}


def _sitios(user):
    ids = sitios_permitidos(user)
    return [s for s in SitioWeb.objects.order_by("orden") if ids is None or s.pk in ids]


def _sitio(request, sitios, clave=None):
    clave = clave or request.GET.get("sitio") or request.session.get("gwa_blog_sitio") or request.session.get("gwa_sitio") or ""
    sitio = next((s for s in sitios if s.clave == clave), None) or (sitios[0] if sitios else None)
    if sitio is None:
        raise PermissionDenied
    if request.session.get("gwa_blog_sitio") != sitio.clave:
        request.session["gwa_blog_sitio"] = sitio.clave
    if request.session.get("gwa_sitio"):  # «Trabajar en» activo: acompaña la elección para Categorías y Autores
        request.session["gwa_sitio"] = sitio.clave
    return sitio


def _version(a):
    return a.get_latest_revision_as_object() if a.has_unpublished_changes and a.latest_revision_id else a


def _miniatura(img):
    if img is None:
        return ""
    try:
        return img.get_rendition("fill-112x76").url
    except Exception:  # noqa: BLE001 — archivo faltante: sin miniatura
        return ""


def _filas(sitio, user, f, blog_clave, ultimo):
    if not sitio.site:
        return []
    qs = (ArticuloPage.objects.descendant_of(sitio.site.root_page).select_related("latest_revision", "locked_by")
          .order_by("-fecha", "-latest_revision_created_at"))
    filas = []
    for a in qs:
        v = _version(a)
        ec, et = estado_editorial(a)
        wc, wt = estado_web(a, blog_clave, ultimo)
        lineas = list(v.lineas.all())
        cats = list(v.categorias.all())
        fila = {"a": a, "v": v, "ec": ec, "et": et, "wc": wc, "wt": wt, "lineas": lineas, "cats": cats, "autor": v.autor,
                "thumb": _miniatura(v.imagen), "ruta": "/" + (a.ruta_publica or ""),
                "editar": reverse("wagtailadmin_pages:edit", args=[a.pk]),
                "previa": reverse("wagtailadmin_pages:view_draft", args=[a.pk]),
                "duplicar": reverse("wagtailadmin_pages:copy", args=[a.pk]),
                "historial": reverse("wagtailadmin_pages:history", args=[a.pk]),
                "puede": puede(user, sitio.pk, lineas[0].pk if len(lineas) == 1 else None)}
        if f["q"] and f["q"].lower() not in v.title.lower():
            continue
        if f["categoria"] and not any(str(c.pk) == f["categoria"] for c in cats):
            continue
        if f["linea"] and not any(str(l.pk) == f["linea"] for l in lineas):
            continue
        if f["estado"] and ec != f["estado"] and not (f["estado"] == "aprobado" and ec == "cambios"):
            continue
        if f["web"] and wc != f["web"]:
            continue
        filas.append(fila)
    return filas


ORDEN_TIPO = {"noticia": 0, "evento": 1, "tendencia": 2, "idea": 3}
PERIODOS = [("7", "Últimos 7 días"), ("30", "Últimos 30 días")]
CONTENIDOS = [("", "Todo"), ("noticia", "Noticias"), ("evento", "Eventos"), ("tendencia", "Tendencias de búsqueda"), ("idea", "Ideas editoriales")]


def _filtros_actualidad(request):
    f = {"periodo": request.GET.get("periodo") if request.GET.get("periodo") in ("7", "30") else "7",
         "contenido": request.GET.get("contenido") if request.GET.get("contenido") in dict(CONTENIDOS) else "",
         "fuente": request.GET.get("fuente") if request.GET.get("fuente") in dict(TIPOS_FUENTE) else ""}
    return f


def _ideas(sitio, linea_id, f=None, descartadas=False):
    """Actualidad e ideas del sitio. Noticias, eventos y tendencias: solo del período elegido (por fecha original);
    las ideas editoriales y lo guardado se mantienen hasta usarlas o descartarlas."""
    f = f or {"periodo": "7", "contenido": "", "fuente": ""}
    estados = ("descartada",) if descartadas else ("sugerida", "guardada")
    qs = IdeaEditorial.objects.filter(sitio=sitio, estado__in=estados).select_related("linea")
    if linea_id:
        qs = qs.filter(Q(linea_id=linea_id) | Q(linea__isnull=True))
    if f["contenido"]:
        qs = qs.filter(tipo=f["contenido"])
    if f["fuente"]:
        qs = qs.filter(fuente_tipo=f["fuente"])
    desde = timezone.localdate() - timedelta(days=int(f["periodo"]))
    res = []
    for i in qs:
        if i.tipo != "idea" and i.estado != "guardada" and i.fecha < desde:
            continue  # noticia vieja: fuera del período
        if i.tipo == "evento" and i.evento_fecha and i.evento_fecha < timezone.localdate():
            continue  # evento que ya pasó
        res.append(i)
    return sorted(res, key=lambda i: (i.estado != "guardada", ORDEN_TIPO.get(i.tipo, 9), -i.fecha.toordinal(), -i.pk))


def _ctx_actualidad(sitio, linea, f, ideas, limite=None):
    ult_idea = IdeaEditorial.objects.filter(sitio=sitio).aggregate(m=Max("creada"))["m"]
    ult_imp = ImportacionTendencias.objects.filter(sitio=sitio).first()
    fechas = [d for d in (ult_idea, ult_imp.creado if ult_imp else None) if d]
    return {"ideas": ideas[:limite] if limite else ideas, "ideas_total": len(ideas), "ideas_mas": max(0, len(ideas) - limite) if limite else 0,
            "fa": f, "periodos": PERIODOS, "contenidos": CONTENIDOS, "fuentes_tipo": TIPOS_FUENTE,
            "ultima_actualizacion": max(fechas) if fechas else None, "ult_imp": ult_imp, "ia": ia.estado(),
            "trends_url": url_trends((linea.nombre if linea else "") or sitio.nombre)}


def blog(request, clave=None):
    sitios = _sitios(request.user)
    if not sitios:
        raise PermissionDenied
    sitio = _sitio(request, sitios, clave)
    lineas = list(LineaProducto.objects.filter(sitio=sitio).order_by("orden"))
    linea_id = request.GET.get("linea", "")
    linea = next((l for l in lineas if str(l.pk) == linea_id), None)
    f = {k: request.GET.get(k, "").strip() for k in ("q", "categoria", "estado", "web")}
    f["linea"] = str(linea.pk) if linea else ""
    ultimo = ultimo_despliegue(sitio)
    bc, bt, bd = estado_blog(sitio, ultimo)
    config = config_actual(sitio)
    filas = _filas(sitio, request.user, f, bc, ultimo)
    total = len(_filas(sitio, request.user, {"q": "", "categoria": "", "linea": "", "estado": "", "web": ""}, bc, ultimo)) if any(f.values()) else len(filas)
    pag = Paginator(filas, 10).get_page(request.GET.get("p") or 1)
    fa = _filtros_actualidad(request)
    ideas = _ideas(sitio, linea.pk if linea else None, fa)
    productos = [{"s": s, "marca": s.marca, "desc": DESCRIPCION.get(s.clave, ""), "actual": s.pk == sitio.pk} for s in sitios]
    ctx = {
        "page_title": "Blog y noticias", "productos": productos, "sitio": sitio, "marca": sitio.marca, "config": config,
        "blog_estado": (bc, bt, bd), "lineas": lineas, "linea": linea, "f": f, "pag": pag, "total": total,
        "categorias": CategoriaBlog.objects.filter(sitio=sitio).order_by("nombre"),
        **_ctx_actualidad(sitio, linea, fa, ideas, limite=6), "icono_linea": ICONO_LINEA,
        "puede_editar": puede(request.user, sitio.pk) or any(puede(request.user, sitio.pk, l.pk) for l in lineas),
        "puede_configurar": puede(request.user, sitio.pk),
        "titulo_blog": (config.titulo if config else f"Blog de {sitio.nombre}"),
        "descripcion_blog": (config.descripcion if config and config.descripcion else DESCRIPCION.get(sitio.clave, "")),
        "filtros_activos": any(f[k] for k in ("q", "categoria", "estado", "web")),
        "estados_editoriales": [("borrador", "Borrador"), ("revision", "En revisión"), ("aprobado", "Aprobado")],
        "estados_web": [("web", "Publicado"), ("falta", "Falta publicar"), ("bloqueado", "Blog sin activar"), ("no", "No está en la web")],
    }
    return render(request, "editorial/blog.html", ctx)


def _sitio_post(request, clave, nivel=1):
    sitio = get_object_or_404(SitioWeb, clave=clave)
    lineas = LineaProducto.objects.filter(sitio=sitio)
    if not (puede(request.user, sitio.pk, nivel=nivel) or (nivel == 1 and any(puede(request.user, sitio.pk, l.pk) for l in lineas))):
        raise PermissionDenied
    return sitio


def _volver(sitio, linea="", request=None):
    """Vuelve a donde estaba (portada del blog o «Ver todas»), con sus filtros."""
    destino = request.POST.get("next", "") if request is not None else ""
    if destino.startswith(reverse("blog:index")) and "//" not in destino:
        return redirect(destino)
    return redirect(reverse("blog:index") + f"?sitio={sitio.clave}" + (f"&linea={linea}" if linea else ""))


@require_POST
def actualizar(request, clave):
    sitio = _sitio_post(request, clave)
    n = actualizar_ideas(sitio)
    st = ia.estado()
    if st["disponible"]:
        try:
            n += len(ia.sugerir_ideas(sitio, request.user, linea=LineaProducto.objects.filter(pk=request.POST.get("linea") or 0, sitio=sitio).first()))
        except (ia.IADesactivada, ia.LimiteAlcanzado) as e:
            messages.warning(request, str(e))
        except Exception:  # noqa: BLE001
            messages.warning(request, "El proveedor de IA no respondió. Se actualizaron solo las ideas editoriales.")
    messages.success(request, f"Actualidad e ideas: {n} nueva(s)." if n else "No hay novedades: los temas de tus contenidos ya tienen artículo o idea.")
    return _volver(sitio, request.POST.get("linea", ""), request)


@require_POST
def idea_accion(request, pk, accion):
    idea = get_object_or_404(IdeaEditorial, pk=pk)
    if not puede(request.user, idea.sitio_id, idea.linea_id):
        raise PermissionDenied
    if accion == "borrador":
        try:
            art = crear_borrador(idea, request.user)
        except ValueError as e:
            messages.error(request, str(e))
            return _volver(idea.sitio)
        messages.success(request, "Se creó el borrador. Revisalo y completalo: nada se publica sin aprobación.")
        return redirect("wagtailadmin_pages:edit", art.pk)
    nuevos = {"guardar": "guardada", "descartar": "descartada", "restaurar": "sugerida"}
    if accion not in nuevos:
        raise PermissionDenied
    idea.estado = nuevos[accion]
    idea.save(update_fields=["estado", "actualizada"])
    messages.success(request, {"guardar": "Guardada: queda arriba hasta que la uses o la descartes.",
                               "descartar": "Descartada: no vuelve a sugerirse.", "restaurar": "Restaurada."}[accion])
    return _volver(idea.sitio, request.POST.get("linea", ""), request)


def idea_detalle(request, pk):
    idea = get_object_or_404(IdeaEditorial.objects.select_related("sitio", "linea", "importacion"), pk=pk)
    if not puede(request.user, idea.sitio_id, idea.linea_id) and not puede(request.user, idea.sitio_id):
        raise PermissionDenied
    return render(request, "editorial/idea.html", {"page_title": idea.titulo, "idea": idea, "marca": idea.sitio.marca,
                                                   "trends": url_trends(idea.palabras_clave or idea.titulo)})


def importar(request, clave):
    sitio = _sitio_post(request, clave)
    lineas = list(LineaProducto.objects.filter(sitio=sitio))
    if request.method == "POST":
        archivo = request.FILES.get("archivo")
        consultado = parse_date(request.POST.get("consultado", "")) or timezone.localdate()
        linea = next((l for l in lineas if str(l.pk) == request.POST.get("linea")), None)
        if archivo is None or archivo.size > 2_000_000:
            messages.error(request, "Elegí el CSV exportado de Google Trends (hasta 2 MB).")
        else:
            try:
                texto = archivo.read().decode("utf-8-sig", errors="replace")
                imp, creadas, desc = importar_trends(sitio, texto, consultado, request.user, linea, request.POST.get("termino", ""),
                                                     request.POST.get("region") or "Argentina", request.POST.get("periodo", ""), archivo.name)
                msg = f"Se importaron {creadas} consulta(s) como tendencias verificadas."
                if desc:
                    msg += f" {desc} se descartaron por temas que no corresponden al blog."
                messages.success(request, msg)
                return _volver(sitio, request.POST.get("linea", ""))
            except ErrorImportacion as e:
                messages.error(request, str(e))
    return render(request, "editorial/importar.html", {"page_title": "Importar tendencias", "sitio": sitio, "marca": sitio.marca,
                                                       "lineas": lineas, "hoy": timezone.localdate()})


@require_POST
def nuevo(request, clave):
    sitio = _sitio_post(request, clave)
    padre = blog_general(sitio)
    if padre is None:
        messages.error(request, f"{sitio.nombre} no tiene un sitio de Wagtail asociado.")
        return _volver(sitio)
    request.session["gwa_linea_nueva"] = request.POST.get("linea") or ""
    return redirect("wagtailadmin_pages:add", "contenidos", "articulopage", padre.pk)


def configurar(request, clave):
    sitio = _sitio_post(request, clave)
    c = ConfigBlog.objects.filter(sitio=sitio).first()
    if c is None:
        if request.method != "POST":
            return render(request, "editorial/configurar.html", {"page_title": "Configurar blog", "sitio": sitio, "marca": sitio.marca})
        c = ConfigBlog.nueva(sitio)
        c.save()
        c.save_revision(user=request.user, log_action=True)
    return redirect("wagtailsnippets_editorial_configblog:edit", c.pk)


def actualidad(request, clave):
    """«Ver todas»: toda la actualidad e ideas del sitio, con los mismos filtros (y las descartadas, para recuperarlas)."""
    sitio = _sitio_post(request, clave)
    lineas = list(LineaProducto.objects.filter(sitio=sitio).order_by("orden"))
    linea = next((l for l in lineas if str(l.pk) == request.GET.get("linea", "")), None)
    fa = _filtros_actualidad(request)
    descartadas = request.GET.get("ver") == "descartadas"
    ideas = _ideas(sitio, linea.pk if linea else None, fa, descartadas=descartadas)
    ctx = {"page_title": f"Actualidad e ideas · {sitio.nombre}", "sitio": sitio, "marca": sitio.marca, "lineas": lineas, "linea": linea,
           "descartadas": descartadas, "config": config_actual(sitio), "pagina_completa": True,
           **_ctx_actualidad(sitio, linea, fa, ideas)}
    return render(request, "editorial/actualidad.html", ctx)
