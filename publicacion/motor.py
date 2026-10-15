"""Generación de una web con el motor de sitios (renderer/) y controles antes de publicarla."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings

from .exportar import CARPETAS, datos_sitio


class NoConectado(Exception):
    pass


class ErrorGeneracion(Exception):
    pass


def conectado(sitio):
    return sitio.clave in CARPETAS


def generar(sitio, destino, overrides=None):
    """Genera la web del sitio en `destino`/<carpeta>. Devuelve (carpeta, datos, registro).
    GENEOS usa su propio build.py (GENEOS WEB, sin modificarlo) y suma las Noticias del administrador (renderer/export_geneos.py)."""
    if not conectado(sitio):
        raise NoConectado(f"La web de {sitio.nombre} todavía no está conectada al generador.")
    archivos, _files = datos_sitio(sitio, overrides)
    tmp = Path(tempfile.mkdtemp(prefix="gwa-datos-", dir=settings.GWA_VAR_DIR))
    try:
        for nombre, contenido in archivos.items():
            (tmp / nombre).write_text(json.dumps(contenido, ensure_ascii=False, indent=1))
        env = dict(os.environ, GENEOS_WEB_DIR=str(settings.GENEOS_WEB_DIR), WEB_DATA_DIR=str(tmp), GEAGRO_SRC_DIR=str(settings.GEAGRO_SRC_DIR))
        if sitio.motor == "institucional":
            cmd = [sys.executable, str(Path(settings.GWA_RENDERER_DIR) / "export_geneos.py"), "--out", str(destino)]
        else:
            cmd = [sys.executable, str(Path(settings.GWA_RENDERER_DIR) / "export.py"), sitio.clave, "--out", str(destino), "--no-project-files"]
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    registro = (r.stdout or "")[-4000:]
    if r.returncode != 0:
        raise ErrorGeneracion("El generador terminó con un error:\n" + (r.stderr or "")[-4000:])
    if "FALTAN:" in r.stdout:
        registro += "\nAviso: hay recursos que no se encontraron (ver arriba)."
    return Path(destino) / CARPETAS[sitio.clave], archivos, registro


def validar(sitio, carpeta, archivos):
    """Controles mínimos antes de reemplazar la web pública."""
    errores = []
    paginas = [""]
    pd = archivos.get(f"{sitio.clave}.admin.json", {})
    paginas += [r for r in pd.get("pages", {}) if r and (carpeta / r).exists()]
    if sitio.clave == "gerp":
        paginas += [p["slug"] for p in archivos["gerp.json"]["plans"]]
    paginas += [b["path"] for b in pd.get("blog", {}).get("indexes", [])] + [a["path"] for a in pd.get("blog", {}).get("posts", [])]
    for ruta in dict.fromkeys(paginas):
        f = carpeta / ruta / "index.html"
        if not f.exists():
            errores.append(f"Falta la página /{ruta}")
            continue
        html = f.read_text()
        if len(re.findall(r"<h1[\s>]", html)) != 1:
            errores.append(f"/{ruta}: tiene que haber un solo título principal (H1)")
        if "<title></title>" in html:
            errores.append(f"/{ruta}: falta el título de la página")
    home = (carpeta / "index.html").read_text() if (carpeta / "index.html").exists() else ""
    precios = []
    if sitio.clave == "gerp":
        precios = [p["price"] for p in archivos["gerp.json"]["plans"]]
    else:
        precios = [p["price"] for p in pd.get("plans", []) if not p.get("hidden")]
    for precio in precios:
        if precio and f"${precio}" not in home and f"$ {precio}" not in home:
            errores.append(f"El precio ${precio} no aparece en la página de inicio")
    return errores
