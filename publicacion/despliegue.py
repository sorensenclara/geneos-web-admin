"""Destinos de publicación. Independientes del proveedor: se elige uno por sitio en «Configuración del sitio».

- carpeta: guarda cada versión en var/publico/<sitio>/versiones/<fecha> y cambia el enlace «actual» de forma atómica.
  Sirve para probar localmente y como historial para volver atrás.
- comando: además de guardar la versión, ejecuta un comando (rsync, git, wrangler de Cloudflare Pages, etc.).
  Si el comando falla, la versión pública anterior no se toca.
"""
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from django.conf import settings

CONSERVAR = 8


def raiz(sitio):
    return Path(settings.GWA_VAR_DIR) / "publico" / sitio.clave


def versiones(sitio):
    d = raiz(sitio) / "versiones"
    return sorted([p for p in d.iterdir() if p.is_dir()], reverse=True) if d.exists() else []


def version_actual(sitio):
    actual = raiz(sitio) / "actual"
    return actual.resolve().parent.name if actual.is_symlink() else None


def nueva_carpeta(sitio, nombre):
    d = raiz(sitio) / "versiones" / nombre
    d.parent.mkdir(parents=True, exist_ok=True)
    return d


def activar(sitio, carpeta_web):
    """Cambia la versión pública local de forma atómica (los visitantes ven la vieja o la nueva, nunca una mezcla)."""
    actual = raiz(sitio) / "actual"
    tmp = raiz(sitio) / f".actual-{carpeta_web.parent.name}"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(carpeta_web, target_is_directory=True)
    os.replace(tmp, actual)


def ejecutar_comando(sitio, carpeta_web):
    cmd = sitio.comando_despliegue.replace("{carpeta}", shlex.quote(str(carpeta_web)))
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=900)
    salida = (r.stdout or "")[-3000:] + (r.stderr or "")[-3000:]
    if r.returncode != 0:
        raise RuntimeError(f"El comando de despliegue terminó con error ({r.returncode}):\n{salida}")
    return salida


def limpiar(sitio):
    actual = version_actual(sitio)
    for v in versiones(sitio)[CONSERVAR:]:
        if v.name != actual:
            shutil.rmtree(v, ignore_errors=True)
