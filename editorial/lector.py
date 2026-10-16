"""Lectura automática de «Actualidad e ideas para publicar»: RSS/Atom, GDELT, YouTube Data API y Google Trends (RSS).

Reglas:
- Una fuente muestra resultados solo después de pasar todos los controles desde el servidor donde corre el administrador:
  accesible, permitida (robots.txt para feeds; condiciones documentadas para APIs), con publicaciones reales (título, fecha
  y enlace), recientes y relacionadas con el producto. El resultado de cada control queda registrado en la fuente, con
  muestras de lo aceptado y lo descartado y el motivo.
- Relevancia por puntaje (catalogo.RELEVANCIA): un término fuerte alcanza; los generales solo suman. Temas ajenos y series
  repetitivas (precios del día, cierres de mercado) se descartan.
- Una misma noticia no se repite: se compara el enlace normalizado y la similitud del título con lo ya guardado.
- Si una fuente falla, se conservan sus resultados anteriores y se registra el error (técnico o de calidad).
- Límites que no se relajan: 3 MB por respuesta (un feed más grande se lee de forma incremental hasta ese tope), robots.txt,
  y los 403 no se insisten. GDELT: un pedido cada 10 segundos, caché de 12 horas, un reintento ante 429 y, si sigue
  limitando en tres lecturas seguidas, la fuente se pausa sola.
- Una sola lectura a la vez (CerrojoActualidad). Al ingresar al administrador se lee si pasaron más de 24 horas desde la última;
  «Actualizar ahora» lee en el momento. Corre en segundo plano: la pantalla no espera.
- Nunca se publica nada ni se copia el contenido: título, fecha, enlace, un resumen breve de la fuente y la relación con el producto.
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
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from .catalogo import EXCLUIR, NORMATIVA, RELEVANCIA, RUIDO
from .ideas import normalizar, url_trends

log = logging.getLogger(__name__)

UA = "GENEOS-Web-Admin/1.0 (lector interno de actualidad; +https://www.geneos.com.ar)"
LIMITE_BYTES = 3_000_000
TIMEOUT = 30
DIAS_RECIENTE = 90      # para verificar una fuente: alguna publicación de los últimos 90 días
DIAS_GUARDAR = 30       # se guardan publicaciones de los últimos 30 días (los filtros muestran 7 o 30)
POR_FUENTE = 10         # máximo de publicaciones nuevas por fuente y lectura: calidad antes que cantidad
MAX_ITEMS_FEED = 60     # en feeds enormes alcanza con las primeras publicaciones
HORAS_ENTRE_LECTURAS = 24
MINUTOS_CERROJO = 20
UMBRAL = 4              # puntaje mínimo de relevancia
SIMILAR = 0.6           # títulos con esta similitud (o más) son la misma noticia
GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_PAUSA = 10        # GDELT pide no más de un pedido cada 5 segundos: dejamos el doble
GDELT_CACHE_HORAS = 12
GDELT_PAUSAR_TRAS = 3   # lecturas seguidas con 429 antes de pausar la fuente
YOUTUBE_API = "https://www.googleapis.com/youtube/v3/"
RE_NORMATIVA = re.compile(NORMATIVA)
VERSION_RELEVANCIA = "2026-10-16b"  # al cambiar las reglas, lo ya guardado se vuelve a evaluar una vez


class ErrorLectura(Exception):
    def __init__(self, mensaje, codigo=None, reintentar=None, parcial=None, html=None):
        super().__init__(mensaje)
        self.codigo, self.reintentar, self.parcial, self.html = codigo, reintentar, parcial, html


# ------------------------------------------------------------------------------------------------ Red
def _limpiar_url_error(texto):
    return re.sub(r"key=[^&\s]+", "key=…", str(texto))


def _pedir(url, timeout):
    if urlsplit(url).scheme not in ("http", "https"):
        raise ErrorLectura("Dirección no válida (solo http o https).")
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/json, text/xml, text/html;q=0.8, */*;q=0.5"})
    try:
        with urlopen(req, timeout=timeout) as r:  # noqa: S310 — esquema validado arriba
            datos = r.read(LIMITE_BYTES + 1)
            tipo = r.headers.get("Content-Type", "")
    except HTTPError as e:
        cuerpo = ""
        try:
            cuerpo = e.read(2000).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        espera = None
        try:
            espera = int(e.headers.get("Retry-After", "")) if e.headers else None
        except ValueError:
            pass
        if e.code == 403 and "quota" in cuerpo.lower():
            raise ErrorLectura("Se agotó la cuota diaria gratuita de la API.", 403) from None
        if e.code in (401, 403) and "key" in cuerpo.lower():
            raise ErrorLectura("La clave de la API no es válida o no tiene la API habilitada.", e.code) from None
        if e.code == 403:
            raise ErrorLectura("El sitio rechaza lectores automáticos (403). No se insiste.", 403) from None
        if e.code == 429:
            raise ErrorLectura("El servicio limitó los pedidos (429: demasiados pedidos).", 429, reintentar=espera) from None
        raise ErrorLectura(f"El servidor respondió {e.code} ({e.reason}).", e.code) from None
    except URLError as e:
        motivo = _limpiar_url_error(getattr(e, "reason", e))
        if "403" in motivo and "tunnel" in motivo.lower():
            raise ErrorLectura("La red de este equipo no permite conectarse a ese sitio (proxy o lista de sitios permitidos).", "red") from None
        if "timed out" in motivo.lower():
            raise ErrorLectura("El sitio no respondió a tiempo.", "tiempo") from None
        raise ErrorLectura(f"No se pudo conectar: {motivo}"[:280], "conexion") from None
    except TimeoutError:
        raise ErrorLectura("El sitio no respondió a tiempo.", "tiempo") from None
    except OSError as e:
        raise ErrorLectura(f"No se pudo conectar: {_limpiar_url_error(e)}"[:280], "conexion") from None
    if len(datos) > LIMITE_BYTES:
        raise ErrorLectura("La respuesta supera los 3 MB.", "grande", parcial=datos[:LIMITE_BYTES])
    return datos, tipo


def descargar(url, timeout=TIMEOUT, reintentos=1):
    """Bytes de la URL (http/https, hasta 3 MB). Un reintento prudente (5 s) ante falta de respuesta o error 5xx."""
    for intento in range(reintentos + 1):
        try:
            return _pedir(url, timeout)[0]
        except ErrorLectura as e:
            transitorio = e.codigo in ("tiempo", "conexion") or (isinstance(e.codigo, int) and 500 <= e.codigo < 600 and e.codigo != 505)
            if not transitorio or intento == reintentos:
                raise
            time.sleep(5)


def robots_permite(url, cache):
    """(permitido, motivo) según robots.txt (RFC 9309: 4xx = sin restricciones; sin respuesta = no leer)."""
    p = urlsplit(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in cache:
        rp = robotparser.RobotFileParser()
        try:
            texto = descargar(base + "/robots.txt", timeout=15).decode("utf-8", "replace")
            rp.parse(texto.splitlines())
            cache[base] = (rp, "")
        except ErrorLectura as e:
            if isinstance(e.codigo, int) and 400 <= e.codigo < 500:
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


def _item(el):
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
    return {"titulo": titulo, "url": url, "fecha": f, "resumen": texto_plano(resumen), "extra": extra}


RE_CONTROL = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")
RE_AMP = re.compile(rb"&(?!(?:#\d+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);)")


def _parsear(datos, truncado=False):
    """Publicaciones de un RSS/Atom leyendo de forma incremental (un feed cortado por el tope de 3 MB rinde lo completo)."""
    p = ET.XMLPullParser(events=("start", "end"))
    items, raiz = [], None
    try:
        for i in range(0, len(datos), 65536):
            p.feed(datos[i:i + 65536])
            for ev, el in p.read_events():
                if ev == "start" and raiz is None:
                    raiz = _local(el.tag)
                    if raiz not in ("rss", "feed", "rdf"):
                        raise ErrorLectura("La respuesta no es un feed RSS o Atom.")
                if ev == "end" and _local(el.tag) in ("item", "entry"):
                    items.append(_item(el))
                    el.clear()
                    if len(items) >= MAX_ITEMS_FEED:
                        return items
        if not truncado:
            p.close()
    except ET.ParseError:
        if truncado and items:
            return items
        raise
    return items


def leer_feed(datos, truncado=False):
    """Publicaciones de un RSS 2.0, RSS 1.0 o Atom: [{titulo, url, fecha, resumen, extra}].

    Tolera los defectos habituales sin cambiar el contenido: espacios o BOM antes de la declaración XML, caracteres de
    control y «&» sin escapar. Una página HTML no es un feed (se informa para buscar el feed declarado en el sitio)."""
    datos = datos.lstrip(b"\xef\xbb\xbf\r\n\t ")
    inicio = datos[:600].lower()
    if inicio.startswith(b"<!doctype html") or b"<html" in inicio:
        raise ErrorLectura("La dirección devuelve una página web, no un feed.", "html", html=datos)
    try:
        return _parsear(datos, truncado)
    except ErrorLectura:
        raise
    except ET.ParseError:
        pass
    limpio = RE_AMP.sub(b"&amp;", RE_CONTROL.sub(b"", datos))
    try:
        return _parsear(limpio, truncado)
    except ET.ParseError as e:
        raise ErrorLectura(f"El feed tiene XML inválido que no se puede corregir sin alterar el contenido ({e}).", "xml") from None


RE_LINK = re.compile(r"<link\b[^>]*>", re.I)


def feeds_declarados(html_bytes, base):
    """Feeds que la página declara con <link rel="alternate" type="application/rss+xml|atom+xml"> (estándar de autodescubrimiento)."""
    texto = html_bytes[:LIMITE_BYTES].decode("utf-8", "replace")
    res = []
    for tag in RE_LINK.findall(texto):
        attrs = {k.lower(): v for k, v in re.findall(r'([a-zA-Z-]+)\s*=\s*["\']([^"\']*)["\']', tag)}
        if "alternate" in attrs.get("rel", "").lower() and attrs.get("type", "").lower() in ("application/rss+xml", "application/atom+xml") and attrs.get("href"):
            href = urljoin(base, html.unescape(attrs["href"]))
            if "comment" in href.lower() or "comentario" in attrs.get("title", "").lower():
                continue
            res.append(href)
    return res


def descubrir(fuente, robots_cache, html_bytes=None, base=None):
    """Feed declarado por el sitio. Lee la página indicada (o la principal), respetando robots.txt."""
    paginas = [base] if html_bytes is not None and base else []
    if fuente.sitio_web:
        paginas.append(fuente.sitio_web)
        p = urlsplit(fuente.sitio_web)
        raiz = f"{p.scheme}://{p.netloc}/"
        if raiz != fuente.sitio_web:
            paginas.append(raiz)
    vistas = set()
    for pagina in paginas:
        if pagina in vistas:
            continue
        vistas.add(pagina)
        if html_bytes is not None and pagina == base:
            contenido = html_bytes
        else:
            ok, _m = robots_permite(pagina, robots_cache)
            if not ok:
                continue
            try:
                contenido = descargar(pagina)
            except ErrorLectura as e:
                contenido = e.parcial or b""
        for href in feeds_declarados(contenido, pagina):
            if href != fuente.url:
                return href, pagina
    return None, None


def leer_gdelt(consulta, cache=True):
    """Artículos de medios argentinos en español de los últimos 14 días (GDELT DOC 2.0, modo artlist), con caché de 12 horas."""
    from .models import CacheLectura
    q = f"{consulta} sourcecountry:argentina sourcelang:spanish"
    url = GDELT_API + "?" + urlencode({"query": q, "mode": "artlist", "format": "json", "maxrecords": "75", "timespan": "14d",
                                       "sort": "datedesc"})
    clave = "gdelt:" + hashlib.sha1(url.encode()).hexdigest()
    guardado = CacheLectura.objects.filter(clave=clave, expira__gt=timezone.now()).first() if cache else None
    if guardado:
        texto, desde_cache = guardado.datos, True
    else:
        _esperar_gdelt()
        try:
            datos = descargar(url, timeout=40, reintentos=0)
        except ErrorLectura as e:
            if e.codigo != 429:
                raise
            time.sleep(min(max(e.reintentar or 0, 30), 90))  # un único reintento, después de la espera que pida el servicio
            _esperar_gdelt()
            datos = descargar(url, timeout=40, reintentos=0)
        texto, desde_cache = datos.decode("utf-8", "replace").strip(), False
    if not texto or texto == "{}":
        arts = []
    else:
        try:
            arts = json.loads(texto).get("articles", [])
        except json.JSONDecodeError:
            raise ErrorLectura(f"GDELT respondió: {texto[:200]}", "gdelt") from None
    if not desde_cache:
        CacheLectura.objects.update_or_create(clave=clave, defaults={"datos": texto, "expira": timezone.now() + timedelta(hours=GDELT_CACHE_HORAS)})
    res = []
    for a in arts:
        dominio = (a.get("domain") or urlsplit(a.get("url", "")).netloc).removeprefix("www.")
        res.append({"titulo": texto_plano(a.get("title", ""), 300), "url": a.get("url", ""), "fecha": fecha(a.get("seendate")),
                    "resumen": "", "extra": {"dominio": dominio, "cache": desde_cache}})
    return res


_gdelt_ultimo = [0.0]
_gdelt_lock = threading.Lock()


def _esperar_gdelt():
    with _gdelt_lock:
        falta = _gdelt_ultimo[0] + GDELT_PAUSA - time.monotonic()
        if falta > 0:
            time.sleep(falta)
        _gdelt_ultimo[0] = time.monotonic()


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


def _leer_rss(fuente, robots_cache, notas):
    """Lee el feed; si no existe (404/410), devuelve una página web o falta la dirección, busca el feed que declara el sitio."""
    def bajar(url):
        ok, motivo = robots_permite(url, robots_cache)
        if not ok:
            raise ErrorLectura(motivo, "robots")
        try:
            return leer_feed(descargar(url))
        except ErrorLectura as e:
            if e.codigo == "grande" and e.parcial:
                notas.append("Feed de más de 3 MB: se leyeron sus primeras publicaciones sin superar el tope.")
                return leer_feed(e.parcial, truncado=True)
            raise

    if fuente.url:
        try:
            return bajar(fuente.url)
        except ErrorLectura as e:
            if not (e.codigo in (404, 410, "html", "xml") and fuente.sitio_web):
                raise
            nuevo, pagina = descubrir(fuente, robots_cache, e.html, fuente.url if e.html else None)
            if not nuevo:
                raise ErrorLectura(f"{e} El sitio no declara otro feed en su página.", e.codigo) from None
            anterior = fuente.url
    else:
        nuevo, pagina = descubrir(fuente, robots_cache)
        if not nuevo:
            raise ErrorLectura("El sitio no declara un feed RSS o Atom en su página (no se lee el HTML).", "sin_feed")
        anterior = ""
    items = bajar(nuevo)
    fuente.url, fuente.url_descubierta = nuevo, True
    notas.append(f"Feed encontrado en {pagina}" + (f" (la dirección anterior, {anterior}, no funcionaba)." if anterior else "."))
    return items


def leer(fuente, robots_cache, notas=None):
    """Publicaciones crudas de una fuente. Lanza ErrorLectura con el motivo si no se puede leer o no está permitido."""
    notas = notas if notas is not None else []
    if fuente.metodo in ("rss", "trends"):
        return _leer_rss(fuente, robots_cache, notas)
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
    return [x for x in terminos if re.search(r"(?<![\w-])" + re.escape(x) + r"(?![\w-])", t)]


def reglas(producto, linea=""):
    """(fuertes, débiles) del producto o de la línea."""
    if producto == "geagro":
        claves = [f"geagro:{linea}"] if linea else ["geagro:cereales", "geagro:vid"]
        return ([normalizar(x) for c in claves for x in RELEVANCIA[c]["fuertes"]], [normalizar(x) for c in claves for x in RELEVANCIA[c]["debiles"]])
    r = RELEVANCIA.get(producto, {"fuertes": [], "debiles": []})
    return [normalizar(x) for x in r["fuertes"]], [normalizar(x) for x in r["debiles"]]


def evaluar(titulo, resumen, producto, linea="", propios=None, filtrar=True, estricto=False, excluidos_extra=()):
    """(aceptada, puntaje, términos, motivo). Puntaje: término fuerte 4; general 2 en el título y 1 en el resumen. Umbral 4."""
    fuertes, debiles = reglas(producto, linea)
    if propios:
        fuertes = list(dict.fromkeys(_lista(propios) + fuertes))
    tn = normalizar(titulo)
    excl = coincidencias(f"{titulo} {resumen}", [normalizar(x) for x in EXCLUIR.get(producto, [])] + list(excluidos_extra))
    f_tit, f_res = coincidencias(titulo, fuertes), [x for x in coincidencias(resumen, fuertes)]
    if excl and not f_tit:
        return False, 0, [], f"Tema que no corresponde al producto: {', '.join(excl[:2])}."
    for patron in RUIDO.get(producto, []) + RUIDO["*"]:
        if re.search(patron, tn):
            return False, 0, [], "Serie repetitiva (precios o cierres del día): no aporta un tema para escribir."
    f_res = [x for x in f_res if x not in f_tit]
    d_tit = coincidencias(titulo, debiles)
    d_res = [x for x in coincidencias(resumen, debiles) if x not in d_tit]
    puntaje = 4 * (len(f_tit) + len(f_res)) + 2 * len(d_tit) + len(d_res)
    terminos = f_tit + f_res + d_tit + d_res
    if not filtrar:
        return True, max(puntaje, UMBRAL), terminos, ""
    if estricto and not (f_tit or len(f_res) >= 2):
        return False, puntaje, terminos, ("Medio general: hace falta un término fuerte del producto en el título" +
                                          (f" (solo tiene {', '.join(terminos[:3])})." if terminos else "."))
    if puntaje >= UMBRAL:
        return True, puntaje, terminos, ""
    if not terminos:
        return False, 0, [], "No menciona ningún término del producto."
    return False, puntaje, terminos, f"Solo términos generales ({', '.join(terminos[:3])}): puntaje {puntaje} de {UMBRAL}."


def clasificar(item, fuente, producto, excluidos_extra=()):
    """(aceptada, puntaje, términos, línea, motivo) de una publicación para un producto."""
    titulo, resumen = item["titulo"], item["resumen"]
    propios = fuente.terminos if fuente.terminos and fuente.producto != "todos" else None
    if producto == "geagro" and not fuente.linea:
        res = {l: evaluar(titulo, resumen, "geagro", l, propios, fuente.filtrar, fuente.estricto, excluidos_extra) for l in ("cereales", "vid")}
        mejor = max(res, key=lambda l: (res[l][0], res[l][1]))
        ok, puntaje, terminos, motivo = res[mejor]
        if ok and not terminos:  # fuente sin filtro y sin términos: no se puede asignar línea
            mejor = ""
        return ok, puntaje, terminos, (mejor if ok else ""), motivo
    ok, puntaje, terminos, motivo = evaluar(titulo, resumen, producto, fuente.linea, propios, fuente.filtrar, fuente.estricto, excluidos_extra)
    return ok, puntaje, terminos, fuente.linea, motivo


PALABRAS_VACIAS = set("para como cual cuales cuando desde donde esta este estos estas entre hasta hacia pero porque sobre tras "
                      "todo todos toda todas tiene tienen sera seran puede pueden segun durante ante contra con sin una uno unos unas "
                      "del las los que por mas muy hoy ayer".split())


def tokens(titulo):
    return {w for w in re.findall(r"\w{4,}", normalizar(titulo)) if w not in PALABRAS_VACIAS}


def similitud(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _url_normal(url):
    p = urlsplit(url.strip())
    qs = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    return urlunsplit(("https", p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), urlencode(qs), ""))


def huella(url):
    return "u:" + hashlib.sha1(_url_normal(url).encode()).hexdigest()[:24]


# ------------------------------------------------------------------------------------------------ Proceso
def _relacion(fuente, terminos):
    base = fuente.relacion.rstrip(".")
    if terminos:
        return f"{base}. Menciona: {', '.join(terminos[:4])}."[:300]
    return f"{base}."[:300]


class Vistos:
    """Lo ya guardado por sitio: enlaces normalizados y títulos (para no repetir la misma noticia entre feeds)."""

    def __init__(self):
        self.claves, self.titulos = set(), {}

    def agregar(self, sitio_id, clave, titulo, ident):
        self.claves.add((sitio_id, clave))
        self.titulos.setdefault(sitio_id, []).append((tokens(titulo), titulo, ident))

    def duplicado(self, sitio_id, clave, titulo):
        if (sitio_id, clave) in self.claves:
            return "Mismo enlace que una noticia ya guardada."
        t = tokens(titulo)
        for otros, otro_titulo, _ in self.titulos.get(sitio_id, []):
            if similitud(t, otros) >= SIMILAR:
                return f"Misma noticia que «{otro_titulo[:90]}»."
        return ""


def _muestra(it, motivo="", terminos=(), producto=""):
    return {"titulo": it["titulo"][:200], "url": it["url"][:300], "fecha": it["fecha"].date().isoformat() if it.get("fecha") else "",
            "motivo": motivo, "terminos": list(terminos)[:5], "producto": producto}


def _guardar(fuente, items, sitios, hoy, vistos, revision):
    """Crea las tarjetas nuevas. Devuelve (relacionadas, nuevas) y deja muestras en revision."""
    from sitios.models import LineaProducto
    from .models import IdeaEditorial, config_actual
    productos = ["geneos", "gerp", "geagro", "gema"] if fuente.producto == "todos" else [fuente.producto]
    relevantes = nuevas = 0
    desde = hoy - timedelta(days=DIAS_GUARDAR)
    for producto in productos:
        sitio = sitios.get(producto)
        if sitio is None:
            continue
        cfg = config_actual(sitio)
        excl_cfg = [normalizar(x) for x in (cfg.terminos_excluidos if cfg else [])]
        lineas = {l.clave: l for l in LineaProducto.objects.filter(sitio=sitio)}
        guardadas = 0
        for it in sorted(items, key=lambda i: i["fecha"], reverse=True):
            ok, puntaje, terminos, linea, motivo = clasificar(it, fuente, producto, excl_cfg)
            if fuente.producto == "todos" and not terminos:
                ok, motivo = False, motivo or "No menciona ningún término del producto."
            if not ok:
                if fuente.producto != "todos":
                    revision["descartadas"].append(_muestra(it, motivo, terminos, producto))
                continue
            relevantes += 1
            if it["fecha"].date() < desde:
                continue
            if guardadas >= POR_FUENTE:
                revision["descartadas"].append(_muestra(it, f"Supera el máximo de {POR_FUENTE} novedades por fuente en una lectura.", terminos, producto))
                continue
            clave = huella(it["url"]) if fuente.tipo != "tendencia" else f"trends:{normalizar(it['titulo'])}:{it['fecha']:%Y%m%d}"
            dup = vistos.duplicado(sitio.pk, clave, it["titulo"])
            if dup:
                revision["duplicadas"].append(_muestra(it, dup, terminos, producto))
                continue
            nombre_fuente = fuente.nombre
            if fuente.metodo == "gdelt":
                nombre_fuente = f"{it['extra'].get('dominio', '')} (vía GDELT)"
            elif fuente.metodo == "youtube":
                nombre_fuente = f"{it['extra'].get('canal') or fuente.organizacion} · YouTube"
            dato = it["extra"].get("trafico", "")
            idea = IdeaEditorial.objects.create(
                sitio=sitio, linea=lineas.get(linea), tipo=fuente.tipo, fuente_tipo=fuente.fuente_tipo, naturaleza=fuente.naturaleza,
                titulo=it["titulo"][:200], resumen=it["resumen"], relacion=_relacion(fuente, terminos), descripcion="",
                palabras_clave=", ".join(terminos)[:250] or it["titulo"][:250], fuente=nombre_fuente[:120],
                fuente_url=(url_trends(it["titulo"]) if fuente.tipo == "tendencia" else it["url"])[:600],
                publicado=it["fecha"].astimezone(timezone.get_current_timezone()).date(), consultado=hoy,
                dato=(f"{dato} búsquedas" if dato else "")[:60], intencion="Informativa", idioma=fuente.idioma, puntaje=min(puntaje, 999),
                menciona_normativa=bool(RE_NORMATIVA.search(normalizar(f"{it['titulo']} {it['resumen']}"))) and fuente.tipo == "noticia",
                prioritaria=fuente.prioritaria, fuente_actualidad=fuente, clave=clave[:200])
            vistos.agregar(sitio.pk, clave, it["titulo"], idea.pk)
            revision["aceptadas"].append(_muestra(it, f"Puntaje {puntaje}" + (f" · {linea}" if linea else ""), terminos, producto))
            guardadas += 1
            nuevas += 1
    return relevantes, nuevas


def _contar_relevantes(fuente, items):
    productos = ["geneos", "gerp", "geagro", "gema"] if fuente.producto == "todos" else [fuente.producto]
    n = 0
    for p in productos:
        for it in items:
            ok, _pu, terminos, _l, _m = clasificar(it, fuente, p)
            if ok and (terminos or fuente.producto != "todos"):
                n += 1
    return n


def procesar(fuente, items, error, sitios, hoy, vistos, notas=(), codigo=None):
    """Aplica los controles, registra el resultado en la fuente (con muestras) y, si está verificada, guarda lo nuevo."""
    ahora = timezone.now()
    fuente.ultima_lectura = ahora
    revision = {"fecha": ahora.isoformat(), "aceptadas": [], "descartadas": [], "duplicadas": [], "notas": list(notas)}
    if error:
        fuente.ultimo_error, fuente.tipo_error = error[:300], "tecnico"
        fuente.fallas_seguidas += 1
        if fuente.metodo == "gdelt" and codigo == 429 and fuente.fallas_seguidas >= GDELT_PAUSAR_TRAS:
            fuente.estado = "pausada"
            fuente.motivo = (f"Desactivada automáticamente: GDELT limitó los pedidos (429) en {fuente.fallas_seguidas} lecturas seguidas. "
                             "Se puede reanudar desde acá cuando haya una alternativa.")[:300]
        elif fuente.verificada is None:
            fuente.motivo = f"No pasó: {error}"[:300]
        revision["error"] = error
        fuente.revision = revision
        fuente.save()
        return {"ok": False, "motivo": error}
    fuente.fallas_seguidas = 0
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
    if validos and not recientes:
        motivo = f"Sin publicaciones en los últimos {DIAS_RECIENTE} días (la última es del {fuente.ultimo_item:%d/%m/%Y})."
    relevantes = nuevas = 0
    if not motivo and fuente.verificada is None and _contar_relevantes(fuente, recientes) == 0:
        motivo = f"Ninguna de las {len(recientes)} publicaciones recientes se relaciona con el producto."
        for it in recientes[:8]:
            ok, _p, terminos, _l, m = clasificar(it, fuente, fuente.producto if fuente.producto != "todos" else "gerp")
            revision["descartadas"].append(_muestra(it, m or "Sin relación con el producto.", terminos, fuente.producto))
    if not motivo:
        if fuente.verificada is None:
            fuente.verificada = ahora
            fuente.estado = "activa"
        relevantes, nuevas = _guardar(fuente, recientes, sitios, timezone.localdate(), vistos, revision)
    fuente.items_relevantes, fuente.items_nuevos = relevantes, nuevas
    for k in ("aceptadas", "descartadas", "duplicadas"):
        revision[k] = revision[k][:12]
    fuente.revision = revision
    if motivo:
        fuente.ultimo_error, fuente.tipo_error = motivo[:300], "calidad"
        if fuente.verificada is None:
            fuente.motivo = f"No pasó: {motivo}"[:300]
        fuente.save()
        return {"ok": False, "motivo": motivo, "leidos": len(items)}
    fuente.ultimo_ok, fuente.ultimo_error, fuente.tipo_error = ahora, "", ""
    nota = (" " + " ".join(notas)) if notas else ""
    fuente.motivo = (f"Verificada el {timezone.localtime(fuente.verificada):%d/%m/%Y}: accesible, permitida, con publicaciones fechadas "
                     f"y relacionadas. Última lectura: {len(items)} publicaciones, {relevantes} relacionadas, {nuevas} nuevas.{nota}")[:300]
    fuente.save()
    return {"ok": True, "leidos": len(items), "relevantes": relevantes, "nuevos": nuevas}


def reclasificar(forzar=False):
    """Vuelve a evaluar lo ya guardado (sin borrar nada) cuando cambian las reglas de relevancia: lo que no pasa queda
    «descartada» con el motivo, y las repeticiones de la misma noticia también. Se puede restaurar desde «Ver descartadas»."""
    from .models import CacheLectura, IdeaEditorial
    marca = CacheLectura.objects.filter(clave="relevancia:version").first()
    if marca and marca.datos == VERSION_RELEVANCIA and not forzar:
        return 0
    n = 0
    vistos = Vistos()
    qs = (IdeaEditorial.objects.filter(fuente_actualidad__isnull=False, estado="sugerida").select_related("fuente_actualidad", "sitio", "linea")
          .order_by("fuente_actualidad__linea", "-prioritaria", "publicado", "pk"))
    # primero las fuentes de una línea (definen la línea correcta) y lo más antiguo (la primera aparición)
    for i in sorted(qs, key=lambda x: (x.fuente_actualidad.linea == "", not x.prioritaria, x.publicado or x.consultado, x.pk)):
        f = i.fuente_actualidad
        item = {"titulo": i.titulo, "resumen": i.resumen}
        ok, puntaje, terminos, linea, motivo = clasificar(item, f, i.sitio.clave)
        if f.producto == "todos" and not terminos:
            ok = False
        dup = "" if not ok else vistos.duplicado(i.sitio_id, i.clave, i.titulo)
        if not ok or dup:
            i.estado, i.motivo_descarte = "descartada", ("Descartada al revisar la relevancia: " + (dup or motivo))[:300]
            i.save(update_fields=["estado", "motivo_descarte", "actualizada"])
            n += 1
            continue
        vistos.agregar(i.sitio_id, i.clave, i.titulo, i.pk)
        cambios = {"puntaje": min(puntaje, 999), "relacion": _relacion(f, terminos), "idioma": f.idioma}
        if f.producto == "geagro" and linea and (i.linea is None or i.linea.clave != linea):
            from sitios.models import LineaProducto
            cambios["linea"] = LineaProducto.objects.filter(sitio=i.sitio, clave=linea).first()
        for k, v in cambios.items():
            setattr(i, k, v)
        i.save(update_fields=list(cambios) + ["actualizada"])
    CacheLectura.objects.update_or_create(clave="relevancia:version", defaults={"datos": VERSION_RELEVANCIA, "expira": timezone.now() + timedelta(days=3650)})
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
    # Primero las fuentes de una línea y las oficiales: una noticia repetida queda con la línea y la fuente más precisas
    return sorted(qs, key=lambda f: (f.metodo == "gdelt", f.linea == "", f.naturaleza != "oficial", f.estricto, f.orden))


def actualizar_fuentes(origen="comando", usuario=None, claves=None):
    """Lee las fuentes en prueba y activas. Devuelve la ActualizacionActualidad, o None si ya había una lectura en curso."""
    from sitios.models import SitioWeb
    from .models import ActualizacionActualidad, IdeaEditorial
    if not tomar_cerrojo():
        return None
    act = ActualizacionActualidad.objects.create(origen=origen, usuario=usuario)
    try:
        reclasificar()
        fuentes = fuentes_a_leer(claves)
        sitios = {s.clave: s for s in SitioWeb.objects.all()}
        desde = timezone.localdate() - timedelta(days=DIAS_GUARDAR + 5)
        vistos = Vistos()
        for i in IdeaEditorial.objects.filter(consultado__gte=desde).exclude(tipo__in=("idea", "evento")).only("pk", "sitio_id", "clave", "titulo"):
            vistos.agregar(i.sitio_id, i.clave, i.titulo, i.pk)
        for sid, clave in IdeaEditorial.objects.filter(clave__startswith="u:").values_list("sitio_id", "clave"):
            vistos.claves.add((sid, clave))  # también las descartadas o viejas: no vuelven
        robots = {}

        def bajar(f):
            notas = []
            try:
                return f, leer(f, robots, notas), None, notas, None
            except ErrorLectura as e:
                return f, None, str(e), notas, e.codigo
            except Exception as e:  # noqa: BLE001 — una fuente rota no frena a las demás
                log.exception("Lectura de %s", f.clave)
                return f, None, f"Error inesperado: {e.__class__.__name__}", notas, None

        resultados = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            resultados += list(ex.map(bajar, [f for f in fuentes if f.metodo != "gdelt"]))
        limitado = False
        for f in [f for f in fuentes if f.metodo == "gdelt"]:
            if limitado:
                resultados.append((f, None, "No se consultó: GDELT limitó los pedidos en esta lectura (429).", [], 429))
                continue
            r = bajar(f)
            limitado = r[4] == 429
            resultados.append(r)
        detalle, ok, err, nuevos = {}, 0, 0, 0
        hoy = timezone.localdate()
        for f, items, error, notas, codigo in resultados:  # en el orden de fuentes_a_leer: primero las más precisas
            r = procesar(f, items or [], error, sitios, hoy, vistos, notas, codigo)
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
