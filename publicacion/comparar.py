"""Comparación de una web generada con otra (la publicada, una versión anterior): páginas, texto visible y archivos.

Sirve para dos cosas: comprobar que lo que generaría el administrador coincide con lo que está en la web antes de publicar,
y mostrar qué cambia en una publicación. Compara el texto que lee una persona (sin scripts, estilos ni íconos),
no el HTML: un cambio de marcado que no cambia el texto no cuenta como diferencia.
"""
import difflib
import html
import re
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlsplit

_SIN_TEXTO = re.compile(r"<(script|style|svg|noscript)\b[^>]*>.*?</\1>", re.S | re.I)
_CORTES = re.compile(r"<br\s*/?>|</(p|h[1-6]|li|div|section|header|footer|article|a|button|th|td|summary|span|b|strong|label|option|figcaption)>", re.I)
_ETIQUETA = re.compile(r"<[^>]+>")
_REDIRECCION = re.compile(r'http-equiv="refresh"', re.I)
_IGNORAR_ARCHIVOS = {".nojekyll", ".gitignore", "README.md", "CNAME", "CNAME.example", "REDIRECCIONES.md"}


def texto_visible(contenido):
    """Renglones de texto que ve una persona, en orden, con los espacios normalizados."""
    t = _SIN_TEXTO.sub("", contenido)
    t = _CORTES.sub("\n", t)
    t = html.unescape(_ETIQUETA.sub(" ", t))
    return [r for r in (re.sub(r"\s+", " ", x).strip() for x in t.split("\n")) if r]


def paginas(carpeta):
    """{ruta: archivo} de las páginas de una web generada ("" = inicio, "lite/"…)."""
    carpeta = Path(carpeta)
    res = {}
    for f in carpeta.rglob("index.html"):
        if ".git" in f.parts:
            continue
        rel = f.parent.relative_to(carpeta).as_posix()
        res["" if rel == "." else rel + "/"] = f
    return res


def archivos(carpeta):
    carpeta = Path(carpeta)
    return {f.relative_to(carpeta).as_posix() for f in carpeta.rglob("*")
            if f.is_file() and ".git" not in f.parts and ".github" not in f.parts and f.name not in _IGNORAR_ARCHIVOS}


def leer_referencia(referencia, ruta):
    """HTML de una página de la referencia: una carpeta local o la URL base de una web publicada. None si no existe."""
    if re.match(r"https?://", str(referencia)):
        url = str(referencia).rstrip("/") + "/" + ruta
        req = urllib.request.Request(url, headers={"User-Agent": "GENEOS-Web-Admin/comparar", "Cache-Control": "no-cache"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            return None
    f = Path(referencia) / ruta / "index.html"
    return f.read_text(errors="replace") if f.exists() else None


def comparar(generada, referencia):
    """Diferencias entre una web generada (carpeta) y una referencia (carpeta o URL).

    Devuelve {"paginas_nuevas", "paginas_faltantes", "texto": {ruta: [renglones con +/-]}, "archivos_nuevos", "archivos_faltantes"}.
    Con una URL de referencia no se comparan archivos (solo las páginas que existen en la generada).
    """
    gen = paginas(generada)
    local = not re.match(r"https?://", str(referencia))
    ref = paginas(referencia) if local else {}
    res = {"paginas_nuevas": sorted(set(gen) - set(ref)) if local else [], "paginas_faltantes": sorted(set(ref) - set(gen)),
           "texto": {}, "archivos_nuevos": [], "archivos_faltantes": []}
    for ruta, f in sorted(gen.items()):
        nuevo = f.read_text(errors="replace")
        viejo = leer_referencia(referencia, ruta)
        if viejo is None:
            if not local:
                res["paginas_nuevas"].append(ruta)
            continue
        if _REDIRECCION.search(nuevo) and _REDIRECCION.search(viejo):
            continue
        d = [x for x in difflib.unified_diff(texto_visible(viejo), texto_visible(nuevo), lineterm="", n=0)
             if x[:1] in "+-" and not x.startswith(("+++", "---"))]
        if d:
            res["texto"][ruta] = d
    if local:
        a, b = archivos(generada), archivos(referencia)
        res["archivos_nuevos"], res["archivos_faltantes"] = sorted(a - b), sorted(b - a)
    return res


def sin_diferencias(res, permitidos=()):
    """True si no hay páginas ni textos distintos (los renglones de `permitidos` no cuentan; los archivos tampoco)."""
    texto = {r: [x for x in d if x[1:] not in permitidos] for r, d in res["texto"].items()}
    return not (res["paginas_nuevas"] or res["paginas_faltantes"] or any(texto.values()))


_REF = re.compile(r'''(?:src|href|poster)=["']([^"']+)["']|srcset=["']([^"']+)["']|url\(\s*['"]?([^'")]+)['"]?\s*\)''')


def referencias_rotas(carpeta):
    """Enlaces y recursos relativos (HTML y CSS) que apuntan a un archivo que no está en la web generada."""
    carpeta = Path(carpeta)
    rotas = []
    for f in list(carpeta.rglob("*.html")) + list(carpeta.rglob("*.css")):
        contenido = f.read_text(errors="replace")
        contenido = re.sub(r"<script\b[^>]*>.*?</script>", "", contenido, flags=re.S)  # JSON-LD y scripts: URLs absolutas
        # url() en un style="" de la página: es una variable CSS que el navegador resuelve desde la hoja de estilos
        # (assets/css/). Las del bloque <style> y los src/href se resuelven desde la página.
        partes = [(re.sub(r'style="[^"]*"', "", contenido), f.parent)]
        if f.suffix == ".html":
            partes += [(a, carpeta / "assets" / "css") for a in re.findall(r'style="([^"]*)"', contenido)]
        for texto, desde in partes:
            for m in _REF.finditer(texto):
                valores = [m.group(1) or m.group(3)] if not m.group(2) else [c.strip().split(" ")[0] for c in m.group(2).split(",")]
                for v in valores:
                    v = (v or "").strip()
                    if not v or v.startswith(("#", "http:", "https:", "//", "mailto:", "tel:", "data:", "javascript:", "{", "$", "/")):
                        continue
                    destino = (desde / unquote(urlsplit(v).path)).resolve()
                    if destino.is_dir():
                        destino = destino / "index.html"
                    if not destino.exists():
                        rotas.append(f"{f.relative_to(carpeta)} → {v}")
    return sorted(set(rotas))
