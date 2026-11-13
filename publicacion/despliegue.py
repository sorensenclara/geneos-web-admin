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


# ------------------------------------------------------------------------------------------------ Repositorio git (web-*)
# Archivos propios del repositorio que la publicación no toca (workflow, README, dominio). El resto es la web generada.
CONSERVAR_EN_REPO = {".git", ".github", "README.md", "CNAME", "CNAME.example", ".gitignore", ".nojekyll"}
AUTOR = ("GENEOS Web Admin", "no-responder@geneos.com.ar")
# Un workflow que vuelve a generar la web por su cuenta pisaría lo que publica el administrador.
WORKFLOW_QUE_REGENERA = ("export.py", "geneos-web-admin", "build.py")


class ErrorRepositorio(Exception):
    pass


def repo_dir(sitio):
    return Path(settings.GWA_VAR_DIR) / "repos" / sitio.clave


def _git(cwd, *args, timeout=300):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="echo", LC_ALL="C")
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        raise ErrorRepositorio(f"git {' '.join(args[:2])}: {(r.stderr or r.stdout).strip()[-1500:]}")
    return r.stdout.strip()


def preparar_repo(sitio):
    """Clon de trabajo al día con la rama remota (sin cambios locales). Devuelve su carpeta."""
    if not sitio.repo_url.strip():
        raise ErrorRepositorio(f"{sitio.nombre} no tiene cargado el repositorio de la web (Configuración del sitio → Publicación).")
    d, rama = repo_dir(sitio), sitio.repo_rama or "main"
    if (d / ".git").exists() and _git(d, "remote", "get-url", "origin") != sitio.repo_url.strip():
        shutil.rmtree(d)
    if not (d / ".git").exists():
        d.parent.mkdir(parents=True, exist_ok=True)
        _git(d.parent, "clone", "--branch", rama, "--single-branch", sitio.repo_url.strip(), d.name)
    else:
        _git(d, "fetch", "--prune", "origin", rama)
        _git(d, "checkout", "-q", "-B", rama, f"origin/{rama}")
        _git(d, "reset", "--hard", "-q", f"origin/{rama}")
        _git(d, "clean", "-fdxq")
    return d


def workflow_regenera(worktree):
    """Workflows del repositorio que generan la web por su cuenta (y pisarían lo publicado)."""
    wf = Path(worktree) / ".github" / "workflows"
    return sorted(f.name for f in wf.glob("*.y*ml") if any(t in f.read_text(errors="ignore") for t in WORKFLOW_QUE_REGENERA)) if wf.exists() else []


def _vaciar(worktree):
    for f in Path(worktree).iterdir():
        if f.name not in CONSERVAR_EN_REPO:
            shutil.rmtree(f) if f.is_dir() and not f.is_symlink() else f.unlink()


def _confirmar(worktree, sitio, mensaje):
    """Commit y push de lo que haya en el clon. Devuelve (commit, hubo_cambios). Si el push falla, el remoto no cambia."""
    _git(worktree, "add", "-A")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=worktree).returncode == 0:
        return _git(worktree, "rev-parse", "HEAD"), False
    _git(worktree, "-c", f"user.name={AUTOR[0]}", "-c", f"user.email={AUTOR[1]}", "commit", "-q", "-m", mensaje)
    commit = _git(worktree, "rev-parse", "HEAD")
    try:
        _git(worktree, "push", "origin", f"HEAD:{sitio.repo_rama or 'main'}")
    except ErrorRepositorio:
        _git(worktree, "reset", "--hard", "-q", f"origin/{sitio.repo_rama or 'main'}")
        raise
    return commit, True


def publicar_en_repo(sitio, carpeta_web, mensaje):
    """Reemplaza la web del repositorio por `carpeta_web` (conserva workflow, README y CNAME), commit y push."""
    d = preparar_repo(sitio)
    if workflow_regenera(d):
        raise ErrorRepositorio("El repositorio tiene un workflow que vuelve a generar la web por su cuenta: " + ", ".join(workflow_regenera(d)))
    _vaciar(d)
    for f in Path(carpeta_web).iterdir():
        if f.name in CONSERVAR_EN_REPO:
            continue
        (shutil.copytree(f, d / f.name) if f.is_dir() else shutil.copy2(f, d / f.name))
    return _confirmar(d, sitio, mensaje)


def restaurar_en_repo(sitio, commit, mensaje):
    """Vuelve la web del repositorio a como estaba en `commit` con un commit nuevo (el historial no se reescribe)."""
    d = preparar_repo(sitio)
    _git(d, "cat-file", "-e", f"{commit}^{{commit}}")
    _vaciar(d)
    archivos = [a for a in _git(d, "ls-tree", "-r", "--name-only", commit).splitlines() if a.split("/")[0] not in CONSERVAR_EN_REPO]
    for i in range(0, len(archivos), 200):
        _git(d, "checkout", commit, "--", *archivos[i:i + 200])
    return _confirmar(d, sitio, mensaje)
