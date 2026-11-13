#!/usr/bin/env python3
"""Base propia del generador de los sitios comerciales (GERP, GEAGRO, GEMA).

El generador (renderer/export.py) ya no lee carpetas de afuera del repositorio: usa la copia versionada en
renderer/base/. Este script es la única forma de actualizarla y deja registrado de dónde salió cada archivo.

  renderer/base/geneos/            archivos de GENEOS WEB listados en MANIFIESTO-geneos.txt
  renderer/base/geagro-publicado/  archivos del sitio publicado de GEAGRO listados en MANIFIESTO-geagro.txt
  renderer/base/ORIGEN.json        repositorio, rama y commit de origen + huella (sha256) de cada archivo

Uso:
  scripts/actualizar_base_comercial.py --geneos-web "../GENEOS WEB" --geagro "<carpeta GEAGRO WEB 2026>"
  scripts/actualizar_base_comercial.py --verificar      # la copia coincide con ORIGEN.json (lo corre la suite de tests)

Actualizar la base cambia lo que generan las webs: después, generar y revisar las diferencias antes de publicar.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
BASE = RAIZ / "renderer" / "base"
FUENTES = {"geneos": ("MANIFIESTO-geneos.txt", "geneos"), "geagro": ("MANIFIESTO-geagro.txt", "geagro-publicado")}


def huella(f):
    return hashlib.sha256(f.read_bytes()).hexdigest()


def patrones(manifiesto):
    return [l.strip() for l in (BASE / manifiesto).read_text().splitlines() if l.strip() and not l.lstrip().startswith("#")]


def listar(origen, manifiesto):
    """Archivos del origen que cubre el manifiesto (relativos). Un patrón sin coincidencias es un error."""
    archivos, faltan = set(), []
    for p in patrones(manifiesto):
        hallados = [f for f in origen.glob(p) if f.is_file() and "__pycache__" not in f.parts and f.name != ".DS_Store"]
        if not hallados:
            faltan.append(p)
        archivos.update(f.relative_to(origen).as_posix() for f in hallados)
    return sorted(archivos), faltan


def git(origen, *args):
    try:
        return subprocess.run(["git", *args], cwd=origen, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        return ""


def copiar(clave, origen):
    manifiesto, carpeta = FUENTES[clave]
    origen = Path(origen).expanduser().resolve()
    if not origen.is_dir():
        sys.exit(f"No existe la carpeta de origen de {clave}: {origen}")
    archivos, faltan = listar(origen, manifiesto)
    if faltan:
        sys.exit(f"{clave}: el manifiesto pide archivos que no están en {origen}:\n  " + "\n  ".join(faltan))
    destino = BASE / carpeta
    if destino.exists():
        shutil.rmtree(destino)
    for rel in archivos:
        t = destino / rel
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen / rel, t)
    cambios = git(origen, "status", "--porcelain", "--", *archivos)
    return {
        "remoto": git(origen, "remote", "get-url", "origin"),
        "rama": git(origen, "branch", "--show-current"),
        "commit": git(origen, "rev-parse", "HEAD"),
        "cambios_sin_commitear": bool(cambios),
        "archivos": {rel: huella(destino / rel) for rel in archivos},
    }


def verificar():
    """Devuelve la lista de problemas: archivos que faltan, sobran o no coinciden con ORIGEN.json."""
    origen = json.loads((BASE / "ORIGEN.json").read_text())
    problemas = []
    for clave, (_manifiesto, carpeta) in FUENTES.items():
        esperados = origen[clave]["archivos"]
        presentes = {f.relative_to(BASE / carpeta).as_posix() for f in (BASE / carpeta).rglob("*")
                     if f.is_file() and "__pycache__" not in f.parts and f.name != ".DS_Store"}
        problemas += [f"{carpeta}/{r}: falta" for r in sorted(set(esperados) - presentes)]
        problemas += [f"{carpeta}/{r}: no figura en ORIGEN.json" for r in sorted(presentes - set(esperados))]
        problemas += [f"{carpeta}/{r}: cambió (no se edita a mano)" for r in sorted(set(esperados) & presentes)
                      if huella(BASE / carpeta / r) != esperados[r]]
    return problemas


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--geneos-web", help="checkout de GENEOS WEB con public/ construido")
    ap.add_argument("--geagro", help="checkout del sitio publicado de GEAGRO (repo geagro-web)")
    ap.add_argument("--verificar", action="store_true")
    a = ap.parse_args()
    if a.verificar:
        problemas = verificar()
        print("\n".join(problemas) or "La base comercial coincide con ORIGEN.json.")
        sys.exit(1 if problemas else 0)
    if not (a.geneos_web and a.geagro):
        ap.error("indicá --geneos-web y --geagro (o --verificar)")
    origen = {"actualizado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "geneos": copiar("geneos", a.geneos_web), "geagro": copiar("geagro", a.geagro)}
    (BASE / "ORIGEN.json").write_text(json.dumps(origen, ensure_ascii=False, indent=1) + "\n")
    for clave in FUENTES:
        o = origen[clave]
        aviso = " (con cambios sin commitear en el origen)" if o["cambios_sin_commitear"] else ""
        print(f"{clave}: {len(o['archivos'])} archivos de {o['remoto'] or 'sin remoto'} · {o['rama']} @ {o['commit'][:7]}{aviso}")


if __name__ == "__main__":
    main()
