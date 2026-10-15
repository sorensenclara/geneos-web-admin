"""Tendencias e ideas para publicar sin servicios pagos.

- Tendencias verificadas: se importan desde el CSV que exporta Google Trends (consultas relacionadas «principales» y «en aumento»).
  Se guarda el valor tal como figura en el archivo, con la fecha y la región de la consulta. Nada se calcula ni se estima.
- Ideas editoriales: surgen de los contenidos aprobados del sitio (funcionalidades, sectores, preguntas frecuentes, servicios)
  que todavía no tienen un artículo. No llevan datos de búsqueda y se muestran como tales.
- Ideas de IA: solo si se habilita un proveedor (editorial/ia.py). Siempre identificadas como «Idea de IA».
"""
import csv
import io
import re
import unicodedata
from datetime import date
from urllib.parse import quote

from django.utils import timezone

from contenidos.models import ArticuloPage, BlogIndexPage, Funcionalidad, PaginaWeb, PreguntaFrecuente, Sector
from sitios.models import LineaProducto

from .models import ConfigBlog, IdeaEditorial, ImportacionTendencias, config_actual, ruta_blog


def normalizar(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


def url_trends(termino, periodo="today 12-m"):
    """Consulta preparada en Google Trends (Argentina). Solo un enlace: no se lee la página."""
    return f"https://trends.google.com/trends/explore?geo=AR&hl=es&date={quote(periodo)}&q={quote(termino)}"


def _excluida(texto, config):
    t = normalizar(texto)
    return any(normalizar(x) in t for x in (config.terminos_excluidos if config else []))


def _articulos(sitio):
    if not sitio.site:
        return ArticuloPage.objects.none()
    return ArticuloPage.objects.descendant_of(sitio.site.root_page)


def _cubierto(termino, titulos):
    n = normalizar(termino)
    return any(n and n in t for t in titulos)


FAQ_COMERCIAL = re.compile(r"\b(precio|planes?|demo|empie|empez|cuesta|pago|abono|contrat|prueb|suscrib|desuscrib|baja|cancel|soporte|capacit|migr|cuanto|cuantos)")


def _intercalar(grupos):
    """Alterna fuentes (funcionalidad, sector, pregunta, página) para que una sola no ocupe todas las ideas."""
    res, grupos = [], [list(g) for g in grupos if g]
    while grupos:
        for g in grupos:
            res.append(g.pop(0))
        grupos = [g for g in grupos if g]
    return res


def candidatas_internas(sitio):
    """Temas que surgen de los contenidos aprobados del sitio. Devuelve dicts listos para IdeaEditorial."""
    hoy = timezone.localdate()
    res = []
    lineas = {l.pk: l for l in LineaProducto.objects.filter(sitio=sitio)}

    def enlace(linea_id, ancla=""):
        l = lineas.get(linea_id)
        return "/" + (l.ruta if l else "") + ancla

    for f in Funcionalidad.objects.filter(sitio=sitio, live=True, visible=True).order_by("grupo", "orden"):
        linea = lineas.get(f.linea_id)
        res.append(dict(clave=f"funcionalidad:{f.pk}", termino=f.etiqueta, linea_id=f.linea_id,
                        titulo=f"{f.etiqueta}: qué es y cómo organizarlo",
                        descripcion=f"Funcionalidad aprobada de {sitio.nombre}{' ' + linea.nombre if linea else ''} que todavía no tiene un artículo.",
                        fuente="Funcionalidades aprobadas", intencion="Informativa", enlace_comercial=enlace(f.linea_id), consultado=hoy))
    for s in Sector.objects.filter(sitio=sitio, live=True, visible=True):
        nombre = s.titulo or s.nombre
        if not nombre:
            continue
        res.append(dict(clave=f"sector:{s.pk}", termino=nombre, linea_id=s.linea_id,
                        titulo=f"{sitio.nombre} para {nombre[0].lower() + nombre[1:]}",
                        descripcion="Sector comercial aprobado sin ningún artículo que lo presente.",
                        fuente="Sectores aprobados", intencion="Comercial", enlace_comercial=enlace(s.linea_id), consultado=hoy))
    for q in PreguntaFrecuente.objects.filter(sitio=sitio, live=True, visible=True).order_by("ubicacion", "orden"):
        if FAQ_COMERCIAL.search(normalizar(q.pregunta)):
            continue  # condiciones comerciales (precio, prueba, baja…): no son temas de artículo
        res.append(dict(clave=f"faq:{q.pk}", termino=q.pregunta.strip("¿?"), linea_id=q.linea_id, titulo=q.pregunta,
                        descripcion="Pregunta frecuente publicada en la web: un artículo puede responderla con más detalle.",
                        fuente="Preguntas frecuentes aprobadas", intencion="Informativa", enlace_comercial="/" + (q.ubicacion or "") + "#faq", consultado=hoy))
    if sitio.motor == "institucional" and sitio.site:
        for p in PaginaWeb.objects.live().descendant_of(sitio.site.root_page).filter(depth__gt=sitio.site.root_page.depth + 1):
            res.append(dict(clave=f"pagina:{p.pk}", termino=p.title, linea_id=None, titulo=f"Novedades: {p.title}",
                            descripcion="Servicio publicado en la web de GENEOS sin noticias que lo acompañen.",
                            fuente="Páginas publicadas", intencion="Informativa", enlace_comercial="/" + (p.ruta_publica or ""), consultado=hoy))
    tipos = {}
    for c in res:
        tipos.setdefault(c["clave"].split(":")[0], []).append(c)
    return _intercalar(tipos.values())


def actualizar_ideas(sitio, maximo=12):
    """Agrega ideas editoriales nuevas (sin repetir las existentes ni las descartadas). Devuelve la cantidad agregada."""
    config = config_actual(sitio)
    titulos = [normalizar(t) for t in _articulos(sitio).values_list("title", flat=True)]
    existentes = set(IdeaEditorial.objects.filter(sitio=sitio).values_list("clave", flat=True))
    nuevas = 0
    for c in candidatas_internas(sitio):
        if nuevas >= maximo:
            break
        if c["clave"] in existentes or _cubierto(c["termino"], titulos) or _excluida(c["titulo"], config):
            continue
        IdeaEditorial.objects.create(sitio=sitio, linea_id=c["linea_id"], tipo="interna", titulo=c["titulo"][:160], descripcion=c["descripcion"],
                                     palabras_clave=c["termino"][:250], intencion=c["intencion"], fuente=c["fuente"],
                                     enlace_comercial=c["enlace_comercial"], consultado=c["consultado"], clave=c["clave"])
        nuevas += 1
    return nuevas


# ------------------------------------------------------------------------------------------------ CSV de Google Trends
SECCIONES_TRENDS = {"top": "principal", "principales": "principal", "rising": "en_aumento", "en aumento": "en_aumento",
                    "aumento": "en_aumento", "increasing": "en_aumento"}


class ErrorImportacion(Exception):
    pass


def leer_csv_trends(texto):
    """Consultas relacionadas de un CSV exportado de Google Trends. Devuelve [(consulta, seccion, valor_tal_cual)].

    Formatos: el clásico (líneas «TOP» / «RISING» o «PRINCIPALES» / «EN AUMENTO» seguidas de «consulta,valor») y el de dos columnas
    con encabezado (p. ej. «query,value»). Las líneas de categoría, vacías o de interés en el tiempo se ignoran."""
    texto = texto.lstrip("﻿")
    filas, seccion = [], "principal"
    encabezados = {"query", "consulta", "consultas", "search term", "término", "termino", "topic", "tema"}
    for row in csv.reader(io.StringIO(texto)):
        celdas = [c.strip() for c in row]
        if not any(celdas):
            continue
        primera = normalizar(celdas[0])
        if len(celdas) == 1 or not celdas[1]:
            if primera in SECCIONES_TRENDS:
                seccion = SECCIONES_TRENDS[primera]
            continue
        if primera in encabezados or primera.startswith(("categoria", "category", "semana", "week", "dia", "day", "mes", "month")):
            continue
        if re.match(r"^\d{4}-\d{2}(-\d{2})?$", celdas[0]):  # serie de interés en el tiempo: no es una consulta
            continue
        filas.append((celdas[0][:150], seccion, celdas[1][:60]))
    if not filas:
        raise ErrorImportacion("No se encontraron consultas relacionadas en el archivo. Exportá desde Google Trends el bloque "
                               "«Consultas relacionadas» (botón de descarga ⤓) y subí ese CSV.")
    return filas


def valor_legible(valor):
    v = valor.strip()
    return {"breakout": "Aumento puntual", "aumento puntual": "Aumento puntual"}.get(normalizar(v), v)


def importar_trends(sitio, texto, consultado, usuario=None, linea=None, termino="", region="Argentina", periodo="", archivo=""):
    filas = leer_csv_trends(texto)
    config = config_actual(sitio)
    imp = ImportacionTendencias.objects.create(sitio=sitio, linea=linea, termino=termino[:120], region=region[:60], periodo=periodo[:60],
                                               consultado=consultado, usuario=usuario, archivo=archivo[:200])
    creadas = descartadas = 0
    for consulta, seccion, valor in filas:
        if _excluida(consulta, config):
            descartadas += 1
            continue
        clave = f"trends:{normalizar(consulta)}"
        texto_dato = valor_legible(valor)
        desc = ("Consulta en aumento" if seccion == "en_aumento" else "Consulta principal") + \
               f" relacionada con «{termino or 'el término consultado'}» en {region}{(', ' + periodo) if periodo else ''}. Valor en el archivo: {texto_dato}."
        idea, nueva = IdeaEditorial.objects.update_or_create(
            sitio=sitio, clave=clave, tipo="verificada",
            defaults=dict(linea=linea, titulo=consulta[:160], descripcion=desc, palabras_clave=consulta[:250],
                          fuente="Google Trends (CSV)", fuente_url=url_trends(consulta), dato=texto_dato,
                          consultado=consultado, importacion=imp))
        if nueva:
            creadas += 1
    imp.filas = creadas
    imp.save(update_fields=["filas"])
    return imp, creadas, descartadas


# ------------------------------------------------------------------------------------------------ Borradores
def blog_general(sitio, crear=True):
    """Página del blog general del sitio (donde viven todos los artículos). Si no existe, se crea como borrador sin publicar."""
    if not sitio.site:
        return None
    root = sitio.site.root_page
    idx = BlogIndexPage.objects.descendant_of(root).filter(linea__isnull=True).first()
    if idx or not crear:
        return idx
    ruta = ruta_blog(sitio)
    c = config_actual(sitio)
    titulo = c.titulo if c else f"Blog de {sitio.nombre}"
    idx = BlogIndexPage(title=titulo, slug=ruta.strip("/"), ruta_publica=ruta, live=False, has_unpublished_changes=True)
    root.specific.add_child(instance=idx)
    idx.save_revision()
    return idx


ESQUEMA = [("h2", "Por qué importa: {tema}"), ("h2", "Cómo se resuelve en la práctica"), ("h3", "Paso a paso"),
           ("h3", "Errores frecuentes"), ("h2", "Cómo ayuda {producto}")]


def crear_borrador(idea, usuario):
    """Artículo en borrador a partir de una idea: sitio y línea elegidos, título, resumen propuesto, esquema H2/H3,
    fuentes y palabras clave. Queda para revisión humana; nunca se publica solo."""
    sitio = idea.sitio
    padre = blog_general(sitio)
    if padre is None:
        raise ValueError(f"{sitio.nombre} no tiene sitio de Wagtail asociado.")
    from django.utils.text import slugify
    base = slugify(idea.titulo)[:70].strip("-") or "articulo"
    slug, n = base, 2
    while padre.get_children().filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    tema = idea.titulo.rstrip(".")
    cuerpo = [("titulo", {"nivel": nivel, "texto": texto.format(tema=tema, producto=sitio.nombre)}) for nivel, texto in ESQUEMA]
    fuentes = f"{idea.get_tipo_display()} · {idea.fuente} · consultado el {idea.consultado:%d/%m/%Y}"
    if idea.dato:
        fuentes += f" · valor en la fuente: {idea.dato}"
    if idea.fuente_url:
        fuentes += f"\n{idea.fuente_url}"
    if not idea.verificada:
        fuentes += "\nSin datos de búsqueda: verificar el tema antes de escribir."
    art = ArticuloPage(title=idea.titulo[:255], slug=slug, live=False, has_unpublished_changes=True, owner=usuario,
                       resumen=f"Borrador para revisar: {tema}. Completar con información verificada sobre {sitio.nombre}."[:300],
                       fecha=timezone.localdate(), cuerpo=cuerpo, origen=idea.tipo, fuentes=fuentes, palabras_clave=idea.palabras_clave)
    padre.add_child(instance=art)
    if idea.linea_id:
        art.lineas = [idea.linea_id]
        art.save()
    art.save_revision(user=usuario, log_action=True)
    idea.estado, idea.articulo = "usada", art
    idea.save(update_fields=["estado", "articulo", "actualizada"])
    return art
