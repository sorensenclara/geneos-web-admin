"""Generación y publicación de los sitios estáticos.

publish_site(): exporta el contenido publicado a JSON → ejecuta el exportador actual en una carpeta nueva
(releases/<fecha>) → valida el resultado → recién entonces cambia el enlace 'current' (cambio atómico).
Si algo falla, el enlace sigue apuntando a la versión anterior y el error queda en PublishJob.
En producción, el último paso es un despliegue atómico (Cloudflare Pages / GitHub Pages) desde la rama del sitio.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

TOOLS = Path(settings.WEB_TOOLS_DIR)          # GENEOS WEB/tools/sitios-comerciales
ROOT = Path(settings.WEB_PUBLIC_ROOT)          # carpeta de versiones públicas
PREVIEWS = Path(settings.WEB_PREVIEW_ROOT)


def build_data(site, override=None):
    """JSON del sitio a partir de la base: contenido publicado (+ un borrador, para la vista previa)."""
    from .models import Plan
    data = json.loads((TOOLS / "data" / f"{site}.json").read_text())
    live = {p.key: p for p in Plan.objects.filter(site=site, live=True)}
    if override is not None:
        live[override.key] = override
    for item in data["plans"]:
        p = live.get(item["key"])
        if p:
            item.update(name=p.name, price=p.price, price_num=p.price_num, impl=p.impl)
    return data


def run_export(site, data, out):
    tmpdata = Path(out).parent / f".data-{uuid.uuid4().hex[:8]}"
    tmpdata.mkdir(parents=True)
    shutil.copy(TOOLS / "data" / "contacto.json", tmpdata / "contacto.json")
    (tmpdata / f"{site}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    env = dict(os.environ, WEB_DATA_DIR=str(tmpdata))
    r = subprocess.run([sys.executable, str(TOOLS / "export.py"), site, "--out", str(out)],
                       capture_output=True, text=True, env=env, timeout=300)
    shutil.rmtree(tmpdata, ignore_errors=True)
    return r


def validate(site, data, folder):
    """Controles mínimos antes de reemplazar la versión pública."""
    errors = []
    pages = [folder / "index.html"] + [folder / p["slug"] / "index.html" for p in data.get("plans", [])]
    for f in pages:
        if not f.exists():
            errors.append(f"Falta {f.relative_to(folder)}")
            continue
        html = f.read_text()
        if html.count("<h1") != 1:
            errors.append(f"{f.relative_to(folder)}: debe tener un H1")
    home = (folder / "index.html").read_text() if (folder / "index.html").exists() else ""
    for p in data.get("plans", []):
        if f"${p['price']}" not in home:
            errors.append(f"El precio de {p['name']} no aparece en la home")
    return errors


def publish_site(site, trigger):
    from .models import PublishJob
    job = PublishJob.objects.create(site=site, trigger=trigger)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    releases = ROOT / site / "releases"
    target = releases / stamp
    log = []
    try:
        data = build_data(site)
        r = run_export(site, data, target)
        log.append(r.stdout[-3000:])
        if r.returncode != 0:
            raise RuntimeError("El generador terminó con error:\n" + r.stderr[-3000:])
        folder = target / f"{site}-web"
        errors = validate(site, data, folder)
        if errors:
            raise RuntimeError("Validación: " + "; ".join(errors))
        current = ROOT / site / "current"
        tmp_link = ROOT / site / f".current-{stamp}"
        tmp_link.symlink_to(folder)
        os.replace(tmp_link, current)  # cambio atómico: los visitantes ven la versión vieja o la nueva, nunca una mezcla
        job.status, job.release = "ok", stamp
    except Exception as e:  # la versión pública anterior queda intacta
        job.status = "failed"
        log.append(str(e))
        shutil.rmtree(target, ignore_errors=True)
    job.log = "\n".join(log)
    job.finished = timezone.now()
    job.save()
    return job


def render_preview(plan, mode):
    token = uuid.uuid4().hex[:12]
    out = PREVIEWS / token
    data = build_data(plan.site, override=plan)
    r = run_export(plan.site, data, out)
    if r.returncode != 0:
        return HttpResponse(f"<h1>No se pudo generar la vista previa</h1><pre>{r.stderr[-2000:]}</pre>", status=500)
    folder = out / f"{plan.site}-web"
    page = folder / ("index.html" if mode == "home" else f"{plan.key}/index.html")
    html = page.read_text()
    base = f"/__preview/{token}/{plan.site}-web/" + ("" if mode == "home" else f"{plan.key}/")
    html = re.sub(r"<head>", f'<head><base href="{base}">', html, count=1)
    return HttpResponse(html)
