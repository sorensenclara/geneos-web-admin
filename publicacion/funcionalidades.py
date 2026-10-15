"""«Oferta comercial → Funcionalidades»: listado del snippet Funcionalidad (contenidos/wagtail_hooks.py).

Una pestaña por producto (GERP, GEAGRO, GEMA) con dos vistas de los mismos datos: la matriz por plan
(Comparador) y una tabla simple (Lista). Los cambios rápidos se guardan como revisiones de cada
funcionalidad, con el mismo historial, permisos, borrador y aprobación de Wagtail que la edición completa.
No hay otra fuente de datos: la web lee las funcionalidades aprobadas y visibles (publicacion/exportar.py)."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse

from contenidos.models import ESTADOS_VALOR, Funcionalidad, Plan, ValorFuncionalidad
from sitios.models import LineaProducto, SitioWeb
from sitios.permisos import SitioPermissionPolicy, puede, sitios_permitidos

GRUPOS = [("basic", "Básica"), ("advanced", "Avanzada")]
# Ícono y texto de cada estado: la celda nunca depende solo del color
ICONO_ESTADO = {"incluido": "success", "no_incluido": "circle-xmark", "opcional": "circle-minus", "texto": "type", "a_confirmar": "help"}
ESTADOS = [(k, v.replace(" ✓", "").replace(" —", "")) for k, v in ESTADOS_VALOR]
ESTADOS = [(k, "Texto personalizado" if k == "texto" else v) for k, v in ESTADOS]


def _politica():
    return SitioPermissionPolicy(Funcionalidad)


def _productos(user, politica):
    """Productos comerciales del usuario, con la cantidad de funcionalidades de cada uno."""
    visibles = politica.instances_user_has_any_permission_for(user, ["view", "change"])
    ids = sitios_permitidos(user)  # incluye a quien tiene acceso solo a una línea (GEAGRO Cereales o Vid)
    res = []
    for s in SitioWeb.objects.filter(motor="comercial").order_by("orden"):
        if ids is None or s.pk in ids:
            res.append({"sitio": s, "marca": s.marca, "n": visibles.filter(sitio=s).count()})
    return res


def _valores(obj):
    return {v.plan_id: v for v in obj.valores.all()}


def _fila(f, planes, user):
    obj = f.get_latest_revision_as_object() if f.has_unpublished_changes else f
    vals = _valores(obj)
    celdas = []
    for p in planes:
        v = vals.get(p.pk)
        estado = v.estado if v else "a_confirmar"
        celdas.append({"plan": p, "estado": estado, "texto": v.texto if v else "", "icono": ICONO_ESTADO.get(estado, "help"),
                       "fuente": v.fuente if v else "", "validado": v.validado_por if v else ""})
    editable = puede(user, f.sitio_id, f.linea_id) and not (f.locked and f.locked_by_id != user.pk)
    return {"f": f, "v": obj, "celdas": celdas, "editable": editable,
            "a_confirmar": any(c["estado"] == "a_confirmar" for c in celdas),
            "previa": reverse("wagtailsnippets_contenidos_funcionalidad:revisions_view", args=[f.pk, f.latest_revision_id]) if f.latest_revision_id else ""}


def _cambios(request, f, obj, planes, lineas):
    """Campos y valores por plan que llegan del formulario, solo si cambiaron. Devuelve (campos, valores, error)."""
    post, pk = request.POST, f.pk
    campos = {}
    grupo = post.get(f"grupo_{pk}", obj.grupo)
    if grupo in dict(GRUPOS) and grupo != obj.grupo:
        campos["grupo"] = grupo
    for k in ("resumen", "visible"):
        if f"{k}_{pk}__presente" in post:
            nuevo = post.get(f"{k}_{pk}") == "on"
            if nuevo != getattr(obj, k):
                campos[k] = nuevo
    orden = post.get(f"orden_{pk}", "")
    if orden.isdigit() and int(orden) != obj.orden:
        campos["orden"] = int(orden)
    if lineas and f"linea_{pk}" in post:
        lid = post.get(f"linea_{pk}") or None
        lid = int(lid) if lid and lid.isdigit() and int(lid) in lineas else None
        if lid != obj.linea_id:
            campos["linea_id"] = lid
    vals, valores, error = _valores(obj), {}, ""
    for p in planes:
        estado = post.get(f"valor_{pk}_{p.pk}")
        if estado is None:
            continue
        texto = post.get(f"texto_{pk}_{p.pk}", "").strip() if estado == "texto" else ""
        if estado not in dict(ESTADOS_VALOR):
            continue
        if estado == "texto" and not texto:
            error = f"falta el texto personalizado para {p.nombre}"
        actual = vals.get(p.pk)
        antes = (actual.estado, actual.texto) if actual else ("a_confirmar", "")
        if (estado, texto) != antes:
            valores[p.pk] = (estado, texto)
    return campos, valores, error


def funcionalidades(request):
    politica = _politica()
    if not politica.user_has_any_permission(request.user, ["view", "change"]):
        raise PermissionDenied
    productos = _productos(request.user, politica)
    if not productos:
        raise PermissionDenied
    clave = request.GET.get("sitio") or request.POST.get("sitio") or request.session.get("gwa_sitio") or ""
    actual = next((p for p in productos if p["sitio"].clave == clave), productos[0])
    sitio = actual["sitio"]
    lista_url = reverse("wagtailsnippets_contenidos_funcionalidad:list") + f"?sitio={sitio.clave}"
    planes = list(Plan.objects.filter(sitio=sitio).order_by("orden"))
    lineas = {l.pk: l for l in LineaProducto.objects.filter(sitio=sitio).order_by("orden")}
    funcs = sorted(politica.instances_user_has_any_permission_for(request.user, ["view", "change"]).filter(sitio=sitio)
                   .select_related("sitio", "linea", "latest_revision__user", "locked_by"),
                   key=lambda f: (f.grupo != "basic", f.orden, f.pk))

    if request.method == "POST":
        accion = request.POST.get("accion")
        cambiados, sin_permiso, errores = [], [], []
        for f in funcs:
            if not puede(request.user, f.sitio_id, f.linea_id) or (f.locked and f.locked_by_id != request.user.pk):
                continue
            obj = f.get_latest_revision_as_object() if f.has_unpublished_changes else f
            campos, valores, error = _cambios(request, f, obj, planes, lineas)
            if error:
                errores.append(f"«{f}»: no se guardó, {error}.")
                continue
            if "linea_id" in campos and not puede(request.user, f.sitio_id, campos["linea_id"]):
                errores.append(f"«{f}»: no tenés permiso para esa línea.")
                continue
            if not campos and not valores:
                if not (accion == "aprobar" and f.has_unpublished_changes):
                    continue
                rev = f.latest_revision  # aprobar un borrador guardado antes, sin cambios nuevos
            else:
                for k, v in campos.items():
                    setattr(obj, k, v)
                if valores:
                    existentes = list(obj.valores.all())
                    por_plan = {v.plan_id: v for v in existentes}
                    for plan_id, (estado, texto) in valores.items():
                        if plan_id in por_plan:
                            por_plan[plan_id].estado, por_plan[plan_id].texto = estado, texto
                        else:
                            existentes.append(ValorFuncionalidad(plan_id=plan_id, estado=estado, texto=texto))
                    obj.valores = existentes
                rev = obj.save_revision(user=request.user, log_action=True)
            if accion == "aprobar":
                if puede(request.user, f.sitio_id, obj.linea_id, nivel=2):
                    rev.publish(user=request.user)
                else:
                    sin_permiso.append(str(f))
            cambiados.append(f)
        if cambiados:
            msg = f"{len(cambiados)} funcionalidad(es) " + ("guardadas y aprobadas." if accion == "aprobar" else "guardadas como borrador.")
            messages.success(request, msg + " Se ven en la web después de «Publicar en la web» desde «Estado de las webs».")
        elif not errores:
            messages.info(request, "No hubo cambios.")
        for e in errores:
            messages.error(request, e)
        for s in sin_permiso:
            messages.warning(request, f"«{s}» quedó como borrador porque no tenés permiso para aprobar en ese producto.")
        vista = request.POST.get("vista", "")
        return redirect(lista_url + (f"&vista={vista}" if vista in ("comparador", "lista") else ""))

    # Se muestran como quedan con sus borradores (grupo y orden incluidos), igual que los ordena la web
    filas = sorted((_fila(f, planes, request.user) for f in funcs), key=lambda r: (r["v"].grupo != "basic", r["v"].orden, r["f"].pk))
    vista = request.GET.get("vista") if request.GET.get("vista") in ("comparador", "lista") else "comparador"
    return render(request, "publicacion/funcionalidades.html", {
        "page_title": "Funcionalidades", "productos": productos, "actual": actual, "sitio": sitio, "planes": planes,
        "lineas": list(lineas.values()), "filas": filas, "vista": vista, "grupos": GRUPOS, "estados": ESTADOS,
        "iconos_estado": ICONO_ESTADO, "puede_agregar": politica.user_has_permission(request.user, "add"),
        "puede_publicar": puede(request.user, sitio.pk, nivel=2),
        "con_a_confirmar": sum(1 for f in filas if f["a_confirmar"]),
    })
