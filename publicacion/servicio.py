"""Circuito de publicación: vista previa, publicación en la web, vuelta atrás y estado de cada sitio.

«Aprobado» = publicado dentro del administrador (versión vigente de Wagtail).
«En la web» = la última publicación que terminó bien. Lo aprobado después de esa fecha figura como pendiente.
"""
import re
import shutil
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from contenidos.models import (ArticuloPage, AutorBlog, BlogIndexPage, CategoriaBlog, Funcionalidad, IdentidadSitio, PaginaWeb, Plan, PreguntaFrecuente, Recurso,
                               Redireccion, Sector, Testimonio, sitio_de_pagina)
from sitios.models import SitioWeb

from . import despliegue
from .models import Despliegue
from .comparar import comparar, referencias_rotas
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
    if sitio.motor != "comercial" and not (isinstance(obj, (ArticuloPage, BlogIndexPage)) or obj.__class__.__name__ == "ConfigBlog"):
        # Las páginas institucionales de GENEOS salen de su build.py: el administrador solo suma las Noticias
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


# ------------------------------------------------------------------------------------------------ Publicación en la web
# Preparar → revisar (controles + diferencias con lo publicado) → confirmar. Lo que se publica es exactamente lo revisado:
# no se vuelve a generar. Una preparación vence a las 2 horas, o antes si se aprueban cambios o se publica otra versión.
VIGENCIA_PREPARACION = timedelta(hours=2)
RENGLONES_POR_PAGINA = 80
PREPARACIONES_GUARDADAS = 5


class ErrorPublicacion(Exception):
    pass


def _usuario(u):
    return u if u and getattr(u, "is_authenticated", False) else None


def _referencia_actual(sitio):
    """Carpeta con lo que hoy está publicado, para comparar: el clon del repositorio o la versión local activa."""
    if sitio.destino == "repositorio":
        return despliegue.preparar_repo(sitio)
    actual = despliegue.raiz(sitio) / "actual"
    return actual.resolve() if actual.exists() else None


def _resumen(res):
    return {"paginas_nuevas": res["paginas_nuevas"], "paginas_faltantes": res["paginas_faltantes"],
            "texto": {r: d[:RENGLONES_POR_PAGINA] for r, d in res["texto"].items()}, "renglones": {r: len(d) for r, d in res["texto"].items()},
            "archivos_nuevos": res["archivos_nuevos"][:300], "archivos_faltantes": res["archivos_faltantes"][:300],
            "total_archivos_nuevos": len(res["archivos_nuevos"]), "total_archivos_faltantes": len(res["archivos_faltantes"])}


def _limpiar_preparadas(sitio):
    d = despliegue.raiz(sitio) / "preparadas"
    if d.exists():
        for v in sorted((x for x in d.iterdir() if x.is_dir()), reverse=True)[PREPARACIONES_GUARDADAS:]:
            shutil.rmtree(v, ignore_errors=True)


def preparar_publicacion(sitio, usuario=None, motivo=""):
    """Genera la web con todo lo aprobado, corre los controles y la compara con lo publicado. No cambia la web."""
    d = Despliegue.objects.create(sitio=sitio, tipo="preparacion", usuario=_usuario(usuario), motivo=(motivo or "Publicación en la web")[:200])
    nombre = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{d.pk}"
    destino = despliegue.raiz(sitio) / "preparadas" / nombre
    publico = sitio.publica_afuera
    try:
        carpeta, datos, registro = generar(sitio, destino, publico=publico)
        controles = validar(sitio, carpeta, datos, publico=publico)
        if "FALTAN:" in registro:
            controles.append("Faltan recursos de la web (ver el registro).")
        controles += [f"Enlace o recurso que no existe: {r}" for r in referencias_rotas(carpeta)]
        referencia = None
        try:
            referencia = _referencia_actual(sitio)
        except despliegue.ErrorRepositorio as e:
            controles.append(f"No se pudo leer el repositorio de la web: {e}")
        if referencia and sitio.destino == "repositorio":
            for wf in despliegue.workflow_regenera(referencia):
                controles.append(f"El repositorio tiene el workflow {wf}, que vuelve a generar la web por su cuenta y pisaría lo publicado. "
                                 "Hay que reemplazarlo por el de publicación estática antes de publicar desde el administrador.")
        d.diferencias = _resumen(comparar(carpeta, referencia)) if referencia else {"primera": True}
        d.controles, d.registro = controles, registro
        d.estado, d.version, d.carpeta = ("listo" if not controles else "fallo"), nombre, str(carpeta)
    except Exception as e:  # noqa: BLE001 — una preparación fallida no toca nada
        d.estado, d.registro = "fallo", str(e)
        shutil.rmtree(destino, ignore_errors=True)
    d.finalizado = timezone.now()
    d.save()
    _limpiar_preparadas(sitio)
    return d


def motivo_para_no_publicar(prep):
    """None si la versión preparada se puede publicar; si no, por qué hay que prepararla de nuevo."""
    if prep.tipo != "preparacion" or prep.estado != "listo":
        return "Esta versión no está lista para publicar." if prep.estado != "ok" else "Esta versión ya se publicó."
    if not prep.carpeta or not Path(prep.carpeta).exists():
        return "Los archivos de esta versión ya no están. Prepará la publicación de nuevo."
    if timezone.now() - prep.finalizado > VIGENCIA_PREPARACION:
        return "Pasaron más de 2 horas desde que se preparó. Prepará la publicación de nuevo para revisar lo actual."
    if prep.sitio.despliegues.filter(tipo__in=("publicacion", "vuelta_atras"), estado="ok", iniciado__gt=prep.iniciado).exists():
        return "Después de preparar esta versión se publicó otra. Prepará la publicación de nuevo."
    if _cambios(prep.sitio, prep.iniciado)[0]:
        return "Se aprobaron cambios después de preparar esta versión. Prepará la publicación de nuevo para revisarlos."
    return None


def publicar_preparacion(prep, usuario=None):
    """Publica exactamente la versión revisada. Si algo falla, la web pública queda como estaba."""
    sitio = prep.sitio
    motivo = motivo_para_no_publicar(prep)
    if motivo:
        raise ErrorPublicacion(motivo)
    d = Despliegue.objects.create(sitio=sitio, usuario=_usuario(usuario), motivo=prep.motivo, preparacion=prep)
    carpeta = Path(prep.carpeta)
    registro = []
    try:
        if sitio.destino == "repositorio":
            quien = _usuario(usuario)
            mensaje = f"{prep.motivo}\n\nPublicado desde GENEOS Web Admin por {quien.get_username() if quien else 'el sistema'} (publicación {d.pk})."
            d.commit, hubo = despliegue.publicar_en_repo(sitio, carpeta, mensaje)
            registro.append(f"Repositorio {sitio.repo_url} · {sitio.repo_rama}: " + (f"commit {d.commit[:10]}" if hubo else "sin cambios en los archivos"))
        elif sitio.destino == "comando" and sitio.comando_despliegue.strip():
            registro.append(despliegue.ejecutar_comando(sitio, carpeta))
        # Copia local de cada versión publicada: historial y vuelta atrás
        version = despliegue.nueva_carpeta(sitio, prep.version)
        shutil.move(str(carpeta.parent), str(version))
        carpeta = version / carpeta.name
        despliegue.activar(sitio, carpeta)
        despliegue.limpiar(sitio)
        d.estado, d.version, d.carpeta = "ok", prep.version, str(carpeta)
        prep.estado, prep.carpeta = "ok", str(carpeta)
        prep.save(update_fields=["estado", "carpeta"])
    except Exception as e:  # noqa: BLE001 — cualquier error deja la versión anterior intacta
        d.estado = "fallo"
        registro.append(str(e))
    d.registro = "\n".join(x for x in registro if x)
    d.finalizado = timezone.now()
    d.save()
    return d


def descartar_preparacion(prep):
    if prep.estado == "listo":
        prep.estado = "descartado"
        prep.save(update_fields=["estado"])
        if prep.carpeta:
            shutil.rmtree(Path(prep.carpeta).parent, ignore_errors=True)


def publicar_sitio(sitio, usuario=None, motivo="Publicación manual"):
    """Preparar y publicar en un paso: solo para la carpeta local (pruebas, carga inicial, aprobación automática).
    Una web que ve otra gente (repositorio o comando) siempre pasa por la revisión y la confirmación."""
    if sitio.publica_afuera:
        raise ErrorPublicacion(f"La web de {sitio.nombre} se publica en {sitio.get_destino_display().lower()}: hay que revisar las diferencias y confirmar.")
    prep = preparar_publicacion(sitio, usuario, motivo)
    if prep.estado != "listo":
        d = Despliegue.objects.create(sitio=sitio, usuario=_usuario(usuario), motivo=motivo[:200], preparacion=prep, estado="fallo",
                                      registro="\n".join(["La web generada no pasó los controles:"] + [f"- {c}" for c in prep.controles] + [prep.registro]),
                                      finalizado=timezone.now())
        return d
    return publicar_preparacion(prep, usuario)


def volver_atras(sitio, usuario=None):
    """Vuelve a la versión publicada anterior a la actual. En un repositorio, con un commit nuevo (no reescribe el historial)."""
    d = Despliegue.objects.create(sitio=sitio, tipo="vuelta_atras", usuario=_usuario(usuario), motivo="Volver a la versión anterior")
    publicadas = list(sitio.despliegues.filter(tipo__in=("publicacion", "vuelta_atras"), estado="ok").exclude(pk=d.pk).order_by("-iniciado"))
    actual = publicadas[0] if publicadas else None
    # La más reciente de las versiones más viejas que la que está en la web (los nombres empiezan con fecha y hora)
    anterior = next((p for p in publicadas if actual and p.version and p.version < actual.version), None)
    try:
        if not anterior:
            raise ErrorPublicacion("No hay una versión anterior guardada.")
        carpeta = Path(anterior.carpeta)
        if sitio.destino == "repositorio":
            if not anterior.commit:
                raise ErrorPublicacion("La versión anterior no se publicó en el repositorio; no se puede volver a ella desde acá.")
            d.commit, _hubo = despliegue.restaurar_en_repo(sitio, anterior.commit, f"Volver a la versión {anterior.version} (publicación {d.pk}, GENEOS Web Admin)")
            d.registro = f"Repositorio: commit {d.commit[:10]} con los archivos del commit {anterior.commit[:10]}."
        elif sitio.destino == "comando" and sitio.comando_despliegue.strip():
            d.registro = despliegue.ejecutar_comando(sitio, carpeta)
        if carpeta.exists():
            despliegue.activar(sitio, carpeta)
        elif sitio.destino != "repositorio":
            raise ErrorPublicacion(f"Los archivos de la versión {anterior.version} ya no están guardados.")
        d.estado, d.version, d.carpeta = "ok", anterior.version, str(carpeta)
    except Exception as e:  # noqa: BLE001
        d.estado, d.registro = "fallo", str(e)
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


def _cambios(sitio, desde):
    """Contenido aprobado después de `desde` (pendiente de publicar), borradores y contenido en revisión."""
    pendientes, borradores, revision = [], 0, 0
    for p in _paginas_sitio(sitio):
        if p.live and p.last_published_at and p.last_published_at > desde:
            pendientes.append(("Página", p.title, p.last_published_at, reverse("wagtailadmin_pages:edit", args=[p.pk])))
        if p.has_unpublished_changes:
            borradores += 1
        if p.workflow_in_progress:
            revision += 1
    from editorial.models import ConfigBlog
    for model, tipo in ((Plan, "Plan"), (Funcionalidad, "Funcionalidad"), (Sector, "Sector"), (PreguntaFrecuente, "Pregunta frecuente"), (Testimonio, "Testimonio"), (IdentidadSitio, "Logos y favicon"),
                        (ConfigBlog, "Configuración del blog")):
        for o in model.objects.filter(sitio=sitio):
            if o.live and o.last_published_at and o.last_published_at > desde:
                pendientes.append((tipo, str(o), o.last_published_at, _url_snippet(o)))
            if o.has_unpublished_changes:
                borradores += 1
            if o.workflow_in_progress:
                revision += 1
    for model, tipo in ((Redireccion, "Redirección"), (CategoriaBlog, "Categoría"), (AutorBlog, "Autor"), (Recurso, "Recurso")):
        for o in model.objects.filter(sitio=sitio, actualizado__gt=desde):
            pendientes.append((tipo, str(o), o.actualizado, _url_snippet(o)))
    if sitio.actualizado > desde:
        pendientes.append(("Configuración", "Datos de contacto y opciones del sitio", sitio.actualizado, _url_snippet(sitio)))
    pendientes.sort(key=lambda x: x[2], reverse=True)
    return pendientes, borradores, revision


def estado_sitio(sitio):
    ultimo_ok = sitio.despliegues.filter(estado="ok", tipo__in=("publicacion", "vuelta_atras")).first()
    ultimo = sitio.despliegues.filter(tipo__in=("publicacion", "vuelta_atras")).first()
    desde = ultimo_ok.finalizado if ultimo_ok else timezone.make_aware(datetime(2000, 1, 1))
    pendientes, borradores, revision = _cambios(sitio, desde)
    error = ultimo if ultimo and ultimo.estado == "fallo" and (not ultimo_ok or ultimo.iniciado > ultimo_ok.iniciado) else None
    from .motor import conectado
    if not conectado(sitio):
        situacion = "no_conectado"
    elif error:
        situacion = "error"
    elif not ultimo_ok:
        situacion = "sin_publicar"
    elif pendientes:
        situacion = "pendiente"
    else:
        situacion = "al_dia"
    preparada = sitio.despliegues.filter(tipo="preparacion", estado="listo").first()
    publicadas = sitio.despliegues.filter(tipo__in=("publicacion", "vuelta_atras"), estado="ok").exclude(version="").values_list("version", flat=True)
    return {"sitio": sitio, "ultimo_ok": ultimo_ok, "error": error, "pendientes": pendientes, "borradores": borradores,
            "revision": revision, "situacion": situacion, "version_local": despliegue.version_actual(sitio),
            "preparada": preparada if preparada and not motivo_para_no_publicar(preparada) else None,
            "puede_volver": len(set(publicadas)) > 1}


def _url_snippet(o):
    from wagtail.admin.admin_url_finder import AdminURLFinder
    return AdminURLFinder().get_edit_url(o) or "#"
