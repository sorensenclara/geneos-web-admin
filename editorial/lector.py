"""Lectura automática de «Actualidad e ideas para publicar»: RSS/Atom, GDELT, YouTube Data API y Google Trends (RSS).

Reglas:
- Una fuente muestra resultados solo después de pasar todos los controles desde el servidor donde corre el administrador:
  accesible, permitida (robots.txt para feeds; condiciones documentadas para APIs), con publicaciones reales (título, fecha
  y enlace), recientes y relacionadas con el producto. El resultado de cada control queda registrado en la fuente.
- Si una fuente falla, se conservan sus resultados anteriores y se registra el error.
- Una sola lectura a la vez (CerrojoActualidad). Al ingresar al administrador se lee si pasaron más de 24 horas desde la última;
  «Actualizar ahora» lee en el momento. Corre en segundo plano: la pantalla no espera.
- Nunca se publica nada ni se copia el contenido: se guardan título, fecha, enlace, un resumen breve de la fuente y por qué
  se relaciona con el producto. Una nota que menciona una norma es una noticia periodística, no la norma.
- Sin dependencias externas: biblioteca estándar de Python.

Para una tarea programada futura: `python manage.py actualizar_actualidad` (mismo código, sin cambios).
"""
import hashlib
import html
import json
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from datetime import timezone as dt_tz
from email.utils import parsedate_to_datetime
from urllib import robotparser
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from .catalogo import EXCLUIR, NORMATIVA, TERMINOS
from .ideas import normalizar, url_trends

log = logging.getLogger(__name__)

UA = "GENEOS-Web-Admin/1.0 (lector interno de actualidad; +https://www.geneos.com.ar)"
LIMITE_BYTES = 3_000_000
DIAS_RECIENTE = 90      # para verificar una fuente: alguna publicación de los últimos 90 días
DIAS_GUARDAR = 30       # se guardan publicaciones de los últimos 30 días (los filtros muestran 7 o 30)
POR_FUENTE = 10         # máximo de publicaciones nuevas por fuente y lectura: calidad antes que cantidad
HORAS_ENTRE_LECTURAS = 24
MINUTOS_CERROJO = 20
GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_PAUSA = 6         # GDELT pide no más de un pedido cada 5 segundos
YOUTUBE_API = "https://www.googleapis.com/youtube/v3/"
RE_NORMATIVA = re.compile(NORMATIVA)


class ErrorLectura(Exception):
    pass


# ------------------------------------------------------------------------------------------------ Red
def _limpiar_url_error(texto):
    return re.sub(r"key=[^&\s]+", "key=…", str(texto))


def descargar(url, timeout=15):
    """Bytes de la URL (http/https, hasta 3 MB). Los errores se traducen a un motivo legible."""
    if urlsplit(url).scheme not in ("http", "https"):
        raise ErrorLectura("Dirección no válida (solo http o https).")
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/json, text/xml, */*;q=0.5"})
    try:
        with urlopen(req, timeout=timeout) as r:  # noqa: S310 — esquema validado arriba
            datos = r.read(LIMITE_BYTES + 1)
    except HTTPError as e:
        cuerpo = ""
        try:
            cuerpo = e.read(2000).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        if e.code == 403 and "quota" in cuerpo.lower():
            raise ErrorLectura("Se agotó la cuota diaria gratuita de la API.") from None
        if e.code in (401, 403) and "key" in cuerpo.lower():
            raise ErrorLectura("La clave de la API no es válida o no tiene la API habilitada.") from None
        raise ErrorLectura(f"El servidor respondió {e.code} ({e.reason}).") from None
    except URLError as e:
        motivo = _limpiar_url_error(getattr(e, "reason", e))
        if "403" in motivo and "tunnel" in motivo.lower():
            raise ErrorLectura("La red de este equipo no permite conectarse a ese sitio (proxy o lista de sitios permitidos).") from None
        raise ErrorLectura(f"No se pudo conectar: {motivo}"[:280]) from None
    except TimeoutError:
        raise ErrorLectura("El sitio no respondió a tiempo.") from None
    except OSError as e:
        raise ErrorLectura(f"No se pudo conectar: {_limpiar_url_error(e)}"[:280]) from None
    if len(datos) > LIMITE_BYTES:
        raise ErrorLectura("La respuesta supera los 3 MB.")
    return datos


def robots_permite(url, cache):
    """(permitido, motivo) según robots.txt (RFC 9309: 4xx = sin restricciones; sin respuesta = no leer)."""
    p = urlsplit(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in cache:
        rp = robotparser.RobotFileParser()
        try:
            texto = descargar(base + "/robots.txt", timeout=10).decode("utf-8", "replace")
            rp.parse(texto.splitlines())
            cache[base] = (rp, "")
        except ErrorLectura as e:
            if re.search(r"respondió 4\d\d", str(e)):
                rp.parse([])
                cache[base] = (rp, "")
            else:
                cache[base] = (None, f"No se pudo leer robots.txt: {e}")
    rp, motivo = cache[base]
    if rp is None:
        return False, motivo
    if not rp.can_fetch("GENEOS-Web-Admin", url):
        return False, "Su robots.txt no permite la lectura automática."
    return True, ""


# ------------------------------------------------------------------------------------------------ Formatos
def _local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _hijo(el, *nombres):
    for h in el:
        if _local(h.tag) in nombres:
            return h
    return None


def _texto(el):
    return "".join(el.itertext()).strip() if el is not None else ""


def fecha(valor):
    """datetime con zona a partir de RFC 822 (RSS), ISO 8601 (Atom, APIs) o 20261016T120000Z (GDELT)."""
    v = (valor or "").strip()
    if not v:
        return None
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z", v)
    if m:
        return datetime(*map(int, m.groups()), tzinfo=dt_tz.utc)
    try:
        d = parsedate_to_datetime(v)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=dt_tz.utc)


def texto_plano(valor, largo=240):
    t = re.sub(r"</?(b|i|em|strong|a|span|u|small|sup|sub)\b[^>]*>", "", valor or "", flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"\s+", " ", t)).strip()
    t = re.sub(r"(The post|La entrada|El artículo) .{0,200} (appeared first on|se publicó primero en|aparece primero en) .*$", "", t).strip()
    if len(t) > largo:
        t = t[:largo].rsplit(" ", 1)[0].rstrip(".,;:") + "…"
    return t


def leer_feed(datos):
    """Publicaciones de un RSS 2.0, RSS 1.0 o Atom: [{titulo, url, fecha, resumen, extra}]."""
    try:
        root = ET.fromstring(datos)
    except ET.ParseError as e:
        raise ErrorLectura(f"La respuesta no es un feed válido ({e}).") from None
    if _local(root.tag) not in ("rss", "feed", "rdf"):
        raise ErrorLectura("La respuesta no es un feed RSS o Atom.")
    res = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        titulo = texto_plano(_texto(_hijo(el, "title")), 300)
        link = _hijo(el, "link")
        url = ""
        if link is not None:
            url = (link.get("href") or link.text or "").strip()
            if link.get("href"):
                for l in el:
                    if _local(l.tag) == "link" and l.get("rel", "alternate") == "alternate" and l.get("href"):
                        url = l.get("href").strip()
                        break
        if not url:
            guid = _hijo(el, "guid")
            if guid is not None and (guid.get("isPermaLink", "true") == "true") and (guid.text or "").startswith("http"):
                url = guid.text.strip()
        f = fecha(_texto(_hijo(el, "pubdate", "published", "updated", "date", "issued")))
        resumen = _texto(_hijo(el, "description", "summary")) or _texto(_hijo(el, "encoded", "content"))
        extra = {}
        trafico = _hijo(el, "approx_traffic")
        if trafico is not None:
            extra["trafico"] = _texto(trafico)
        res.append({"titulo": titulo, "url": url, "fecha": f, "resumen": texto_plano(resumen), "extra": extra})
    return res


def leer_gdelt(consulta):
    """Artículos de medios argentinos en español de los últimos 14 días (GDELT DOC 2.0, modo artlist)."""
    q = f"{consulta} sourcecountry:argentina sourcelang:spanish"
    url = GDELT_API + "?" + urlencode({"query": q, "mode": "artlist", "format": "json", "maxrecords": "75", "timespan": "14d",
                                       "sort": "datedesc"})
    datos = descargar(url, timeout=30)
    texto = datos.decode("utf-8", "replace").strip()
    if not texto or texto == "{}":
        return []
    try:
        j = json.loads(texto)
    except json.JSONDecodeError:
        raise ErrorLectura(f"GDELT respondió: {texto[:200]}") from None
    res = []
    for a in j.get("articles", []):
        dominio = (a.get("domain") or urlsplit(a.get("url", "")).netloc).removeprefix("www.")
        res.append({"titulo": texto_plano(a.get("title", ""), 300), "url": a.get("url", ""), "fecha": fecha(a.get("seendate")),
                    "resumen": "", "extra": {"dominio": dominio}})
    return res


def youtube_configurado():
    return bool(getattr(settings, "YOUTUBE_API_KEY", ""))


def leer_youtube(canal):
    """Últimos videos de un canal público (YouTube Data API v3: 2 unidades de cuota por canal)."""
    clave = getattr(settings, "YOUTUBE_API_KEY", "")
    if not clave:
        raise ErrorLectura("Falta configurar la clave de YouTube en el servidor (YOUTUBE_API_KEY).")
    j = json.loads(descargar(YOUTUBE_API + "channels?" + urlencode({"part": "contentDetails,snippet", "id": canal, "key": clave})))
    if not j.get("items"):
        raise ErrorLectura("YouTube no encontró el canal.")
    canal_nombre = j["items"][0]["snippet"]["title"]
    lista = j["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    j = json.loads(descargar(YOUTUBE_API + "playlistItems?" + urlencode({"part": "snippet", "playlistId": lista, "maxResults": "10", "key": clave})))
    res = []
    for it in j.get("items", []):
        s = it.get("snippet", {})
        vid = s.get("resourceId", {}).get("videoId")
        if not vid or s.get("title") in ("Private video", "Deleted video"):
            continue
        res.append({"titulo": texto_plano(s.get("title", ""), 300), "url": f"https://www.youtube.com/watch?v={vid}",
                    "fecha": fecha(s.get("publishedAt")), "resumen": texto_plano(s.get("description", "")), "extra": {"canal": canal_nombre}})
    return res


def leer(fuente, robots_cache):
    """Publicaciones crudas de una fuente. Lanza ErrorLectura con el motivo si no se puede leer o no está permitido."""
    if fuente.metodo in ("rss", "trends"):
        ok, motivo = robots_permite(fuente.url, robots_cache)
        if not ok:
            raise ErrorLectura(motivo)
        return leer_feed(descargar(fuente.url))
    if fuente.metodo == "gdelt":
        return leer_gdelt(fuente.consulta)
    if fuente.metodo == "youtube":
        return leer_youtube(fuente.consulta)
    raise ErrorLectura("Esta fuente no tiene un canal de lectura automática.")


# ------------------------------------------------------------------------------------------------ Relevancia
def _lista(texto):
    return [normalizar(t) for t in (texto or "").split(",") if t.strip()]


def coincidencias(texto, terminos):
    t = " " + normalizar(texto) + " "
    return [x for x in terminos if re.search(r"(?<![\w])" + re.escape(x) + r"(?![\w])", t)]


def terminos_producto(producto, linea=""):
    if producto == "geagro":
        if linea:
            return _lista(TERMINOS[f"geagro:{linea}"])
        return _lista(TERMINOS["geagro:cereales"]) + _lista(TERMINOS["geagro:vid"])
    return _lista(TERMINOS.get(producto, ""))


def clasificar(item, fuente, producto, excluidos):
    """(relevante, coincidencias, línea) de una publicación para un producto."""
    texto = f"{item['titulo']} {item['resumen']}"
    if coincidencias(texto, excluidos):
        return False, [], ""
    linea = fuente.linea
    if producto == "geagro" and not linea:
        cer = coincidencias(texto, terminos_producto("geagro", "cereales"))
        vid = coincidencias(texto, terminos_producto("geagro", "vid"))
        if not cer and not vid:
            return (not fuente.filtrar), [], ""
        return True, (vid if len(vid) > len(cer) else cer), ("vid" if len(vid) > len(cer) else "cereales")
    terms = _lista(fuente.terminos) if fuente.terminos and fuente.producto != "todos" else terminos_producto(producto, linea)
    c = coincidencias(texto, terms)
    return (bool(c) or not fuente.filtrar), c, linea


def _url_normal(url):
    p = urlsplit(url.strip())
    qs = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    return urlunsplit(("https", p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), urlencode(qs), ""))


def huella(url):
    return "u:" + hashlib.sha1(_url_normal(url).encode()).hexdigest()[:24]


# ------------------------------------------------------------------------------------------------ Proceso
def _relacion(fuente, coinc, producto_nombre):
    base = fuente.relacion.rstrip(".")
    if coinc:
        return f"{base}. Menciona: {', '.join(coinc[:4])}."[:300]
    return f"{base}."[:300]


def _guardar(fuente, items, sitios, hoy, vistos):
    """Crea las tarjetas nuevas (sin repetir por enlace ni por título). Devuelve (relevantes, nuevas)."""
    from sitios.models import LineaProducto
    from .models import IdeaEditorial, config_actual
    productos = [p for p in ("geneos", "gerp", "geagro", "gema")] if fuente.producto == "todos" else [fuente.producto]
    relevantes = nuevas = 0
    desde = hoy - timedelta(days=DIAS_GUARDAR)
    por_producto = {}
    for producto in productos:
        sitio = sitios.get(producto)
        if sitio is None:
            continue
        cfg = config_actual(sitio)
        excluidos = _lista(EXCLUIR.get(producto, "")) + [normalizar(x) for x in (cfg.terminos_excluidos if cfg else [])]
        lineas = {l.clave: l for l in LineaProducto.objects.filter(sitio=sitio)}
        for it in sorted(items, key=lambda i: i["fecha"], reverse=True):
            ok, coinc, linea = clasificar(it, fuente, producto, excluidos)
            if fuente.producto == "todos" and not coinc:
                ok = False  # una fuente general solo aporta lo que coincide con el producto
            if not ok:
                continue
            relevantes += 1
            if it["fecha"].date() < desde or por_producto.get(producto, 0) >= POR_FUENTE:
                continue
            clave = huella(it["url"]) if fuente.tipo != "tendencia" else f"trends:{normalizar(it['titulo'])}:{it['fecha']:%Y%m%d}"
            tnorm = normalizar(it["titulo"])
            if (sitio.pk, clave) in vistos["claves"] or (sitio.pk, tnorm) in vistos["titulos"]:
                continue
            vistos["claves"].add((sitio.pk, clave))
            vistos["titulos"].add((sitio.pk, tnorm))
            nombre_fuente = fuente.nombre
            if fuente.metodo == "gdelt":
                nombre_fuente = f"{it['extra'].get('dominio', '')} (vía GDELT)"
            elif fuente.metodo == "youtube":
                nombre_fuente = f"{it['extra'].get('canal') or fuente.organizacion} · YouTube"
            dato = it["extra"].get("trafico", "")
            IdeaEditorial.objects.create(
                sitio=sitio, linea=lineas.get(linea), tipo=fuente.tipo, fuente_tipo=fuente.fuente_tipo, naturaleza=fuente.naturaleza,
                titulo=it["titulo"][:200], resumen=it["resumen"],
                relacion=_relacion(fuente, coinc, sitio.nombre), descripcion="",
                palabras_clave=", ".join(coinc)[:250] or it["titulo"][:250], fuente=nombre_fuente[:120],
                fuente_url=(url_trends(it["titulo"]) if fuente.tipo == "tendencia" else it["url"])[:600],
                publicado=it["fecha"].astimezone(timezone.get_current_timezone()).date(), consultado=hoy,
                dato=(f"{dato} búsquedas" if dato else "")[:60], intencion="Informativa",
                menciona_normativa=bool(RE_NORMATIVA.search(normalizar(f"{it['titulo']} {it['resumen']}"))) and fuente.tipo == "noticia",
                prioritaria=fuente.prioritaria, fuente_actualidad=fuente, clave=clave[:200])
            por_producto[producto] = por_producto.get(producto, 0) + 1
            nuevas += 1
    return relevantes, nuevas


def procesar(fuente, items, error, sitios, hoy, vistos):
    """Aplica los controles, registra el resultado en la fuente y, si está verificada, guarda lo nuevo."""
    ahora = timezone.now()
    fuente.ultima_lectura = ahora
    if error:
        fuente.ultimo_error = error[:300]
        if fuente.verificada is None:
            fuente.motivo = f"No pasó: {error}"[:300]
        fuente.save()
        return {"ok": False, "motivo": error}
    validos = [i for i in items if i["titulo"] and i["url"].startswith("http") and i["fecha"]]
    fuente.items_leidos = len(items)
    motivo = ""
    if not items:
        motivo = "La fuente no devolvió publicaciones."
    elif not validos:
        motivo = "Las publicaciones no traen título, fecha y enlace."
    recientes = [i for i in validos if i["fecha"] >= ahora - timedelta(days=DIAS_RECIENTE)]
    if validos:
        fuente.ultimo_item = max(i["fecha"] for i in validos).astimezone(timezone.get_current_timezone()).date()
    if validos and not recientes and fuente.tipo != "tendencia":
        motivo = f"Sin publicaciones en los últimos {DIAS_RECIENTE} días (la última es del {fuente.ultimo_item:%d/%m/%Y})."
    relevantes = nuevas = 0
    if not motivo:
        if fuente.verificada is None:
            # Antes de verificar: ¿hay algo relacionado con el producto? (sin guardar nada todavía)
            prueba = _contar_relevantes(fuente, recientes, sitios)
            if prueba == 0 and fuente.tipo != "tendencia":
                motivo = f"Ninguna de las {len(recientes)} publicaciones recientes se relaciona con el producto."
        if not motivo:
            if fuente.verificada is None:
                fuente.verificada = ahora
                fuente.estado = "activa"
            relevantes, nuevas = _guardar(fuente, recientes, sitios, timezone.localdate(), vistos)
    fuente.items_relevantes, fuente.items_nuevos = relevantes, nuevas
    if motivo:
        fuente.ultimo_error = motivo[:300]
        if fuente.verificada is None:
            fuente.motivo = f"No pasó: {motivo}"[:300]
        fuente.save()
        return {"ok": False, "motivo": motivo, "leidos": len(items)}
    fuente.ultimo_ok, fuente.ultimo_error = ahora, ""
    fuente.motivo = (f"Verificada el {timezone.localtime(fuente.verificada):%d/%m/%Y}: accesible, permitida, con publicaciones fechadas "
                     f"y relacionadas. Última lectura: {len(items)} publicaciones, {relevantes} relacionadas, {nuevas} nuevas.")[:300]
    fuente.save()
    return {"ok": True, "leidos": len(items), "relevantes": relevantes, "nuevos": nuevas}


def _contar_relevantes(fuente, items, sitios):
    productos = ["geneos", "gerp", "geagro", "gema"] if fuente.producto == "todos" else [fuente.producto]
    n = 0
    for p in productos:
        excl = _lista(EXCLUIR.get(p, ""))
        for it in items:
            ok, coinc, _ = clasificar(it, fuente, p, excl)
            if ok and (coinc or fuente.producto != "todos"):
                n += 1
    return n


# ------------------------------------------------------------------------------------------------ Ejecución
def _cerrojo():
    from .models import CerrojoActualidad
    c, _ = CerrojoActualidad.objects.get_or_create(pk=1, defaults={"hasta": timezone.now() - timedelta(minutes=1)})
    return c


def en_curso():
    return _cerrojo().hasta > timezone.now()


def tomar_cerrojo():
    from .models import CerrojoActualidad
    _cerrojo()
    ahora = timezone.now()
    return CerrojoActualidad.objects.filter(pk=1, hasta__lte=ahora).update(hasta=ahora + timedelta(minutes=MINUTOS_CERROJO)) == 1


def soltar_cerrojo():
    from .models import CerrojoActualidad
    CerrojoActualidad.objects.filter(pk=1).update(hasta=timezone.now())


def ultima():
    from .models import ActualizacionActualidad
    return ActualizacionActualidad.objects.exclude(estado="corriendo").first()


def necesita_actualizar():
    from .models import ActualizacionActualidad
    u = ActualizacionActualidad.objects.first()
    return u is None or u.inicio < timezone.now() - timedelta(hours=HORAS_ENTRE_LECTURAS)


def fuentes_a_leer(claves=None):
    from .models import FuenteActualidad
    qs = FuenteActualidad.objects.filter(estado__in=("prueba", "activa")).exclude(metodo__in=("ninguno", "google_news"))
    if claves:
        qs = qs.filter(clave__in=claves)
    if not youtube_configurado():
        qs = qs.exclude(metodo="youtube")
    return list(qs)


def actualizar_fuentes(origen="comando", usuario=None, claves=None):
    """Lee las fuentes en prueba y activas. Devuelve la ActualizacionActualidad, o None si ya había una lectura en curso."""
    from sitios.models import SitioWeb
    from .models import ActualizacionActualidad, IdeaEditorial
    if not tomar_cerrojo():
        return None
    act = ActualizacionActualidad.objects.create(origen=origen, usuario=usuario)
    try:
        fuentes = fuentes_a_leer(claves)
        sitios = {s.clave: s for s in SitioWeb.objects.all()}
        desde = timezone.localdate() - timedelta(days=DIAS_GUARDAR + 5)
        vistos = {"claves": set(), "titulos": set()}
        for sid, clave, titulo in IdeaEditorial.objects.filter(consultado__gte=desde).exclude(tipo="idea").values_list("sitio_id", "clave", "titulo"):
            vistos["claves"].add((sid, clave))
            vistos["titulos"].add((sid, normalizar(titulo)))
        for sid, clave in IdeaEditorial.objects.filter(clave__startswith="u:").values_list("sitio_id", "clave"):
            vistos["claves"].add((sid, clave))  # también las descartadas o viejas: no vuelven
        robots = {}

        def bajar(f):
            try:
                if f.metodo == "gdelt":
                    return f, None, "gdelt"
                return f, leer(f, robots), None
            except ErrorLectura as e:
                return f, None, str(e)
            except Exception as e:  # noqa: BLE001 — una fuente rota no frena a las demás
                log.exception("Lectura de %s", f.clave)
                return f, None, f"Error inesperado: {e.__class__.__name__}"

        resultados = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            for f, items, err in ex.map(bajar, fuentes):
                if err == "gdelt":
                    continue
                resultados.append((f, items, err))
        primero = True
        for f in fuentes:
            if f.metodo != "gdelt":
                continue
            if not primero:
                time.sleep(GDELT_PAUSA)
            primero = False
            try:
                resultados.append((f, leer(f, robots), None))
            except ErrorLectura as e:
                resultados.append((f, None, str(e)))
        detalle, ok, err, nuevos = {}, 0, 0, 0
        hoy = timezone.localdate()
        for f, items, error in resultados:
            r = procesar(f, items or [], error, sitios, hoy, vistos)
            detalle[f.clave] = r
            ok += r["ok"]
            err += not r["ok"]
            nuevos += r.get("nuevos", 0)
        act.estado = "ok" if not err else ("parcial" if ok else "error")
        act.fuentes_ok, act.fuentes_error, act.nuevos, act.detalle = ok, err, nuevos, detalle
    except Exception as e:  # noqa: BLE001
        log.exception("Actualización de fuentes")
        act.estado, act.detalle = "error", {"error": f"{e.__class__.__name__}: {e}"[:300]}
    finally:
        act.fin = timezone.now()
        act.save()
        soltar_cerrojo()
    return act


def _hilo(origen, usuario_id, claves):
    try:
        from django.contrib.auth import get_user_model
        u = get_user_model().objects.filter(pk=usuario_id).first() if usuario_id else None
        actualizar_fuentes(origen, u, claves)
    finally:
        close_old_connections()


def iniciar(origen, usuario=None, forzar=False, claves=None):
    """Arranca una lectura sin bloquear la pantalla. False si no hacía falta o ya había una en curso."""
    if en_curso() or (not forzar and not necesita_actualizar()):
        return False
    if not fuentes_a_leer(claves):
        return False
    uid = usuario.pk if usuario is not None and usuario.is_authenticated else None
    if getattr(settings, "ACTUALIDAD_EN_SEGUNDO_PLANO", True):
        threading.Thread(target=_hilo, args=(origen, uid, claves), daemon=True, name="gwa-actualidad").start()
    else:
        actualizar_fuentes(origen, usuario, claves)
    return True
