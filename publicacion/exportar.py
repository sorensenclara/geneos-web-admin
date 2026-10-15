"""Del administrador al generador: arma los datos JSON de cada sitio a partir del contenido aprobado.

El formato es el mismo que ya usa el motor de sitios (renderer/data/*.json), así las plantillas no cambian.
`overrides` permite reemplazar un objeto por su borrador para generar una vista previa.
"""
import copy
import json
import re
from datetime import date
from pathlib import Path

from django.conf import settings
from django.utils.html import escape
from wagtail.models import Page
from wagtail.rich_text import expand_db_html

from contenidos.models import (ArticuloPage, BlogIndexPage, Funcionalidad, IdentidadSitio, PaginaWeb, Plan, PreguntaFrecuente, Redireccion, Sector,
                               Testimonio)

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
RENDERER = Path(settings.GWA_RENDERER_DIR)
CARPETAS = {"gerp": "gerp-web", "geagro": "geagro-web", "gema": "gema-web"}


def fecha_larga(d):
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}" if d else ""


def titulo_html(texto):
    """Renglones del título; **texto** queda resaltado con el color del sitio."""
    lineas = []
    for linea in (texto or "").strip().splitlines():
        linea = escape(linea.strip())
        if not linea:
            continue
        completa = re.fullmatch(r"\*\*(.+?)\*\*", linea)
        if completa:  # renglón entero resaltado
            lineas.append([completa.group(1), True])
        else:
            lineas.append([re.sub(r"\*\*(.+?)\*\*", r'<span class="pp-hl">\1</span>', linea), False])
    return lineas


class Fuente:
    """Contenido aprobado de un sitio, con los borradores de la vista previa encima."""

    def __init__(self, sitio, overrides=None):
        self.sitio = sitio
        self.files = []  # [origen absoluto, destino en assets/] que el generador copia al sitio
        self.over = {}
        for o in overrides or []:
            self.over[(o.__class__.__name__, o.pk)] = o

    def _aplicar(self, model, objetos):
        res = {o.pk: o for o in objetos}
        for (nombre, pk), o in self.over.items():
            if nombre == model.__name__ and getattr(o, "sitio_id", self.sitio.pk) == self.sitio.pk:
                res[pk or f"nuevo-{id(o)}"] = o
        return list(res.values())

    def snippets(self, model, **filtros):
        qs = model.objects.filter(sitio=self.sitio, **filtros)
        if hasattr(model, "live"):
            qs = qs.filter(live=True)
        return self._aplicar(model, qs)

    def paginas(self, model):
        site = self.sitio.site
        if site is None:
            return []
        qs = model.objects.live().descendant_of(site.root_page, inclusive=True)
        res = {p.pk: p for p in qs}
        for (nombre, pk), o in self.over.items():
            if nombre == model.__name__ and (pk is None or pk in res or Page.objects.filter(pk=pk).descendant_of(site.root_page, inclusive=True).exists()):
                res[pk or f"nuevo-{id(o)}"] = o
        return list(res.values())


# ------------------------------------------------------------------------------------------------ Bloques del blog
def video_embed(url):
    m = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([\w-]{6,})", url)
    if m:
        return f"https://www.youtube-nocookie.com/embed/{m.group(1)}"
    m = re.search(r"vimeo\.com/(\d+)", url)
    if m:
        return f"https://player.vimeo.com/video/{m.group(1)}"
    return None


def enlace_seguro(href):
    href = (href or "").strip()
    return href if re.match(r"^(https?://|/|#|mailto:)", href) else "#"


def imagen_archivo(img, spec, files):
    """Copia una versión optimizada (WebP) de la imagen a la web. Devuelve {src, alt, w, h} con src relativo a assets/."""
    r = img.get_rendition(spec)
    nombre = f"blog/{Path(r.file.name).name}"
    files.append([r.file.path, nombre])
    return {"src": nombre, "alt": img.description or img.title, "w": r.width, "h": r.height}


def cuerpo_html(stream, files):
    out = []
    for b in stream:
        t, v = b.block_type, b.value
        if t == "titulo":
            out.append(f"<{v['nivel']}>{escape(v['texto'])}</{v['nivel']}>")
        elif t == "parrafo":
            out.append(html_semantico(expand_db_html(v.source)))
        elif t == "destacado":
            out.append(f'<div class="pp-callout">{html_semantico(expand_db_html(v.source))}</div>')
        elif t == "imagen":
            im = imagen_archivo(v["imagen"], "width-1200|format-webp", files)
            alt = escape(v.get("alt") or im["alt"])
            pie = f"<figcaption>{escape(v['pie'])}</figcaption>" if v.get("pie") else ""
            out.append(f'<figure><img src="__ASSETS__/{im["src"]}" alt="{alt}" width="{im["w"]}" height="{im["h"]}" loading="lazy">{pie}</figure>')
        elif t == "cita":
            autor = f"<footer>{escape(v['autor'])}</footer>" if v.get("autor") else ""
            out.append(f"<blockquote><p>{escape(v['texto'])}</p>{autor}</blockquote>")
        elif t == "tabla":
            data = v.get("data") or []
            cab = v.get("first_row_is_table_header")
            filas = []
            for i, fila in enumerate(data):
                tag = "th" if cab and i == 0 else "td"
                filas.append("<tr>" + "".join(f"<{tag}>{escape(c or '')}</{tag}>" for c in fila) + "</tr>")
            out.append(f'<div class="pp-table-wrap"><table>{"".join(filas)}</table></div>')
        elif t == "boton":
            out.append(f'<a class="pp-btn pp-btn-primary" href="{escape(enlace_seguro(v["enlace"]))}">{escape(v["texto"])}</a>')
        elif t == "video":
            src = video_embed(v)
            out.append(f'<div class="pp-video"><iframe src="{escape(src)}" title="Video" loading="lazy" allowfullscreen></iframe></div>' if src
                       else f'<p><a href="{escape(enlace_seguro(v))}">Ver video</a></p>')
    return "\n".join(out)


# ------------------------------------------------------------------------------------------------ Datos por sitio
def contacto(sitio):
    return {"whatsapp": sitio.whatsapp, "whatsapp_label": sitio.whatsapp_visible, "phone": sitio.telefono, "email": sitio.email}


def datos_paginas(fuente, faqs_por_ruta, excluir_faqs=()):
    pages = {}
    for p in fuente.paginas(PaginaWeb):
        d = {}
        if p.seo_title:
            d["title"] = p.seo_title
        if p.search_description:
            d["description"] = p.search_description
        if not p.indexar:
            d["robots"] = "noindex, follow"
        hero = {}
        if p.hero_titulo.strip():
            hero["title"] = titulo_html(p.hero_titulo)
        if p.hero_bajada.strip():
            hero["lead"] = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escape(p.hero_bajada.strip()))
        acciones = [{"label": escape(p.boton1_texto), "href": p.boton1_enlace}, {"label": escape(p.boton2_texto), "href": p.boton2_enlace}]
        if any(a["label"] or a["href"] for a in acciones):
            hero["actions"] = acciones
        if hero:
            d["hero"] = hero
        if p.secciones_ocultas:
            d["hidden"] = list(p.secciones_ocultas)
        pages[p.ruta_publica] = d
    for ruta, items in faqs_por_ruta.items():
        if ruta not in excluir_faqs:
            pages.setdefault(ruta, {})["faqs"] = items
    return pages


def con_precios(texto, planes):
    """[precio:lite], [implementacion:lite] y [vigencia:lite] se reemplazan por los datos vigentes del plan
    (importe con moneda e IVA: «$89.250 + IVA»).
    Así una respuesta que menciona precios se actualiza sola cuando cambian."""
    idx = {}
    for p in planes:
        idx[p.clave.lower()] = p
        idx.setdefault(p.nombre.lower(), p)

    def rep(m):
        p = idx.get(m.group(2).strip().lower())
        if p is None:
            return m.group(0)
        if m.group(1) == "vigencia":
            return p.leyenda_vigencia
        return p.importe(p.precio if m.group(1) == "precio" else p.implementacion)
    return re.sub(r"\[(precio|implementacion|vigencia):([^\]]+)\]", rep, texto)


def html_semantico(html):
    """El editor de Wagtail guarda <b>/<i>; la web usa <strong>/<em> como hasta ahora."""
    for a, b in (("b", "strong"), ("i", "em")):
        html = html.replace(f"<{a}>", f"<{b}>").replace(f"</{a}>", f"</{b}>")
    return html


def enlaces_internos(html):
    """Enlaces a rutas del propio sitio (/cereales/) → __RAIZ__/cereales/; el generador los hace relativos a cada página."""
    return re.sub(r'href="/(?!/)', 'href="__RAIZ__/', html)


def faqs(fuente):
    res = {}
    planes = fuente.snippets(Plan)
    for f in sorted(fuente.snippets(PreguntaFrecuente), key=lambda x: (x.ubicacion, x.orden, x.pk or 0)):
        if f.visible:
            res.setdefault(f.ubicacion, []).append([con_precios(f.pregunta, planes), enlaces_internos(html_semantico(con_precios(expand_db_html(f.respuesta), planes)))])
    return res


def datos_blog(fuente, files):
    sitio = fuente.sitio
    if not sitio.usa_blog:
        return {}
    indices = fuente.paginas(BlogIndexPage)
    if not indices:
        return {}
    articulos = [a for a in fuente.paginas(ArticuloPage) if a.fecha]
    por_padre = {}
    for a in articulos:
        por_padre.setdefault(a.get_parent().pk, []).append(a)
    lineas = {i.pk: i for i in indices}

    def tarjeta(a, incluir_img=True):
        padre = lineas.get(a.get_parent().pk)
        return {"path": a.ruta, "title": a.title, "summary": a.resumen, "date": a.fecha.isoformat(), "date_label": fecha_larga(a.fecha),
                "line_label": padre.linea.nombre if padre and padre.linea else "",
                "image": imagen_archivo(a.imagen, "fill-1200x675|format-webp", files) if (incluir_img and a.imagen) else None,
                "categories": [c.nombre for c in a.categorias.all()] if a.pk else [],
                "schema": {"@type": "BlogPosting", "headline": a.title, "datePublished": a.fecha.isoformat(), "url": (sitio.dominio_publico + "/" + a.ruta) if sitio.dominio_publico else "/" + a.ruta}}

    posts, idx = [], []
    for i in indices:
        propios = por_padre.get(i.pk, [])
        incluidos = list(propios)
        if i.reune_lineas:
            for otro in indices:
                if otro.pk != i.pk:
                    incluidos += por_padre.get(otro.pk, [])
        incluidos.sort(key=lambda a: a.fecha, reverse=True)
        filtros = []
        if i.reune_lineas:
            filtros = [("Todos", "/" + i.ruta_publica, True)] + [(o.linea.nombre, "/" + o.ruta_publica, False) for o in indices if o.pk != i.pk and o.linea]
        elif i.linea:
            general = [o for o in indices if o.reune_lineas]
            if general:
                filtros = [("Todos", "/" + general[0].ruta_publica, False), (i.linea.nombre, "/" + i.ruta_publica, True)]
        cards = [tarjeta(a) for a in incluidos]
        n = max(1, i.articulos_por_pagina)
        grupos = [cards[k:k + n] for k in range(0, len(cards), n)] or [[]]
        for num, grupo in enumerate(grupos, 1):
            ruta = i.ruta_publica if num == 1 else f"{i.ruta_publica}pagina/{num}/"
            idx.append({"path": ruta, "title": i.title, "intro": i.intro, "posts": grupo, "filters": filtros,
                        "pages": [(k, "/" + (i.ruta_publica if k == 1 else f"{i.ruta_publica}pagina/{k}/"), k == num) for k in range(1, len(grupos) + 1)],
                        "seo_title": i.seo_title or f"{i.title} | {sitio.nombre}", "description": i.search_description or i.intro or f"Artículos de {sitio.nombre}",
                        "robots": "noindex, follow" if (not i.indexar or num > 1) else None})
        for a in propios:
            rel = list(a.relacionados.all()) if a.pk else []
            if not rel:
                cats = set(a.categorias.values_list("pk", flat=True)) if a.pk else set()
                rel = [b for b in incluidos if b.pk != a.pk and cats & set(b.categorias.values_list("pk", flat=True))][:3]
            d = tarjeta(a)
            d.update({"author": a.autor, "body_html": cuerpo_html(a.cuerpo, files), "index_path": i.ruta_publica, "index_title": i.title,
                      "tags": [t.name for t in a.tags.all()] if a.pk else [],
                      "related": [tarjeta(b, incluir_img=False) for b in rel if b.live],
                      "seo_title": a.seo_title or f"{a.title} | {sitio.nombre}", "description": a.search_description or a.resumen,
                      "robots": None if a.indexar else "noindex, follow"})
            d["schema"] = dict(d["schema"], **{"@context": "https://schema.org", "description": a.resumen, "author": {"@type": "Organization", "name": a.autor or "GENEOS"},
                                               "publisher": {"@type": "Organization", "name": "Cooperativa GENEOS"}})
            posts.append(d)
    return {"indexes": idx, "posts": posts}


def valor_funcionalidad(v):
    return {"incluido": True, "no_incluido": False, "a_confirmar": None, "opcional": "Opcional"}.get(v.estado, v.texto or None)


def datos_gerp(fuente, faqs_por_ruta):
    """gerp.json: parte de la base del motor y reemplaza lo que se administra acá."""
    base = json.loads((RENDERER / "data" / "gerp.json").read_text())
    sitio = fuente.sitio
    planes = {p.clave: p for p in fuente.snippets(Plan)}
    nuevos = []
    for item in base["plans"]:
        p = planes.get(item["key"])
        if p is None:
            nuevos.append(item)
            continue
        if not p.visible:
            continue
        item = dict(item)
        item.update({"name": p.nombre, "label": p.etiqueta or item.get("label"), "price": p.precio, "price_num": p.precio_num, "impl": p.implementacion,
                     "currency": p.simbolo, "currency_code": p.moneda, "iva": p.mas_iva, "validity": p.leyenda_vigencia,
                     "featured": p.destacado, "short": p.publico_corto or item.get("short"), "audience": p.publico or item.get("audience")})
        if p.caracteristicas.strip():
            item["card_feats"] = [x.strip() for x in p.caracteristicas.splitlines() if x.strip()]
        if p.ruta:
            item["slug"] = p.ruta
        if p.titulo_landing.strip():
            item["h1"] = [x.strip() for x in p.titulo_landing.splitlines() if x.strip()]
        for campo, clave in [("titulo_seo", "title"), ("descripcion_seo", "description"), ("color", "color"), ("color_acento", "accent"),
                             ("color_hover", "hover"), ("color_suave", "soft"), ("icono", "icon"), ("logo_blanco", "logo_white"), ("nota_funciones", "functions_note")]:
            if getattr(p, campo):
                item[clave] = getattr(p, campo)
        for campo, clave, prefijo in (("icono_img", "icon", "img/"), ("logo_blanco_img", "logo_white", "")):
            img = getattr(p, campo)
            if img and img.file:
                src, nombre, _w, _h = preparar_imagen(sitio, img, f"plan-{p.clave}-{campo.replace('_img', '').replace('_', '-')}")
                fuente.files.append([src, f"img/identidad/{nombre}"])
                item[clave] = f"{prefijo}identidad/{nombre}"
        if p.color:
            c = p.color.lstrip("#")
            item["deep_rgb"] = ", ".join(str(int(c[i:i + 2], 16)) for i in (0, 2, 4))
        if len(p.modulos):
            item["modules"] = [{"icon": m.value["icono"], "title": m.value["titulo"], "text": m.value["texto"]} for m in p.modulos]
        if len(p.funciones):
            item["functions"] = [{"icon": g.value["icono"], "title": g.value["titulo"], "checks": [[x["titulo"], x["texto"]] for x in g.value["items"]]} for g in p.funciones]
        ruta = item.get("slug", "")
        if ruta in faqs_por_ruta:
            item["faqs"] = faqs_por_ruta[ruta]
        nuevos.append(item)
    base["plans"] = sorted(nuevos, key=lambda it: next((planes[it["key"]].orden for _ in [0] if it["key"] in planes), 99))
    claves = {p["key"] for p in base["plans"]}
    funcs = sorted((f for f in fuente.snippets(Funcionalidad) if f.visible), key=lambda f: (f.grupo != "basic", f.orden))
    if funcs:
        base["features"] = []
        for f in funcs:
            valores = {v.plan.clave: valor_funcionalidad(v) for v in f.valores.all() if v.plan.clave in claves}
            base["features"].append({"group": f.grupo, "label": f.etiqueta, "summary": f.resumen, "values": {k: valores.get(k) for k in claves}})
    sectores = fuente.snippets(Sector)
    if sectores:
        base["sectors"] = [{"icon": s.icono, "title": s.titulo, "text": s.texto} for s in sorted(sectores, key=lambda s: s.orden)]
    base["testimonials"] = [{"company": t.empresa, "publish": True, "text": t.texto} for t in fuente.snippets(Testimonio) if t.publicable]
    reds = fuente.snippets(Redireccion)
    if reds:
        base["redirects"] = [[r.origen, r.destino] for r in reds]
    # Leyenda de vigencia: la de los planes visibles (vacía = no se muestra)
    base["price_note"] = " ".join(dict.fromkeys(p.leyenda_vigencia for p in planes.values() if p.visible and p.leyenda_vigencia))
    return base


# ------------------------------------------------------------------------------------------------ Identidad visual
def _cache_identidad(sitio):
    d = Path(settings.GWA_VAR_DIR) / "identidad" / sitio.clave
    d.mkdir(parents=True, exist_ok=True)
    return d


def _medidas_svg(ruta):
    t = Path(ruta).read_text(errors="ignore")[:4000]
    m = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', t)
    if m:
        return round(float(m.group(1))), round(float(m.group(2)))
    w, h = re.search(r'width="([\d.]+)', t), re.search(r'height="([\d.]+)', t)
    return (round(float(w.group(1))), round(float(h.group(1)))) if w and h else (300, 100)


def preparar_imagen(sitio, imagen, nombre):
    """Copia un logo o ícono del administrador al sitio. SVG tal cual; PNG/JPG se convierten a WebP.
    Devuelve (ruta absoluta, nombre de archivo, ancho, alto). El nombre lleva una huella del archivo: si cambia, cambia la URL."""
    import hashlib
    origen = Path(imagen.file.path)
    huella = hashlib.sha1(origen.read_bytes()).hexdigest()[:8]
    if origen.suffix.lower() == ".svg":
        w, h = _medidas_svg(origen)
        return str(origen), f"{nombre}-{huella}.svg", w, h
    from PIL import Image
    destino = _cache_identidad(sitio) / f"{nombre}-{huella}.webp"
    with Image.open(origen) as im:
        w, h = im.size
        if not destino.exists():
            im.save(destino, "WEBP", quality=92, method=6)
    return str(destino), destino.name, w, h


def preparar_favicons(sitio, ident):
    """Juego completo de favicons a partir de la imagen cargada (PNG cuadrado ≥ 512 px) y del SVG opcional.
    Parte del juego actual del sitio, así lo que no se carga queda como estaba."""
    import hashlib, shutil
    from PIL import Image
    base = RENDERER / "favicons" / sitio.clave
    partes = [ident.favicon.file.path if ident.favicon else "", ident.favicon_svg.file.path if ident.favicon_svg else ""]
    huella = hashlib.sha1("".join(Path(p).read_bytes().hex()[:4000] + str(Path(p).stat().st_size) if p else "-" for p in partes).encode()).hexdigest()[:10]
    d = _cache_identidad(sitio) / f"favicons-{huella}"
    if d.exists():
        return str(d)
    tmp = d.with_name(d.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(base, tmp)
    if ident.favicon:
        with Image.open(ident.favicon.file.path) as im:
            im = im.convert("RGBA")
            lado = max(im.size)
            cuadro = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
            cuadro.paste(im, ((lado - im.width) // 2, (lado - im.height) // 2))
            for nombre, px in (("favicon-16x16.png", 16), ("favicon-32x32.png", 32), ("apple-touch-icon.png", 180),
                               ("android-chrome-192x192.png", 192), ("android-chrome-512x512.png", 512)):
                icono = cuadro.resize((px, px), Image.LANCZOS)
                if nombre == "apple-touch-icon.png":  # iOS no usa transparencia: fondo blanco
                    fondo = Image.new("RGBA", icono.size, (255, 255, 255, 255)); fondo.alpha_composite(icono); icono = fondo.convert("RGB")
                icono.save(tmp / nombre, optimize=True)
            cuadro.save(tmp / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    if ident.favicon_svg:
        shutil.copy2(ident.favicon_svg.file.path, tmp / "favicon.svg")
    elif ident.favicon and (tmp / "favicon.svg").exists():
        (tmp / "favicon.svg").unlink()  # el SVG anterior taparía al favicon nuevo en los navegadores que prefieren SVG
    manifest = json.loads((base / "site.webmanifest").read_text())
    manifest["name"] = manifest.get("name") or sitio.nombre
    (tmp / "site.webmanifest").write_text(json.dumps(manifest, ensure_ascii=False))
    tmp.rename(d)
    return str(d)


def datos_identidad(fuente, files):
    """Logos y favicon cargados en «Logos y favicon». Vacío: el sitio conserva los actuales."""
    sitio = fuente.sitio
    lista = fuente.snippets(IdentidadSitio)
    ident = lista[0] if lista else None
    if ident is None:
        return {}
    res = {}
    for campo, clave in (("logo", "header_logo"), ("logo_blanco", "logo")):
        img = getattr(ident, campo)
        if img and img.file:
            src, nombre, w, h = preparar_imagen(sitio, img, f"{sitio.clave}-{campo.replace('_', '-')}")
            files.append([src, f"img/identidad/{nombre}"])
            res.update({clave: f"identidad/{nombre}", f"{clave}_w": w, f"{clave}_h": h})
    if ident.favicon or ident.favicon_svg:
        res["favicons"] = preparar_favicons(sitio, ident)
    return res


def datos_sitio(sitio, overrides=None):
    """Devuelve {"contacto.json": ..., "<clave>.json": ..., ["gerp.json": ...]} y la lista de archivos a copiar."""
    fuente = Fuente(sitio, overrides)
    files = fuente.files
    fq = faqs(fuente)
    rutas_planes = {p.ruta for p in fuente.snippets(Plan) if p.ruta} if sitio.clave == "gerp" else set()
    pd = {"domain": sitio.dominio_publico, "pages": datos_paginas(fuente, fq, excluir_faqs=rutas_planes), "files": files}
    if sitio.clave in ("geagro", "gema"):
        pd["plans"] = [{"name": p.nombre, "price": p.precio, "num": p.precio_num, "impl": p.implementacion, "hidden": not p.visible,
                        "currency": p.simbolo, "currency_code": p.moneda, "iva": p.mas_iva, "validity": p.leyenda_vigencia}
                       for p in fuente.snippets(Plan)]
    pd["blog"] = datos_blog(fuente, files)
    pd["identity"] = datos_identidad(fuente, files)
    if sitio.usa_formularios:
        pd["form"] = {"endpoint": settings.GWA_URL_PUBLICA.rstrip("/") + "/api/formularios/demo", "site": sitio.clave, "privacy": sitio.texto_consentimiento}
    archivos = {"contacto.json": contacto(sitio), f"{sitio.clave}.admin.json": pd}
    if sitio.clave == "gerp":
        archivos["gerp.json"] = datos_gerp(fuente, fq)  # planes, comparador, sectores, testimonios, redirecciones
    return archivos, files
