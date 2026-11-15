#!/usr/bin/env python3
"""Genera el sitio estático de GENEOS en ./public a partir de ./templates y ./static.

Uso:
    pip install jinja2
    python build.py                       # sitio servido desde la raíz del dominio
    BASE_PATH=/geneos python build.py     # p. ej. GitHub Pages de proyecto

Variables de entorno:
    BASE_PATH      subcarpeta donde se publica (vacío en dominio propio)
    SITE_URL       URL pública donde se sirve este build (para redirecciones del formulario)
    CANONICAL_URL  dominio oficial para canonical, sitemap y datos estructurados
"""
import json
import os
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, pass_context, select_autoescape
from markupsafe import Markup

ROOT = Path(__file__).parent
OUT = ROOT / "public"
BASE_PATH = os.environ.get("BASE_PATH", "").rstrip("/")
CANONICAL_URL = os.environ.get("CANONICAL_URL", "https://geneos.coop.ar").rstrip("/")
SITE_URL = (os.environ.get("SITE_URL") or CANONICAL_URL).rstrip("/")
TODAY = date.today().isoformat()


def lastmod(tpl):
    """Fecha del último commit que tocó la plantilla (para <lastmod> del sitemap)."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", f"templates/{tpl}"],
                             cwd=Path(__file__).resolve().parent, capture_output=True, text=True, timeout=10).stdout.strip()
        return out or TODAY
    except Exception:
        return TODAY

SITE = {
    "name": "GENEOS",
    "legal_name": "Cooperativa de Trabajo GENEOS Ltda.",
    "tagline": "Cooperativa de Software Libre",
    "whatsapp": "5492494521418",
    "whatsapp_label": "+549 2494 521418",
    "phone": "+54 9 249 452-1418",
    "email": "info@geneos.com.ar",
    "address": "Alem 1015 - Tandil",
    "street": "Alem 1015",
    "city": "Tandil",
    "province": "Buenos Aires",
    "postal_code": "B7000",
    "country": "AR",
    "region": "Buenos Aires - Argentina",
    "maps": "https://maps.app.goo.gl/SG3oBGYpz7ttdvbB8",
    # Endpoint del formulario de contacto. FormSubmit reenvía al mail sin backend
    # (la primera vez manda un mail de activación). Se puede cambiar por Formspree,
    # un endpoint propio en Django, etc.
    "form_action": "https://formsubmit.co/info@geneos.com.ar",
    # Productos propios: barra superior (pestaña nueva). Se configuran en data/productos.json
    "products": [],
    "social": [
        ("Facebook", "https://www.facebook.com/coopgeneos/", "facebook"),
        ("Instagram", "https://www.instagram.com/coopgeneos/", "instagram"),
        ("X / Twitter", "https://x.com/CoopGENEOS", "twitter"),
        ("LinkedIn", "https://ar.linkedin.com/company/geneos-coop", "linkedin"),
    ],
}

# Webs independientes de los productos (barra superior y botones de las páginas de producto)
PRODUCTOS = {k: v for k, v in json.loads((ROOT / "data" / "productos.json").read_text()).items() if not k.startswith("_")}
for _p in PRODUCTOS.values():
    _p["sitio"] = _p["url"] if _p.get("url_confirmada") and _p.get("url") else ""  # vacío: no se muestran los botones
SITE["products"] = [(p["nombre"], p["descripcion"], p["url"], p["logo"]) for p in PRODUCTOS.values() if p.get("url")]

# Trabajos e imágenes de identidad: los genera GENEOS Web Admin (data/trabajos.json y data/identidad.json).
# Solo se publican los activos y aprobados, ordenados; trabajos_de("diseno") filtra por servicio.
_TRAB = json.loads((ROOT / "data" / "trabajos.json").read_text())
TRABAJOS = sorted([t for t in _TRAB.get("trabajos", []) if t.get("activo") and t.get("aprobado")], key=lambda t: t.get("orden", 0))
PORTFOLIO_URL = _TRAB.get("portfolio_url") or ""
IDENTIDAD = sorted([i for i in json.loads((ROOT / "data" / "identidad.json").read_text()).get("imagenes", []) if i.get("activo") and i.get("aprobado")], key=lambda i: i.get("orden", 0))


SITIO = {k: v for k, v in json.loads((ROOT / "data" / "sitio.json").read_text()).items() if not k.startswith("_")}
ENCABEZADOS = ("claro", "oscuro")


def encabezado_de(page):
    """Apariencia del encabezado: la de la página si la define (claro/oscuro); si no, la global (heredar)."""
    valor = page.get("encabezado") or SITIO.get("encabezado") or "claro"
    return valor if valor in ENCABEZADOS else "claro"


def trabajos_de(servicio):
    return [t for t in TRABAJOS if servicio in t.get("servicios", [])]


# ------------------------------------------------------------------ Contenido administrado (GENEOS Web Admin)
# Cada sección editable tiene una clave estable (su ancla) y sus textos por defecto en la plantilla:
#     {% set s = seccion("soluciones", {...textos actuales...}) %}
# GENEOS Web Admin entrega los cambios en page["admin"] = {"secciones": {clave: {...}}, "ocultas": [...], "orden": [...]}.
# Solo reemplaza los campos con contenido: un campo vacío conserva el texto de la plantilla. Sin datos (build.py solo),
# la web queda idéntica. El diseño (clases, colores, íconos de cada tarjeta, componentes) nunca viene del administrador.
SECCIONES_LEIDAS = {}  # {ruta: {clave: valores por defecto}}: el administrador los lee para importar los textos actuales


def _vacio(v):
    return v is None or v == "" or v == [] or v == {}


def combinar(base, admin):
    """Valores de la plantilla con los del administrador encima, campo por campo.
    Las listas de ítems se combinan por la clave de cada ítem; el orden y la cantidad son los del administrador."""
    if not isinstance(admin, dict):
        return base
    res = dict(base)
    for k, v in admin.items():
        if _vacio(v):
            continue
        if isinstance(v, list) and all(isinstance(i, dict) for i in v):  # ítems (tarjetas, botones, destacados)
            previos = {i.get("clave"): i for i in base.get(k) or [] if isinstance(i, dict) and i.get("clave")}
            res[k] = [combinar(previos.get(i.get("clave"), {}), i) for i in v if isinstance(i, dict)]
        elif isinstance(v, dict) and isinstance(base.get(k), dict):
            res[k] = combinar(base[k], v)
        else:
            res[k] = v
    return res


def _admin(ctx):
    page = ctx.get("page") or {}
    return page.get("admin") or {}


@pass_context
def seccion(ctx, clave, base):
    page = ctx.get("page") or {}
    SECCIONES_LEIDAS.setdefault(page.get("out", ""), {})[clave] = base
    return combinar(base, (_admin(ctx).get("secciones") or {}).get(clave))


@pass_context
def visible(ctx, clave):
    return clave not in (_admin(ctx).get("ocultas") or [])


@pass_context
def orden_secciones(ctx, claves):
    """Secciones visibles en el orden elegido. Solo se reordenan entre sí las que el administrador ordenó;
    las demás quedan en su lugar y las claves desconocidas se ignoran."""
    elegidas = [c for c in (_admin(ctx).get("orden") or []) if c in claves]
    elegidas = list(dict.fromkeys(elegidas))
    cola = iter(elegidas)
    res = [next(cola) if c in elegidas else c for c in claves]
    return [c for c in res if c not in (_admin(ctx).get("ocultas") or [])]


@pass_context
def logos_de(ctx, clave, logos):
    """Logos de la plantilla (se conservan siempre) más los autorizados en el administrador que todavía no están."""
    page = ctx.get("page") or {}
    SECCIONES_LEIDAS.setdefault(page.get("out", ""), {})["logos:" + clave] = list(logos)
    actuales = {(x[0] if isinstance(x, (list, tuple)) else x) for x in logos}
    nuevos = [(n["src"], n.get("enlace") or None, "Logo de " + n["nombre"]) if n.get("nombre") else n["src"]
              for n in (_admin(ctx).get("logos") or {}).get(clave, []) if n.get("src") and n.get("archivo_web") not in actuales]
    return list(logos) + nuevos


# Cada página: plantilla, ruta, título (<60 car.), descripción (<160 car.),
# miga de pan (nombre corto), imagen para redes y prioridad en el sitemap.
PAGES = [
    dict(tpl="index.html", out="",
         title="GENEOS | Cooperativa de software libre: ERP, apps y webs",
         description="Cooperativa de software libre de Argentina. Desarrollamos software de gestión Odoo, apps, sitios web y campus Moodle para Argentina y Latinoamérica.",
         crumb="Inicio", priority="1.0"),
    dict(tpl="servicios.html", out="servicios/",
         title="Servicios de desarrollo de software libre | GENEOS",
         description="Software de gestión Odoo, staff augmentation, apps y sitios web, plataformas Moodle y diseño. Soluciones con software libre para Argentina y Latam.",
         crumb="Servicios", priority="0.9"),
    dict(tpl="software-de-gestion.html", out="software-de-gestion-completo/", parent="servicios/",
         title="GERP | Software de gestión empresarial – GENEOS",
         description="GERP, el software de gestión empresarial para pymes de GENEOS: integra ventas, compras, stock, facturación y contabilidad en una sola plataforma online.",
         crumb="Software de Gestión GERP", og="og/gerp.jpg", priority="0.9"),
    dict(tpl="gema.html", out="software-gestion-matafuegos-extintores/", parent="servicios/",
         title="GEMA | Software para talleres de matafuegos – GENEOS",
         description="GEMA, el software de gestión para talleres de matafuegos de GENEOS: clientes, extintores, órdenes de trabajo, vencimientos y avisos en una plataforma online.",
         crumb="Software de Matafuegos GEMA", og="og/gema.jpg", priority="0.9"),
    dict(tpl="geagro.html", out="software-agropecuario-geagro/", parent="servicios/",
         # La palabra clave "software de gestión agropecuaria" queda para geagro.ar; acá se presenta el producto como desarrollo de GENEOS
         title="GEAGRO: software agropecuario de la cooperativa GENEOS",
         description="GEAGRO es el software agropecuario que desarrolla la cooperativa GENEOS en Tandil, con versiones para cereales y viñedos. Planes y demo en geagro.ar.",
         crumb="Software Agropecuario GEAGRO", og="og/geagro.jpg", priority="0.9"),
    dict(tpl="staff-augmentation.html", out="staff-augmentation/", parent="servicios/",
         title="Staff Augmentation en Argentina | Talento IT – GENEOS",
         description="Ampliá tu equipo con desarrolladores, DevOps, analistas y diseñadores UX/UI de Argentina. Staff augmentation flexible con GENEOS.",
         crumb="Staff Augmentation", priority="0.8"),
    dict(tpl="apps-y-webs.html", out="desarrollo-apps-sitios-web-cooperativos/", parent="servicios/",
         title="Desarrollo de aplicaciones y sitios web a medida | GENEOS",
         description="Sitios web a medida y autoadministrables con Wagtail, y aplicaciones web con usuarios, formularios y mapas. Desarrollo con software libre en Argentina.",
         crumb="Apps y sitios web", priority="0.8"),
    dict(tpl="e-learning.html", out="plataformas-e-learning-lms-moodle/", parent="servicios/",
         title="Plataformas e-learning y campus virtual Moodle | GENEOS",
         description="Creamos campus virtuales en Moodle para universidades, institutos y empresas: diseño a medida, gamificación con H5P, capacitación y soporte. Argentina y Latam.",
         crumb="E-learning Moodle", priority="0.8"),
    dict(tpl="diseno.html", out="diseno-sitios-web-identidades/", parent="servicios/",
         title="Diseño web, identidad visual y comunicación | GENEOS",
         description="Diseño de sitios web UX/UI, identidades visuales y estrategia de comunicación digital para cooperativas, pymes e instituciones de Argentina y Latinoamérica.",
         crumb="Diseño y Comunicación", priority="0.8"),
    dict(tpl="quienes-somos.html", out="quienes-somos/",
         title="Quiénes somos: cooperativa de software en Tandil | GENEOS",
         description="Cooperativa de software de Tandil que desarrolla sistemas de gestión y soluciones digitales a medida con software libre. Conocé al equipo de GENEOS.",
         crumb="Quiénes somos", og="og/quienes-somos.jpg", priority="0.7"),
    dict(tpl="recursos.html", out="recursos/",
         title="Recursos de marca: logos y brochures | GENEOS",
         description="Descargá los logotipos oficiales, manuales de identidad y brochures comerciales de GENEOS y de sus productos GERP, GEAGRO y GEMA.",
         crumb="Recursos", priority="0.4"),
    dict(tpl="contacto.html", out="contacto-geneos/",
         title="Contacto | GENEOS, cooperativa de software libre",
         description="Escribinos por WhatsApp, mail o formulario. Software a medida con Django, Wagtail, Odoo, Moodle y diseño para Argentina y Latinoamérica. Alem 1015, Tandil.",
         crumb="Contacto", priority="0.7"),
    dict(tpl="404.html", out="404.html", title="Página no encontrada | GENEOS",
         description="La página que buscás no existe.", crumb="Error 404", noindex=True),
]
PAGE_BY_OUT = {p["out"]: p for p in PAGES}

# URLs viejas (WordPress) -> nuevas. Se generan _redirects (Netlify/Cloudflare) y .htaccess (Apache).
REDIRECTS = {
    "/index.php/apps-y-sitios-web/": "/desarrollo-apps-sitios-web-cooperativos/",
    "/index.php/plataformas-e-learning/": "/plataformas-e-learning-lms-moodle/",
    "/index.php/disenamos-sitios-web-identidades/": "/diseno-sitios-web-identidades/",
    "/index.php/plataformas-de-gestion/": "/software-de-gestion-completo/",
    "/index.php/software-de-gestion/": "/software-de-gestion-completo/",
    "/index.php/app-webs/": "/desarrollo-apps-sitios-web-cooperativos/",
    "/index.php/diseno-grafico-y-web/": "/diseno-sitios-web-identidades/",
    "/index.php/contact/": "/contacto-geneos/",
    "/apps-y-sitios-web/": "/desarrollo-apps-sitios-web-cooperativos/",
    "/plataformas-e-learning/": "/plataformas-e-learning-lms-moodle/",
    "/disenamos-sitios-web-identidades/": "/diseno-sitios-web-identidades/",
    "/contact/": "/contacto-geneos/",
    "/recursos-graficos/": "/recursos/",
    "/index.php/recursos-graficos/": "/recursos/",
    "/assets/descargas/Logos-GENEOS-Vector.zip": "/assets/descargas/geneos-logos-svg.zip",
    "/assets/descargas/Logos-GENEOS-PNG.zip": "/assets/descargas/geneos-logos-png.zip",
    "/assets/descargas/GERP-Vector.zip": "/assets/descargas/gerp-logos-svg.zip",
    "/assets/descargas/GERP-PNG.zip": "/assets/descargas/gerp-logos-png.zip",
    "/assets/descargas/Manual-de-MARCA-G-ERP.pdf": "/assets/descargas/manual-de-marca-gerp.pdf",
}


def url(path=""):
    """Ruta interna respetando BASE_PATH."""
    if path.startswith(("http://", "https://", "mailto:", "tel:", "#")):
        return path
    return f"{BASE_PATH}/{path.lstrip('/')}"


def asset(path):
    return url("assets/" + path.lstrip("/"))


def img(path):
    """Imagen en assets/img. Las rasterizadas se publican como .webp."""
    p = Path(path)
    if p.suffix.lower() in (".png", ".jpg", ".jpeg"):
        p = p.with_suffix(".webp")
    return asset("img/" + p.as_posix())


def abs_url(path=""):
    """URL absoluta en el dominio oficial (canonical, schema, sitemap)."""
    return f"{CANONICAL_URL}/{path.lstrip('/')}"


_icon_cache = {}


def icon(name, cls="icon"):
    if name not in _icon_cache:
        _icon_cache[name] = (ROOT / "templates" / "icons" / f"{name}.svg").read_text()
    svg = _icon_cache[name].replace("<svg ", f'<svg class="{cls}" ', 1)
    return Markup(svg)


def wa(text=""):
    from urllib.parse import quote
    return f"https://wa.me/{SITE['whatsapp']}" + (f"?text={quote(text)}" if text else "")


def jsonld(data):
    """Bloque <script type=application/ld+json> seguro."""
    raw = json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/")
    return Markup(f'<script type="application/ld+json">{raw}</script>')


def breadcrumbs(page):
    """Lista [(nombre, ruta)] desde Inicio hasta la página."""
    chain, p = [], page
    while p:
        chain.insert(0, (p["crumb"], p["out"]))
        p = PAGE_BY_OUT.get(p.get("parent")) if p.get("parent") is not None else None
    if page["out"] != "":
        chain.insert(0, ("Inicio", ""))
    return chain


def crumbs_schema(crumbs):
    return [{"@type": "ListItem", "position": i + 1, "name": name, "item": abs_url(href)}
            for i, (name, href) in enumerate(crumbs)]


def faq_entities(items):
    import re
    return [{"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": re.sub(r"<[^>]+>", "", a)}} for q, a in items]


SERVICE_PAGES = ["software-de-gestion-completo/", "software-gestion-matafuegos-extintores/",
                 "software-agropecuario-geagro/", "staff-augmentation/",
                 "desarrollo-apps-sitios-web-cooperativos/", "plataformas-e-learning-lms-moodle/",
                 "diseno-sitios-web-identidades/"]


def service_items():
    return [{"@type": "ListItem", "position": i + 1, "name": PAGE_BY_OUT[o]["crumb"], "url": abs_url(o)}
            for i, o in enumerate(SERVICE_PAGES)]


def org_schema():
    s = SITE
    return {
        "@type": ["Organization", "LocalBusiness"],
        "@id": abs_url("#organizacion"),
        "name": s["name"],
        "legalName": s["legal_name"],
        "alternateName": "GENEOS Cooperativa de Software Libre",
        "url": abs_url(),
        "logo": abs_url("assets/img/favicon-192.png"),
        "image": abs_url("assets/img/og/geneos.jpg"),
        "description": "Cooperativa de trabajo de software libre que desarrolla software de gestión, aplicaciones, sitios web y plataformas e-learning.",
        "email": s["email"],
        "telephone": s["phone"],
        "address": {"@type": "PostalAddress", "streetAddress": s["street"], "addressLocality": s["city"],
                    "addressRegion": s["province"], "postalCode": s["postal_code"], "addressCountry": s["country"]},
        "hasMap": s["maps"],
        "areaServed": [{"@type": "Country", "name": "Argentina"}, {"@type": "Place", "name": "Latinoamérica"}],
        "knowsAbout": ["Software libre", "Odoo", "ERP", "Software agropecuario", "Django", "Wagtail", "Python", "Moodle", "Angular",
                       "React Native", "Desarrollo web", "Diseño UX/UI", "Staff augmentation"],
        "memberOf": {"@type": "Organization", "name": "FACTTIC", "url": "https://facttic.org.ar/"},
        "sameAs": [href for _, href, _ in s["social"]],
        "contactPoint": {"@type": "ContactPoint", "contactType": "customer service", "telephone": s["phone"],
                         "email": s["email"], "availableLanguage": ["es"], "areaServed": ["AR", "419"]},
        "hasOfferCatalog": {"@type": "OfferCatalog", "name": "Servicios y productos de GENEOS",
                            "itemListElement": [{"@type": "Offer", "itemOffered": {"@type": "Service", "name": pg["crumb"], "url": abs_url(pg["out"])}}
                                                for pg in PAGES if pg.get("parent") == "servicios/"]},
    }


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "static", OUT)

    env = Environment(loader=FileSystemLoader(ROOT / "templates"),
                      autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
    env.filters["regex_replace"] = lambda v, pat, rep="": re.sub(pat, rep, v)
    env.globals.update(PRODUCTOS=PRODUCTOS, trabajos_de=trabajos_de, PORTFOLIO_URL=PORTFOLIO_URL, IDENTIDAD=IDENTIDAD, site=SITE, url=url, asset=asset, img=img, icon=icon, wa=wa, jsonld=jsonld,
                       abs_url=abs_url, year=date.today().year, site_url=SITE_URL, org_schema=org_schema, crumbs_schema=crumbs_schema, faq_entities=faq_entities, service_items=service_items,
                       pages=PAGE_BY_OUT, seccion=seccion, visible=visible, orden_secciones=orden_secciones, logos_de=logos_de)

    for page in PAGES:
        out = page["out"]
        target = OUT / out if out.endswith(".html") else OUT / out / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        crumbs = breadcrumbs(page)
        html = env.get_template(page["tpl"]).render(
            page=page, title=page["title"], description=page["description"], encabezado=encabezado_de(page),
            path="/" + (out if not out.endswith(".html") else ""),
            canonical=None if page.get("noindex") else abs_url(out),
            og_image=abs_url("assets/img/" + page.get("og", "og/geneos.jpg")),
            crumbs=crumbs,
        )
        target.write_text(html)
        print("✓", target.relative_to(ROOT), f"({len(page['title'])} / {len(page['description'])} car.)")

    # Redirecciones
    lines = [f"{old} {url(new)} 301" for old, new in REDIRECTS.items()]
    lines.append(f"/index.php/* {url('/:splat')} 301")
    (OUT / "_redirects").write_text("\n".join(lines) + "\n")
    ht = ["ErrorDocument 404 /404.html", "RewriteEngine On"]
    for old, new in REDIRECTS.items():
        ht.append(f"RewriteRule ^{old.strip('/')}/?$ {url(new)} [R=301,L]")
    ht.append(f"RewriteRule ^index\\.php/(.*)$ {url('/')}$1 [R=301,L]")
    (OUT / ".htaccess").write_text("\n".join(ht) + "\n")
    # Páginas puente para hosts estáticos sin redirecciones (GitHub Pages): meta refresh + canonical
    for old, new in REDIRECTS.items():
        if not old.endswith("/") or old.startswith("/index.php/"):
            continue
        stub = OUT / old.strip("/") / "index.html"
        if stub.exists():
            continue
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text(f'<!doctype html><html lang="es-AR"><head><meta charset="utf-8"><title>Redirigiendo…</title>'
                        f'<meta name="robots" content="noindex"><link rel="canonical" href="{abs_url(new)}">'
                        f'<meta http-equiv="refresh" content="0; url={url(new)}"></head>'
                        f'<body><p><a href="{url(new)}">Esta página se mudó</a>.</p></body></html>')

    # sitemap + robots
    urls = "\n".join(
        f"  <url><loc>{abs_url(p['out'])}</loc><lastmod>{lastmod(p['tpl'])}</lastmod><priority>{p.get('priority', '0.5')}</priority></url>"
        for p in PAGES if not p.get("noindex"))
    (OUT / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n')
    # llms.txt: resumen del sitio para buscadores con IA (ChatGPT, Perplexity, Gemini…)
    llms = ["# GENEOS", "",
            "> Cooperativa de Trabajo GENEOS Ltda. (Tandil, Argentina): desarrollo de software libre para organizaciones de "
            "Argentina y Latinoamérica. Productos propios GERP (ERP basado en Odoo), GEMA (gestión de talleres de matafuegos) "
            "y GEAGRO (gestión agropecuaria), además de staff augmentation, apps, sitios web, campus Moodle y diseño.", "",
            f"Contacto: {SITE['email']} · WhatsApp {SITE['phone']} · {SITE['street']}, {SITE['city']}, {SITE['province']}", "",
            "## Páginas"]
    llms += [f"- [{pg['title']}]({abs_url(pg['out'])}): {pg['description']}" for pg in PAGES if not pg.get("noindex")]
    llms += ["", "## Productos", *[f"- [{n}]({h}): {d}" for n, d, h, _ in SITE["products"]]]
    (OUT / "llms.txt").write_text("\n".join(llms) + "\n")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {CANONICAL_URL}/sitemap.xml\n")


if __name__ == "__main__":
    build()
