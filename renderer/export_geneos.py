"""Genera la web institucional de GENEOS con su propio build.py (GENEOS WEB) y le suma, si está activo y aprobado, el blog de Noticias.

GENEOS WEB no se modifica: se importa build.py y se ejecuta igual que «python build.py», pero escribiendo en otra carpeta.
Con Noticias inactivo el resultado es idéntico, archivo por archivo, al de build.py (lo verifica tests y la auditoría).

Con Noticias activo, sin tocar los archivos de GENEOS WEB:
  - el menú (partials/header.html) recibe el ítem en la posición elegida: la lista `nav` pasa por gwa_nav() al cargar la plantilla;
  - base.html usa og:type «article» y el canonical propio del artículo cuando corresponde;
  - se agregan la portada (con paginación) y los artículos, con las plantillas tpl/geneos/*.html que extienden base.html de GENEOS;
  - el sitemap y llms.txt los incluyen, con la fecha real de cada artículo.

Uso:  GENEOS_WEB_DIR=<GENEOS WEB> WEB_DATA_DIR=<datos del administrador> python export_geneos.py --out <carpeta>
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GENEOS = Path(os.environ.get("GENEOS_WEB_DIR") or HERE.parents[1]).resolve()
DATA = Path(os.environ["WEB_DATA_DIR"]) if os.environ.get("WEB_DATA_DIR") else None


class RutaSalida(type(Path())):
    """Carpeta de salida fuera de GENEOS WEB: build.py muestra cada archivo relativo a su carpeta, acá se muestra completo."""

    def relative_to(self, *otros, **kw):
        try:
            return super().relative_to(*otros, **kw)
        except ValueError:
            return self


class ErrorPlantilla(Exception):
    pass


def datos():
    f = DATA / "geneos.admin.json" if DATA else None
    return json.loads(f.read_text()) if f and f.exists() else {}


def transformar(nombre, fuente, activo):
    """Cambios en memoria (nunca en disco) de dos plantillas de GENEOS WEB. Sin blog activo, no se toca nada."""
    if not activo:
        return fuente
    if nombre == "partials/header.html":
        if "{% set nav = [" not in fuente:
            raise ErrorPlantilla("partials/header.html cambió: no se encontró la lista del menú («{% set nav = [»).")
        inicio = fuente.index("{% set nav = [")
        fin = fuente.index("] %}", inicio)
        return fuente[:inicio] + "{% set nav = gwa_nav([" + fuente[inicio + len("{% set nav = ["):fin] + "]) %}" + fuente[fin + len("] %}"):]
    if nombre == "base.html":
        og = '<meta property="og:type" content="website">'
        if og not in fuente:
            raise ErrorPlantilla("base.html cambió: no se encontró og:type.")
        fuente = fuente.replace(og, '<meta property="og:type" content="{{ page.og_type or \'website\' }}">')
        return fuente.replace("{{ canonical }}", "{{ page.canonical or canonical }}")
    return fuente


def generar(out_root):
    sys.path.insert(0, str(GENEOS))
    import build as B  # noqa: E402  (GENEOS WEB/build.py: solo se lee)
    from jinja2 import FileSystemLoader

    PD = datos()
    BLOG = PD.get("blog") or {}
    MENU = BLOG.get("menu")
    activo = bool(BLOG.get("indexes"))
    out = RutaSalida(Path(out_root).resolve() / "geneos-web")
    B.OUT = out  # build.py escribe acá en lugar de GENEOS WEB/public

    from jinja2 import BaseLoader

    class Cargador(BaseLoader):
        """Plantillas de GENEOS WEB (con los cambios en memoria) y las del blog (tpl/geneos/).
        «plantilla.html@ruta» es la misma plantilla: el sufijo solo sirve para que build.py calcule el <lastmod> de cada artículo."""

        def __init__(self, ruta):
            self.base = FileSystemLoader(ruta)
            self.blog = FileSystemLoader(HERE / "tpl" / "geneos")

        def get_source(self, environment, template):
            nombre = template.split("@")[0]
            try:
                fuente, archivo, actualizado = self.base.get_source(environment, nombre)
            except Exception:  # noqa: BLE001 — no está en GENEOS WEB: plantilla del blog
                return self.blog.get_source(environment, nombre)
            return transformar(nombre, fuente, activo), archivo, actualizado

    def cargador(ruta):
        return Cargador(ruta) if activo else FileSystemLoader(ruta)

    class Entorno(B.Environment):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.globals["gwa_nav"] = gwa_nav

    def gwa_nav(nav):
        if not MENU:
            return nav
        nav = list(nav)
        pos = MENU.get("position") or 0
        item = (MENU["label"], MENU["href"], [])
        nav.insert(pos - 1 if 0 < pos <= len(nav) else len(nav), item)
        return nav

    B.FileSystemLoader = cargador
    B.Environment = Entorno
    if activo:
        fechas = {}
        for b in BLOG["indexes"]:
            tpl = f"geneos-blog-index.html@{b['path']}"
            B.PAGES.append(dict(tpl=tpl, out=b["path"], title=b["seo_title"], description=b["description"], crumb=b["title"],
                                priority="0.6", blog=b, noindex=bool(b.get("robots"))))
            fechas[tpl] = b["lastmod"]
        for a in BLOG["posts"]:
            tpl = f"geneos-blog-post.html@{a['path']}"
            p = dict(tpl=tpl, out=a["path"], title=a["seo_title"], description=a["description"], crumb=a["title"],
                     parent=a["index_path"], priority="0.5", post=a, og_type="article", canonical=a.get("canonical"),
                     noindex=bool(a.get("robots")))
            if a.get("og"):
                p["og"] = a["og"]["src"]  # se copia a assets/img/blog/og/
            B.PAGES.append(p)
            fechas[tpl] = a["lastmod"]
        B.PAGE_BY_OUT.update({p["out"]: p for p in B.PAGES})
        lastmod_original = B.lastmod
        B.lastmod = lambda tpl: fechas.get(tpl) or lastmod_original(tpl)
    B.build()
    if activo:
        for src, d in PD.get("files", []):  # imágenes del blog entregadas por el administrador
            t = out / "assets" / "img" / d
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, t)
        css = HERE / "static" / "css" / "blog.css"
        (out / "assets" / "css").mkdir(parents=True, exist_ok=True)
        shutil.copy2(css, out / "assets" / "css" / "blog.css")
        js = HERE / "static" / "js" / "blog.js"
        (out / "assets" / "js").mkdir(parents=True, exist_ok=True)
        shutil.copy2(js, out / "assets" / "js" / "blog.js")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Genera la web de GENEOS (build.py) con el blog del administrador")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    try:
        carpeta = generar(args.out)
    except ErrorPlantilla as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    print(f"✓ {carpeta}")
