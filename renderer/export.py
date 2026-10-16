"""Exporta los sitios comerciales (GERP, GEAGRO, GEMA) como sitios estáticos independientes.

Renderiza las plantillas comerciales con una base propia (header blanco con el logo a color,
footer del producto), copia solo los recursos usados y deja rutas relativas, para que cada
carpeta funcione sola. GEAGRO tiene tres páginas (inicio, /cereales/, /vid/) y conserva las
URL de recursos del sitio publicado en geagro.ar (imágenes, PDF, favicons).

Datos editables (una sola fuente para home, landings, comparador, formularios y footer):
  data/contacto.json  WhatsApp, teléfono y email de los tres sitios
  data/gerp.json      planes, precios, módulos, funcionalidades, comparador, sectores, testimonios y redirecciones de GERP

Uso (desde la carpeta GENEOS WEB, con el sitio de GENEOS construido: python3 build.py):
  python3 tools/sitios-comerciales/export.py gerp            # regenera ../gerp-web
  python3 tools/sitios-comerciales/export.py                 # los tres sitios
Opciones: --out <carpeta donde están gerp-web, geagro-web y gema-web> (por defecto, la carpeta que contiene GENEOS WEB)
          --geagro-src <carpeta del sitio publicado de GEAGRO> (recursos que conservan su URL)
"""
import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

import os
HERE = Path(__file__).resolve().parent
# GENEOS WEB (plantillas base, build.py y recursos ya construidos en public/). Solo se lee, nunca se modifica.
GENEOS = Path(os.environ.get("GENEOS_WEB_DIR") or HERE.parents[1]).resolve()
_ap = argparse.ArgumentParser(description="Exporta los sitios comerciales de GENEOS")
_ap.add_argument("products", nargs="*", help="gerp, geagro, gema (por defecto, todos)")
_ap.add_argument("--out", default=str(GENEOS.parent))
_ap.add_argument("--geagro-src", default=os.environ.get("GEAGRO_SRC_DIR") or str(Path.home() / "Documents/geagro_clean/GEAGRO Geneos : Imagen de marca/GEAGRO WEB 2026"))
_ap.add_argument("--no-project-files", action="store_true", help="no escribir README, workflow ni CNAME (exportación desde el administrador)")
ARGS = _ap.parse_args()
OUTROOT = Path(ARGS.out).resolve()
GEAGRO_SRC = Path(ARGS.geagro_src)
# Datos editables: el administrador los entrega en WEB_DATA_DIR; si no, se usan los de renderer/data/
DATA = Path(os.environ.get("WEB_DATA_DIR") or HERE / "data")
CONTACT = json.loads((DATA / "contacto.json").read_text())
GERP_DATA = json.loads(((DATA / "gerp.json") if (DATA / "gerp.json").exists() else HERE / "data/gerp.json").read_text())


def product_data(key):
    """Datos del administrador para un sitio (páginas, FAQ, planes, blog, formularios). Vacío si no hay."""
    f = DATA / f"{key}.admin.json"
    return json.loads(f.read_text()) if f.exists() else {}
sys.path.insert(0, str(GENEOS))
import build as B  # noqa: E402
sys.path.insert(0, str(HERE))
from project_files import write_project_files  # noqa: E402
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape  # noqa: E402

PUB = GENEOS / "public"  # sitio GENEOS ya construido (fuente de los recursos optimizados)

# Desplegable «Planes» de GERP: una página por plan y las tarjetas de la home
GERP_PLANES_MENU = [(q["label"], "/" + q["slug"]) for q in GERP_DATA["plans"]] + [("Ver todos los planes", "/#planes")]

# Versión de site.css, site.js y formulario.js (huella del contenido): al cambiar el archivo cambia la URL
# y el navegador no usa una copia vieja guardada en caché.
import hashlib  # noqa: E402
VERSION_ESTATICOS = {f.name: hashlib.sha1(f.read_bytes()).hexdigest()[:10] for f in (HERE / "static").rglob("*") if f.is_file()}

PRODUCTS = {
    "gerp": dict(
        folder="gerp-web", name="GERP", domain="https://gerp.ar",
        pages=[dict(tpl="gerp.html", out="",
                    title="GERP | Software de gestión ERP para pymes basado en Odoo",
                    description="GERP: sistema de gestión online basado en Odoo para pymes. Inventario, compras, ventas, facturación y contabilidad. Planes, precios y demo.",
                    og="img/og/gerp.jpg",
                    nav=[("Cómo funciona", "#como-funciona"), ("Módulos", "#modulos"), ("Planes", "", GERP_PLANES_MENU), ("Preguntas", "#faq")])]
              + [dict(tpl="gerp-plan.html", out=p["slug"], plan=p["key"], crumb=p["label"], title=p["title"], description=p["description"],
                      og="img/og/gerp.jpg",
                      nav=[("Qué incluye", "#incluye"), ("Planes", "", GERP_PLANES_MENU), ("Preguntas", "#faq")])
                 for p in GERP_DATA["plans"]],
        logo="productos/gerp-logo-blanco.svg", logo_w=296, logo_h=87,
        header_logo="2025/02/Isologo-GERP-Full.svg", header_logo_w=296, header_logo_h=87,
        footer_text="GERP es el software de gestión empresarial de GENEOS, basado en Odoo Community: inventario, compras, ventas, facturación y contabilidad en una sola plataforma online.",
        footer_pages=[("GERP · Inicio", "/")] + [(p["label"], "/" + p["slug"]) for p in GERP_DATA["plans"]] + [("Comparar planes", "/#comparar")],
        siblings=[("GEAGRO · Software agropecuario", "https://geagro.ar/")],
        redirects=GERP_DATA["redirects"],
    ),
    "geagro": dict(
        folder="geagro-web", name="GEAGRO", domain="https://geagro.ar",
        pages=[
            dict(tpl="geagro.html", out="", crumb="GEAGRO",
                 title="GEAGRO | Software de gestión agropecuaria: cereales y viñedos",
                 description="GEAGRO, software de gestión agropecuaria: campañas, lotes, clima, insumos y acopio con GEAGRO CEREALES, y gestión de viñedos con GEAGRO VID. Planes y demo.",
                 og="images/shared/og-image.jpg", og_alt="GEAGRO, software de gestión agropecuaria para cereales y viñedos",
                 nav=[("Cómo funciona", "#como-funciona"), ("Cereales", "/cereales/"), ("Vid", "/vid/"), ("Planes", "#planes"), ("Preguntas", "#faq")]),
            dict(tpl="geagro-cereales.html", out="cereales/", crumb="GEAGRO CEREALES",
                 title="GEAGRO CEREALES | Software de gestión agrícola para cereales",
                 description="Software de gestión agrícola para planificar campañas, controlar lotes, labores, insumos y costos, y seguir el acopio de granos. Por la Cooperativa GENEOS.",
                 og="images/cereales/og-cereales.jpg", og_alt="GEAGRO CEREALES, software de gestión agrícola para campañas, lotes y acopio",
                 nav=[("Qué incluye", "#incluye"), ("Cereales", "/cereales/"), ("Vid", "/vid/"), ("Planes", "/#planes"), ("Preguntas", "#faq")]),
            dict(tpl="geagro-vid.html", out="vid/", crumb="GEAGRO VID",
                 title="GEAGRO VID | Software para viñedos y gestión vitivinícola",
                 description="Software para la gestión de viñedos: clima, fenología y riesgos sanitarios por cuartel, plan técnico y labores del viñedo. Por la Cooperativa GENEOS.",
                 og="images/vid/og-vid.jpg", og_alt="GEAGRO VID, software de gestión de viñedos con alertas de clima y sanidad",
                 nav=[("Qué incluye", "#incluye"), ("Cereales", "/cereales/"), ("Vid", "/vid/"), ("Planes", "/#planes"), ("Preguntas", "#faq")]),
        ],
        logo="geagro/logo-geagro-white.svg", logo_w=300, logo_h=64,
        header_logo="geagro/logo-geagro.svg", header_logo_w=414, header_logo_h=88,
        favicons=True, local_fonts=True, website=True,
        footer_text="GEAGRO es el software de gestión agropecuaria de GENEOS para campañas agrícolas (CEREALES) y viñedos (VID).",
        footer_pages=[("GEAGRO · Inicio", "/"), ("GEAGRO CEREALES", "/cereales/"), ("GEAGRO VID", "/vid/"), ("Planes", "/#planes")],
        siblings=[("GERP · Software de gestión", "https://gerp.ar/")],
        # Recursos con la misma URL que en el sitio publicado (geagro.ar)
        path_map=[("geagro-landing/images/", "images/"), ("geagro-landing/icons/", "icons/"),
                  ("descargas/brochure-geagro-software-de-gestion-agropecuaria.pdf", "docs/Brochure-GEAGRO.pdf")],
        # Archivos del sitio publicado que se conservan tal cual (ruta relativa a la raíz)
        keep=["campo/index.html",
              "assets/docs/Brochure-GEAGRO-CEREALES.pdf", "assets/docs/Brochure-GEAGRO-VID.pdf",
              "assets/fonts/titillium-web-latin-400-normal.woff2", "assets/fonts/titillium-web-latin-600-normal.woff2",
              "assets/fonts/titillium-web-latin-700-normal.woff2", "assets/fonts/OFL-titillium-web.txt",
              "assets/images/shared/og-image.jpg", "assets/images/cereales/og-cereales.jpg", "assets/images/vid/og-vid.jpg",
              "assets/images/shared/hero-1920.avif", "assets/images/shared/hero-900.avif",
              "assets/images/cereales/campo-bg-1600.avif", "assets/images/cereales/campo-bg-900.avif", "assets/images/cereales/campo-bg-1600.webp",
              "assets/images/vid/vid-bg-1600.avif", "assets/images/vid/vid-bg-900.avif", "assets/images/vid/vid-bg-1600.webp",
              ],
        not_found_links=[("GEAGRO CEREALES", "/cereales/"), ("GEAGRO VID", "/vid/")],
    ),
    "gema": dict(
        folder="gema-web", name="GEMA", domain="",  # dominio comercial a definir
        pages=[dict(tpl="gema.html", out="",
                    title="GEMA | Software para talleres de matafuegos y extintores",
                    description="GEMA: plataforma online para talleres de recarga de matafuegos. Control de vencimientos, recargas, órdenes de trabajo, obleas y avisos a clientes. Planes y demo.",
                    og="img/og/gema.jpg",
                    nav=[("Cómo funciona", "#como-funciona"), ("Módulos", "#modulos"), ("Planes", "#planes"), ("Preguntas", "#faq")])],
        logo="productos/gema-logo-blanco.svg", logo_w=300, logo_h=84,
        header_logo="recursos/gema-logotipo.svg", header_logo_w=340, header_logo_h=95,
        footer_text="GEMA es la plataforma online de GENEOS para talleres de matafuegos: vencimientos, recargas, órdenes de trabajo y avisos a clientes.",
        siblings=[("GERP · Software de gestión", "https://gerp.ar/"), ("GEAGRO · Software agropecuario", "https://geagro.ar/")],
    ),
}

# Enlaces internos de GENEOS que aparecen dentro del contenido comercial
LINK_MAP = {
    "/software-de-gestion-completo/": "https://gerp.ar/",
    "/software-agropecuario-geagro/": "https://geagro.ar/",
}

CSS_URL = re.compile(r'url\("?\.\./([^")]+)"?\)')
# Fondos de sección: si existe la versión AVIF de una imagen, se ofrece primero (image-set) y queda el WebP de respaldo
BG_WEBP = re.compile(r"url\('\.\./([^']+)\.webp'\)")


# Contacto centralizado (data/contacto.json): pisa los datos de GENEOS en los tres sitios
SITE = dict(B.SITE, **{k: v for k, v in CONTACT.items() if not k.startswith("_")})
B.SITE.update(SITE)  # macros de GENEOS que leen SITE directamente (datos estructurados)


def wa(text=""):
    from urllib.parse import quote
    return f"https://wa.me/{SITE['whatsapp']}" + (f"?text={quote(text)}" if text else "")


def export(key, P):
    P = dict(P, key=key)
    PD = product_data(key)
    if PD.get("domain") is not None:
        P["domain"] = PD["domain"]
    if PD.get("siblings"):
        P["siblings"] = [tuple(x) for x in PD["siblings"]]
    # Títulos, descripciones e indexación de cada página (administrador)
    # Logos cargados en el administrador («Logos y favicon»)
    IDENT = PD.get("identity") or {}
    P["logo_original"] = P.get("logo")
    for k in ("header_logo", "header_logo_w", "header_logo_h", "logo", "logo_w", "logo_h"):
        if IDENT.get(k):
            P[k] = IDENT[k]
    if PD.get("redirects"):  # direcciones anteriores cargadas en el administrador (p. ej. un artículo que cambió de dirección)
        P["redirects"] = list(P.get("redirects") or []) + [tuple(r) for r in PD["redirects"]]
    BLOG = PD.get("blog") or {}
    MENU = BLOG.get("menu")

    def con_blog(nav):
        """Enlace «Blog» o «Noticias» en el menú (escritorio y celular), en la posición elegida en el administrador."""
        if not MENU:
            return nav
        nav = list(nav)
        pos = MENU.get("position") or 0
        item = (MENU["label"], MENU["href"])
        nav.insert(pos - 1 if 0 < pos <= len(nav) else len(nav), item)
        return nav

    if MENU and P.get("footer_pages"):
        P["footer_pages"] = list(P["footer_pages"]) + [(f'{P["name"]} · {MENU["label"]}', MENU["href"])]
    pages = []
    for pg in P["pages"]:
        o = (PD.get("pages") or {}).get(pg["out"], {})
        pg = dict(pg, **{k: v for k, v in o.items() if k in ("title", "description", "robots", "og_alt") and v})
        pg["nav"] = con_blog(pg["nav"])
        pages.append(pg)
    # Blog (portada, listados por línea y artículos)
    def raiz(href):
        return href if not href.startswith("#") else "/" + href
    home_nav = [(it[0], raiz(it[1])) + ((tuple((a, raiz(b)) for a, b in it[2]),) if len(it) > 2 else ()) for it in pages[0]["nav"]]
    for b in BLOG.get("indexes", []):
        pages.append(dict(tpl="blog-index.html", out=b["path"], crumb=b["title"], title=b["seo_title"], description=b["description"],
                          og=P["pages"][0]["og"], nav=home_nav, robots=b.get("robots"), sitemap=b.get("sitemap", True), blog=b))
    for a in BLOG.get("posts", []):
        pages.append(dict(tpl="blog-post.html", out=a["path"], crumb=a["title"], title=a["seo_title"], description=a["description"],
                          og=P["pages"][0]["og"], og_file=(a.get("og") or {}).get("src"), og_alt=(a.get("og") or {}).get("alt"),
                          og_type="article", canonical=a.get("canonical"), nav=home_nav, robots=a.get("robots"), post=a))
    P["pages"] = pages
    out = OUTROOT / P["folder"]
    out.mkdir(parents=True, exist_ok=True)
    for old in ("assets", "index.html", "404.html", "cereales", "vid", "campo", "favicon.ico", "lite", "core", "plus", "index.php", "REDIRECCIONES.md", "blog"):
        t = out / old
        if t.is_dir():
            shutil.rmtree(t)
        elif t.exists():
            t.unlink()
    used = {}  # destino (relativo a assets/) -> origen (relativo a public/assets/)
    path_map = P.get("path_map", [])
    paths = {pg["out"]: pg for pg in P["pages"]}

    def dest(path):
        for a, b in path_map:
            if path.startswith(a):
                return b + path[len(a):]
        return path

    def make_env(prefix):
        def asset(path):
            path = path.lstrip("/")
            d = dest(path)
            used[d] = path
            return prefix + "assets/" + d

        def img(path):
            p = Path(path)
            if p.suffix.lower() in (".png", ".jpg", ".jpeg"):
                p = p.with_suffix(".webp")
            return asset("img/" + p.as_posix())

        def url(path=""):
            if path.startswith(("http://", "https://", "mailto:", "tel:", "#")):
                return path
            if path.startswith("/assets/"):
                return asset(path[len("/assets/"):])
            base = path.split("#")[0]
            frag = path[len(base):]
            if base in LINK_MAP:
                return LINK_MAP[base] + frag
            return "https://geneos.coop.ar/" + path.lstrip("/")

        def page_url(path):
            """Enlace a otra página del mismo sitio ("" = inicio, "cereales/", "../#planes"…)."""
            if path.startswith("#"):
                return path
            base, _, frag = path.lstrip("/").partition("#")
            return (prefix + base or "./") + ("#" + frag if frag else "")

        def abs_url(path=""):
            root = P["domain"] or "https://geneos.coop.ar"
            return f"{root}/{path.lstrip('/')}"

        env = Environment(loader=ChoiceLoader([FileSystemLoader(HERE / "tpl"), FileSystemLoader(GENEOS / "templates")]),
                          autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
        env.filters["regex_replace"] = lambda v, pat, rep="": re.sub(pat, rep, v)
        page_over = {}

        def hero_data(h):
            """Título, bajada y botones del hero cargados en el administrador (si los hay)."""
            o = page_over.get("hero") or {}
            h = dict(h)
            if h.get("logo") and h["logo"] == P.get("logo_original") and P.get("logo") != P.get("logo_original"):
                h.update({"logo": P["logo"], "logo_w": P.get("logo_w") or h.get("logo_w"), "logo_h": P.get("logo_h") or h.get("logo_h")})
            if o.get("title"):
                h["title"] = [line if isinstance(line, list) else [line, False] for line in o["title"]]
            if o.get("lead"):
                h["lead"] = o["lead"]
            acts = [dict(a) for a in h.get("actions", [])]
            for i, a in enumerate(o.get("actions") or []):
                if i < len(acts):
                    acts[i].update({k: v for k, v in a.items() if v})
            h["actions"] = acts
            return h

        def faq_items(default):
            o = page_over.get("faqs")
            return [tuple(x) for x in o] if o else default

        def plans_data(default):
            o = {p["name"].lower(): p for p in (PD.get("plans") or [])}
            res = []
            for p in default:
                q = o.get(p["name"].lower())
                if q and q.get("hidden"):
                    continue
                res.append(dict(p, **{k: v for k, v in (q or {}).items() if k not in ("name", "hidden")}) if q else p)
            return res

        # Precios: moneda, IVA y leyenda de vigencia salen de cada plan (administrador). Sin datos: $, + IVA, ARS.
        def cur(p):
            return p.get("currency") or "$"

        def iva(p):
            return p.get("iva", True) is not False

        def currency_code(p):
            return p.get("currency_code") or "ARS"

        def importe(p, campo="price"):
            v = p.get(campo)
            return f"{cur(p)}{v}{' + IVA' if iva(p) else ''}" if v else ""

        def plans_note(plans):
            return " ".join(dict.fromkeys(p.get("validity") for p in plans if p.get("validity")))

        def show(section):
            return section not in (page_over.get("hidden") or [])

        fav_dir = Path((PD.get("identity") or {}).get("favicons") or HERE / "favicons" / key)
        env.globals.update(FAVICON_SVG=(fav_dir / "favicon.svg").exists(), V=VERSION_ESTATICOS, site=SITE, url=url, asset=asset, img=img, icon=B.icon, wa=wa, jsonld=B.jsonld, GERP=GERP_DATA,
                           DATA=PD, PAGE_OVER=page_over, hero_data=hero_data, faq_items=faq_items, plans_data=plans_data, show=show,
                           cur=cur, iva=iva, currency_code=currency_code, importe=importe, plans_note=plans_note,
                           FORM=PD.get("form"),
                           abs_url=abs_url, page_url=page_url, prefix=prefix, year=date.today().year, site_url="",
                           org_schema=B.org_schema, crumbs_schema=B.crumbs_schema, faq_entities=B.faq_entities,
                           service_items=B.service_items, pages={})
        return env, asset

    rendered = []
    for pg in P["pages"]:
        prefix = "../" * pg["out"].count("/")
        env, asset = make_env(prefix)
        env.globals["PAGE_OVER"].update((PD.get("pages") or {}).get(pg["out"], {}))
        if pg.get("og_file"):  # imagen para redes propia del artículo (la entrega el administrador)
            og_url = (P["domain"] or "https://geneos.coop.ar") + "/assets/" + pg["og_file"]
        else:
            og = pg["og"]
            og_url = (P["domain"] or "https://geneos.coop.ar") + "/assets/" + dest(og)
            asset(og)
        page = {"out": pg["out"], "crumb": pg.get("crumb", P["name"])}
        html = env.get_template(pg["tpl"]).render(P=P, PG=pg, page=page, title=pg["title"], description=pg["description"],
                                                  path="/" + pg["out"], canonical=pg.get("canonical") or env.globals["abs_url"](pg["out"]),
                                                  crumbs=[], og_image=og_url)
        # Las imágenes de fondo se pasan como variables CSS en style="": el navegador resuelve esas url()
        # relativas a la hoja de estilos que usa la variable (assets/css/), no a la página.
        html = html.replace(f"url('{prefix}assets/", "url('../")
        # Enlaces internos cargados en el administrador (__RAIZ__/ruta/): relativos a esta página
        html = re.sub(r'href="__RAIZ__/([^"]*)"', lambda m: f'href="{(prefix + m.group(1)) or "./"}"', html)
        rendered.append((pg, html))

    # Estilos y scripts del sitio
    for f in ("css/styles.css", "css/product.css", "js/main.js", "js/product.js"):
        used[f] = f
    for css in ("css/styles.css", "css/product.css"):
        for ref in CSS_URL.findall((PUB / "assets" / css).read_text()):
            used[ref] = ref
    if os.environ.get("GWA_LISTA_RECURSOS"):  # auditoría de assets: qué archivos de GENEOS WEB usa cada sitio
        with open(os.environ["GWA_LISTA_RECURSOS"], "a") as fh:
            for d, src in sorted(used.items()):
                fh.write(f"{key}\t{src}\t{d}\n")
    missing = []
    del_admin = {d for _src, d in PD.get("files", [])}
    for d, src in sorted(used.items()):
        if d in del_admin:
            continue
        s = PUB / "assets" / src
        if not s.exists() and (HERE / "assets" / key / d).exists():
            s = HERE / "assets" / key / d  # recursos propios del sitio comercial (tools/sitios-comerciales/assets/<sitio>/)
        if not s.exists():
            if not (HERE / "static" / d).exists() and not (key == "geagro" and (GEAGRO_SRC / "assets" / d).exists()):
                missing.append(src)
            continue
        t = out / "assets" / d
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, t)
    # Archivos entregados por el administrador (imágenes del blog, brochures): [origen absoluto, destino en assets/]
    for src, d in PD.get("files", []):
        t = out / "assets" / d
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, t)
    # Archivos propios de los sitios comerciales (site.css, site.js; blog.css y blog.js solo si el sitio tiene blog)
    for f in (HERE / "static").rglob("*"):
        if f.is_file() and (BLOG or not f.name.startswith("blog.")):
            t = out / "assets" / f.relative_to(HERE / "static")
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, t)
    # Favicons del producto
    fav = Path((PD.get("identity") or {}).get("favicons") or HERE / "favicons" / key)
    for f in fav.iterdir():
        t = out / ("favicon.ico" if f.name == "favicon.ico" else "assets/icons/favicon/" + f.name)
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, t)
    # Recursos conservados del sitio publicado
    for rel in P.get("keep", []):
        s = GEAGRO_SRC / rel
        t = out / rel
        if not s.exists():
            missing.append(f"(GEAGRO publicado) {rel}")
            continue
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, t)
    # AVIF para los fondos grandes que no lo tienen en el sitio publicado
    if P.get("keep"):
        from PIL import Image
        for rel in ("images/shared/cta-productor.webp", "images/backgrounds/bg-como-funciona.webp"):
            s = out / "assets" / rel
            a = s.with_suffix(".avif")
            if s.exists() and not a.exists():
                Image.open(s).save(a, "AVIF", quality=60, speed=4)

    def avif(m):
        rel = m.group(1)
        if (out / "assets" / (rel + ".avif")).exists():
            return f"image-set(url('../{rel}.avif') type('image/avif'), url('../{rel}.webp') type('image/webp'))"
        return m.group(0)

    for pg, html in rendered:
        html = BG_WEBP.sub(avif, html)
        f = out / pg["out"] / "index.html"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(html)

    # Direcciones anteriores: página con redirección inmediata + canónica + noindex (GitHub Pages no permite 301)
    rlines = []
    for old, new in P.get("redirects", []):
        target = P["domain"] + "/" + new.lstrip("/") if not new.startswith("#") else P["domain"] + "/" + new
        rel = "../" * old.count("/") + (new if not new.startswith("#") else new)
        f = out / old / "index.html"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f'<!doctype html>\n<html lang="es-AR"><head><meta charset="utf-8"><title>{P["name"]}</title>\n'
                     f'<!-- Dirección anterior. Con un servidor que permita redirecciones, reemplazar por un 301 (ver REDIRECCIONES.md). -->\n'
                     f'<meta name="robots" content="noindex, follow"><link rel="canonical" href="{target}">\n'
                     f'<meta http-equiv="refresh" content="0; url={rel}"><script>location.replace("{rel}")</script></head>\n'
                     f'<body><p>Esta página se mudó a <a href="{rel}">{target}</a>.</p></body></html>\n')
        rlines.append(f"| `/{old}` | `{target}` |")
    if rlines:
        (out / "REDIRECCIONES.md").write_text(
            "# Redirecciones de las URL anteriores\n\nSe generan desde `data/" + key + ".json` (clave `redirects`).\n"
            "En GitHub Pages funcionan como páginas con redirección inmediata y canónica. Con un hosting que permita 301, usar esta tabla.\n\n"
            "| URL anterior | Destino |\n|---|---|\n" + "\n".join(rlines) + "\n")

    # 404, robots, sitemap
    links = "".join(f' · <a href="{h}">{lab}</a>' for lab, h in P.get("not_found_links", []))
    (out / "404.html").write_text(
        f'<!doctype html><html lang="es-AR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>Página no encontrada | {P["name"]}</title><meta name="robots" content="{"noindex, follow" if links else "noindex"}">'
        f'<link rel="stylesheet" href="/assets/css/styles.css"></head><body style="display:grid;place-items:center;min-height:100vh;text-align:center;padding:24px">'
        f'<div><h1>Página no encontrada</h1><p>La página que buscás no existe{" o cambió de dirección" if links else ""}.</p>'
        f'<p><a class="btn btn-solid" href="/">Volver a {P["name"]}</a></p>'
        + (f'<p><a href="/">Inicio</a>{links}</p>' if links else "") + '</div></body></html>')
    robots = "User-agent: *\nAllow: /\n" + (f"Sitemap: {P['domain']}/sitemap.xml\n" if P["domain"] else "")
    (out / "robots.txt").write_text(robots)
    if P["domain"]:
        # Fecha real del último cambio aprobado de cada página (administrador); sin datos, la del día
        lastmod = PD.get("lastmod") or {}
        defecto = PD.get("lastmod_default") or date.today().isoformat()
        urls = "".join(f'  <url><loc>{P["domain"]}/{pg["out"]}</loc><lastmod>{lastmod.get(pg["out"], defecto)}</lastmod></url>\n'
                       for pg in P["pages"] if "noindex" not in (pg.get("robots") or "") and not pg.get("canonical") and pg.get("sitemap", True))
        (out / "sitemap.xml").write_text(
            f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}</urlset>\n')
    if not ARGS.no_project_files:
        write_project_files(out, P)
    for f in out.rglob("*"):
        if ".git" not in f.parts:
            f.chmod(0o755 if f.is_dir() else 0o644)
    return out, len(used), missing


if __name__ == "__main__":
    only = ARGS.products or list(PRODUCTS)
    for k in only:
        out, n, missing = export(k, PRODUCTS[k])
        print(f"✓ {out} · {n} recursos" + (f" · FALTAN: {missing}" if missing else ""))
    if "gerp" in only:
        pend = [f"  - {f['label']}: " + ", ".join(p["label"] for p in GERP_DATA["plans"] if f["values"][p["key"]] is None)
                for f in GERP_DATA["features"] if None in f["values"].values()]
        print("GERP · datos pendientes de validación:")
        for x in GERP_DATA["pending_validation"]:
            print("  - " + x)
        print("GERP · funcionalidades sin confirmar en el comparador:")
        print("\n".join(pend))
