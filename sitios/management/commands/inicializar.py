"""Carga inicial del administrador: sitios, líneas, páginas, grupos y permisos, flujo de aprobación y el contenido actual.

    python manage.py inicializar            # crea lo que falte y publica una primera versión local de cada web
    python manage.py inicializar --sin-publicar

Se puede ejecutar más de una vez: no duplica lo que ya existe.
El contenido se toma de las webs tal como las genera hoy el motor de sitios (renderer/) y de renderer/data/gerp.json,
así el punto de partida es exactamente lo que está publicado. No inventa planes, precios ni prestaciones.
"""
import ast
import shutil
import html as htmllib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction
from wagtail.models import (Collection, GroupCollectionPermission, GroupPagePermission, Page, Site, Workflow, WorkflowContentType,
                            WorkflowPage, WorkflowTask)

from contenidos.models import (BlogIndexPage, Funcionalidad, PaginaWeb, Plan, PreguntaFrecuente, Redireccion, Sector, Testimonio,
                               ValorFuncionalidad)
from sitios.models import AccesoSitio, AprobacionSitio, LineaProducto, SitioWeb

FUENTE = "gerp.ar, octubre 2026"

SITIOS = [
    dict(clave="geneos", nombre="GENEOS", motor="institucional", dominio="https://geneos.coop.ar", dominio_confirmado=True, color="#178943", orden=0,
         usa_blog=True, usa_planes=False, usa_comparador=False, usa_testimonios=False, usa_formularios=False),
    dict(clave="gerp", nombre="GERP", dominio="https://gerp.ar", dominio_confirmado=True, color="#254d99", orden=1,
         usa_blog=False, usa_planes=True, usa_comparador=True, usa_testimonios=True),
    dict(clave="geagro", nombre="GEAGRO", dominio="https://geagro.ar", dominio_confirmado=True, color="#22b24c", orden=2,
         usa_blog=True, usa_planes=True),
    # gema.geneos.com.ar hoy sirve la landing comercial vieja. Queda sin confirmar hasta que Infra defina dónde vive la aplicación.
    dict(clave="gema", nombre="GEMA", dominio="https://gema.geneos.com.ar", dominio_confirmado=False, color="#e2231a", orden=3,
         usa_blog=False, usa_planes=True),
]
LINEAS = {"geagro": [dict(clave="cereales", nombre="Cereales", ruta="cereales/", color="#22b24c", orden=1),
                     dict(clave="vid", nombre="Vid", ruta="vid/", color="#7b2346", orden=2)]}
CARPETAS = {"gerp": "gerp-web", "geagro": "geagro-web", "gema": "gema-web"}
PAGINAS = {  # páginas comerciales editables (las landings de GERP Lite/Core/Plus se editan desde cada plan)
    "gerp": [("", "GERP · Inicio", None)],
    "geagro": [("", "GEAGRO · Inicio", None), ("cereales/", "GEAGRO CEREALES", "cereales"), ("vid/", "GEAGRO VID", "vid")],
    "gema": [("", "GEMA · Inicio", None)],
}
# Importes tal como están publicados hoy (octubre 2026):
#   GEAGRO: https://geagro.ar/ (sin leyenda de vigencia)
#   GEMA:   https://geneos.coop.ar/index.php/software-gestion-matafuegos-extintores/
#   GERP:   https://gerp.ar/index.php/planes-precios-erp-gerp/ (renderer/data/gerp.json)
VIGENCIA_GERP = "Los valores informados son precios vigentes hasta diciembre 2026"
PLANES_SIMPLES = {
    "geagro": [dict(clave="lite", nombre="Lite", precio="89.250", implementacion="624.750", color="#22b24c", orden=1),
               dict(clave="plus", nombre="Plus", precio="178.500", implementacion="1.071.000", color="#0b3422", orden=2, destacado=True)],
    "gema": [dict(clave="mensual", nombre="Plan mensual", precio="89.250", implementacion="349.750", orden=1,
                  leyenda_vigencia="Precios válidos para Octubre, Noviembre y Diciembre. Actualización bimestral.",
                  publico_corto="Plataforma online personalizada",
                  caracteristicas="Plataforma online personalizada\nCarga ILIMITADA de clientes\nUso de todas las funciones")],
}
PERMISOS_PAGINA = {"editor": ["add_page", "change_page", "lock_page"],
                   "publicador": ["add_page", "change_page", "lock_page", "publish_page", "unlock_page"],
                   "administrador": ["add_page", "change_page", "lock_page", "publish_page", "unlock_page", "bulk_delete_page"]}
PERMISOS_COLECCION = {"editor": ["add_image", "change_image", "choose_image", "add_document", "change_document", "choose_document"],
                      "publicador": ["add_image", "change_image", "choose_image", "add_document", "change_document", "choose_document"],
                      "administrador": ["add_image", "change_image", "choose_image", "delete_image",
                                        "add_document", "change_document", "choose_document", "delete_document"]}
ROLES = [("editor", "Editor"), ("publicador", "Publicador"), ("administrador", "Administrador")]


def texto(fragmento):
    return htmllib.unescape(re.sub(r"<[^>]+>", "", fragmento or "")).strip()


def a_negritas(fragmento):
    """<strong>x</strong> → **x** (formato de los campos de texto del administrador)."""
    fragmento = re.sub(r"<(strong|b)>(.*?)</\1>", r"**\2**", fragmento or "", flags=re.S)
    return texto(fragmento)


def enlaces_absolutos(fragmento, ruta):
    """href relativos de la web generada → rutas del sitio (/cereales/). Así sirven desde cualquier página."""
    def rep(m):
        href = m.group(1)
        if href.startswith(("#", "http://", "https://", "mailto:", "tel:", "/")):
            return m.group(0)
        return f'href="{urljoin("/" + ruta, href)}"'
    fragmento = re.sub(r'href="([^"]*)"', rep, fragmento)
    return fragmento.replace("<strong>", "<b>").replace("</strong>", "</b>").replace("<em>", "<i>").replace("</em>", "</i>")


def leer_pagina(carpeta, ruta):
    f = Path(carpeta) / ruta / "index.html"
    if not f.exists():
        return None
    t = f.read_text()
    d = {"title": texto((re.search(r"<title>(.*?)</title>", t, re.S) or [None, ""])[1]),
         "description": htmllib.unescape((re.search(r'<meta name="description" content="([^"]*)"', t) or [None, ""])[1])}
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", t, re.S)
    if h1:
        inner = re.sub(r'<span class="pp-hl">(.*?)</span>', r"**\1**", h1.group(1), flags=re.S)
        lineas = re.findall(r"<span>(.*?)</span>|(\*\*.*?\*\*)", inner, re.S)
        d["h1"] = "\n".join(texto(a or b) for a, b in lineas) if lineas else texto(inner)
    lead = re.search(r'class="pp-hero-lead">(.*?)</p>', t, re.S)
    d["lead"] = a_negritas(lead.group(1)) if lead else ""
    acc = re.search(r'class="pp-hero-actions">(.*?)</div>', t, re.S)
    d["actions"] = [(texto(lbl), href) for href, lbl in re.findall(r'<a class="pp-btn[^"]*"\s+href="([^"]*)"[^>]*>(.*?)(?:<svg|</a>)', acc.group(1), re.S)] if acc else []
    d["faqs"] = [(texto(q), enlaces_absolutos(a.strip(), ruta))
                 for q, a in re.findall(r'<summary>(.*?)</summary>\s*<div class="pp-faq-answer">(.*?)</div>', t, re.S)]
    return d


def paginas_geneos():
    """Rutas, títulos y descripciones de la web institucional (GENEOS WEB/build.py → PAGES)."""
    f = Path(settings.GENEOS_WEB_DIR) / "build.py"
    if not f.exists():
        return []
    arbol = ast.parse(f.read_text())
    res = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Assign) and any(getattr(t, "id", None) == "PAGES" for t in nodo.targets) and isinstance(nodo.value, ast.List):
            for el in nodo.value.elts:
                if isinstance(el, ast.Call):
                    kw = {}
                    for k in el.keywords:
                        try:
                            kw[k.arg] = ast.literal_eval(k.value)
                        except ValueError:
                            pass
                    if kw.get("out", "").endswith("/") or kw.get("out") == "":
                        res.append(kw)
    return res


class Command(BaseCommand):
    help = "Crea los sitios, permisos y flujo de aprobación, e importa el contenido actual de las webs."

    def add_arguments(self, parser):
        parser.add_argument("--sin-publicar", action="store_true", help="No generar la primera versión local de cada web.")

    def log(self, msg):
        self.stdout.write(msg)

    def handle(self, *args, **opts):
        Path(settings.GWA_VAR_DIR).mkdir(parents=True, exist_ok=True)
        base = Path(tempfile.mkdtemp(prefix="gwa-base-", dir=settings.GWA_VAR_DIR))
        self.generar_base(base)
        with transaction.atomic():
            sitios = self.sitios()
            self.gerp(sitios["gerp"])  # primero los planes: las preguntas frecuentes los referencian
            self.planes_simples(sitios)
            self.paginas(sitios, base)
            self.colecciones_y_grupos(sitios)
            self.flujo()
        shutil.rmtree(base, ignore_errors=True)
        if not opts["sin_publicar"]:
            from publicacion.servicio import publicar_sitio
            for clave in ("gerp", "geagro", "gema"):
                s = SitioWeb.objects.get(clave=clave)
                if not s.despliegues.filter(estado="ok").exists():
                    d = publicar_sitio(s, None, "Versión inicial (contenido importado)")
                    self.log(f"  Web {s.nombre}: {'publicada localmente' if d.estado == 'ok' else 'ERROR: ' + d.registro[-500:]}")
        self.log(self.style.SUCCESS("Listo. Entrá a http://localhost:8000/admin/"))

    # ----------------------------------------------------------------------------------------------------------------
    def generar_base(self, base):
        """Genera las webs comerciales con las plantillas actuales (sin datos del administrador) para leer su contenido."""
        env = dict(os.environ, GENEOS_WEB_DIR=str(settings.GENEOS_WEB_DIR), GEAGRO_SRC_DIR=str(settings.GEAGRO_SRC_DIR))
        env.pop("WEB_DATA_DIR", None)
        for clave in CARPETAS:
            r = subprocess.run([sys.executable, str(Path(settings.GWA_RENDERER_DIR) / "export.py"), clave, "--out", str(base), "--no-project-files"],
                               capture_output=True, text=True, env=env)
            if r.returncode != 0:
                self.log(self.style.WARNING(f"No se pudo leer la web de {clave}: {r.stderr[-600:]}"))

    def sitios(self):
        res = {}
        raiz = Page.get_first_root_node()
        # La página de bienvenida que crea Wagtail no se usa
        for p in Page.objects.filter(depth=2, content_type=ContentType.objects.get_for_model(Page)):
            Site.objects.filter(root_page=p).delete()
            p.delete()
        raiz.refresh_from_db()
        for datos in SITIOS:
            datos = dict(datos)
            clave = datos.pop("clave")
            s, nuevo = SitioWeb.objects.get_or_create(clave=clave, defaults=datos)
            if s.site is None:
                inicio = PaginaWeb(title=f"{s.nombre} · Inicio", slug=clave, ruta_publica="")
                raiz.add_child(instance=inicio)
                s.site = Site.objects.create(hostname=f"{clave}.localhost", port=80, root_page=inicio, site_name=s.nombre,
                                             is_default_site=(clave == "geneos"))
                s.save()
            for l in LINEAS.get(clave, []):
                LineaProducto.objects.get_or_create(sitio=s, clave=l["clave"], defaults=l)
            res[clave] = s
            self.log(f"Sitio {s.nombre}{' (nuevo)' if nuevo else ''}")
        return res

    def publicar(self, obj):
        obj.save_revision().publish()

    def faqs(self, sitio, ruta, items, linea=None, precios=None):
        if PreguntaFrecuente.objects.filter(sitio=sitio, ubicacion=ruta).exists():
            return
        for i, (q, a) in enumerate(items, 1):
            for valor, token in (precios or {}).items():  # el importe escrito pasa a ser una referencia al plan
                a = a.replace(f"${valor} + IVA", token).replace(f"${valor}", token)
            f = PreguntaFrecuente(sitio=sitio, linea=linea, ubicacion=ruta, pregunta=q, respuesta=a, orden=i, live=False)
            f.save()
            self.publicar(f)

    def paginas(self, sitios, base):
        for clave, lista in PAGINAS.items():
            s = sitios[clave]
            inicio = s.site.root_page.specific
            precios = {}
            for p in PLANES_SIMPLES.get(clave, []):
                precios[p["precio"]] = f"[precio:{p['clave']}]"
                precios[p["implementacion"]] = f"[implementacion:{p['clave']}]"
            if clave == "gerp":
                import json as _json
                for it in _json.loads((Path(settings.GWA_RENDERER_DIR) / "data" / "gerp.json").read_text())["plans"]:
                    precios[it["price"]] = f"[precio:{it['key']}]"
                    precios[it["impl"]] = f"[implementacion:{it['key']}]"
            for ruta, titulo, linea_clave in lista:
                linea = LineaProducto.objects.get(sitio=s, clave=linea_clave) if linea_clave else None
                if ruta == "":
                    pag = inicio
                else:
                    pag = PaginaWeb.objects.child_of(inicio).filter(ruta_publica=ruta).first()
                    if pag is None:
                        pag = PaginaWeb(title=titulo, slug=ruta.strip("/"), ruta_publica=ruta, linea=linea)
                        inicio.add_child(instance=pag)
                if pag.hero_titulo:  # ya importada
                    continue
                d = leer_pagina(base / CARPETAS[clave], ruta)
                if not d:
                    continue
                pag.title, pag.linea = titulo, linea
                pag.seo_title, pag.search_description = d["title"], d["description"]
                pag.hero_titulo, pag.hero_bajada = d.get("h1", ""), d["lead"]
                for i, (lbl, href) in enumerate(d["actions"][:2], 1):
                    setattr(pag, f"boton{i}_texto", lbl)
                    setattr(pag, f"boton{i}_enlace", href)
                pag.save()
                self.publicar(pag)
                self.faqs(s, ruta, d["faqs"], linea, precios)
                self.log(f"  Página {s.nombre} /{ruta}: título, SEO, botones y {len(d['faqs'])} preguntas frecuentes")
            # Blogs en borrador (se publican cuando tengan artículos)
            if s.usa_blog:
                for ruta, titulo, linea_clave in [("blog/", f"Blog de {s.nombre}", None)] + \
                        [(l.ruta + "blog/", f"Blog de {s.nombre} {l.nombre}", l.clave) for l in s.lineas.all()]:
                    padre = inicio if linea_clave is None else PaginaWeb.objects.child_of(inicio).get(linea__clave=linea_clave)
                    if not BlogIndexPage.objects.child_of(padre).exists():
                        b = BlogIndexPage(title=titulo, slug="blog", ruta_publica=ruta, live=False, reune_lineas=linea_clave is None,
                                          linea=LineaProducto.objects.filter(sitio=s, clave=linea_clave).first() if linea_clave else None,
                                          seo_title=f"{titulo} | {s.nombre}")
                        padre.add_child(instance=b)
                        b.save_revision()
        # Web institucional: rutas y SEO (el diseño se conecta en la etapa 7)
        g = sitios["geneos"]
        inicio = g.site.root_page.specific
        por_ruta = {"": inicio}
        for kw in paginas_geneos():
            ruta = kw["out"]
            if ruta == "":
                pag = inicio
            else:
                padre = por_ruta.get(kw.get("parent", ""), inicio)
                pag = PaginaWeb.objects.filter(ruta_publica=ruta).descendant_of(inicio).first()
                if pag is None:
                    pag = PaginaWeb(title=kw.get("crumb") or ruta.strip("/"), slug=ruta.strip("/").split("/")[-1], ruta_publica=ruta)
                    padre.add_child(instance=pag)
            por_ruta[ruta] = pag
            if not pag.seo_title:
                pag.seo_title, pag.search_description = kw.get("title", ""), kw.get("description", "")
                if ruta == "":
                    pag.title = "GENEOS · Inicio"
                pag.save()
                self.publicar(pag)
        self.log(f"  Web institucional: {len(por_ruta)} páginas con su SEO")

    def colecciones_y_grupos(self, sitios):
        raiz_col = Collection.get_first_root_node()
        acceso = Permission.objects.get(content_type__app_label="wagtailadmin", codename="access_admin")

        def coleccion(nombre, padre):
            c = padre.get_children().filter(name=nombre).first()
            return c or padre.add_child(name=nombre)

        def grupo(nombre, sitio, linea, rol, pagina, col):
            g, nuevo = Group.objects.get_or_create(name=nombre)
            if not nuevo:
                return g
            g.permissions.add(acceso)
            AccesoSitio.objects.get_or_create(grupo=g, sitio=sitio, linea=linea, rol=rol)
            for cod in PERMISOS_PAGINA[rol]:
                GroupPagePermission.objects.get_or_create(group=g, page=pagina, permission=Permission.objects.get(content_type__app_label="wagtailcore", codename=cod))
            for cod in PERMISOS_COLECCION[rol]:
                app = "wagtailimages" if cod.endswith("image") else "wagtaildocs"
                GroupCollectionPermission.objects.get_or_create(group=g, collection=col, permission=Permission.objects.get(content_type__app_label=app, codename=cod))
            return g

        for s in sitios.values():
            col = coleccion(s.nombre, raiz_col)
            inicio = s.site.root_page
            for rol, nombre in ROLES:
                grupo(f"{s.nombre} · {nombre}", s, None, rol, inicio, col)
            for l in s.lineas.all():
                col_l = coleccion(l.nombre, col)
                pag = PaginaWeb.objects.child_of(inicio).filter(linea=l).first() or inicio
                for rol, nombre in ROLES:
                    grupo(f"{s.nombre} {l.nombre} · {nombre}", s, l, rol, pag, col_l)
        self.log("  Grupos por sitio y línea: Editor, Publicador y Administrador")

    def flujo(self):
        tarea = AprobacionSitio.objects.first()
        if tarea is None:
            tarea = AprobacionSitio.objects.create(name="Aprobación del publicador del sitio")
        tarea.groups.set(Group.objects.filter(accesos_sitio__rol__in=["publicador", "administrador"]).distinct())
        wf, _ = Workflow.objects.get_or_create(name="aprobación")
        WorkflowTask.objects.get_or_create(workflow=wf, task=tarea.task_ptr, defaults={"sort_order": 0})
        Workflow.objects.exclude(pk=wf.pk).update(active=False)
        WorkflowPage.objects.update_or_create(page=Page.get_first_root_node(), defaults={"workflow": wf})
        for model in (Plan, PreguntaFrecuente, Testimonio):
            WorkflowContentType.objects.update_or_create(content_type=ContentType.objects.get_for_model(model), defaults={"workflow": wf})
        self.log("  Flujo de aprobación asignado a páginas, planes, preguntas frecuentes y testimonios")

    def gerp(self, s):
        if Plan.objects.filter(sitio=s).exists():
            return
        d = json.loads((Path(settings.GWA_RENDERER_DIR) / "data" / "gerp.json").read_text())
        planes = {}
        for i, it in enumerate(d["plans"], 1):
            p = Plan(sitio=s, clave=it["key"], nombre=it["name"], etiqueta=it.get("label", ""), precio=it["price"], implementacion=it.get("impl", ""),
                     leyenda_vigencia=VIGENCIA_GERP, vigente_hasta=date(2026, 12, 31), destacado=bool(it.get("featured")), orden=i, publico_corto=it.get("short", ""),
                     publico=it.get("audience", ""), caracteristicas="\n".join(it.get("card_feats", [])), ruta=it.get("slug", ""),
                     titulo_landing="\n".join(it.get("h1", [])), titulo_seo=it.get("title", ""), descripcion_seo=it.get("description", ""),
                     color=it.get("color", ""), color_acento=it.get("accent", ""), color_hover=it.get("hover", ""), color_suave=it.get("soft", ""),
                     icono=it.get("icon", ""), logo_blanco=it.get("logo_white", ""), nota_funciones=it.get("functions_note", ""), live=False)
            p.modulos = [("modulo", {"icono": m["icon"], "titulo": m["title"], "texto": m["text"]}) for m in it.get("modules", [])]
            p.funciones = [("grupo", {"icono": g["icon"], "titulo": g["title"], "items": [{"titulo": a, "texto": b} for a, b in g["checks"]]})
                           for g in it.get("functions", [])]
            p.save()
            self.publicar(p)
            planes[p.clave] = p
            self.faqs(s, p.ruta, [(q, a if a.startswith("<") else f"<p>{a}</p>") for q, a in it.get("faqs", [])],
                      precios={x["price"]: f"[precio:{x['key']}]" for x in d["plans"]} | {x["impl"]: f"[implementacion:{x['key']}]" for x in d["plans"]})
        for i, f in enumerate(d["features"], 1):
            func = Funcionalidad(sitio=s, etiqueta=f["label"], grupo=f["group"], resumen=f.get("summary", f["group"] == "basic") is not False, orden=i)
            valores = []
            for clave, v in f["values"].items():
                estado = {True: "incluido", False: "no_incluido", None: "a_confirmar"}.get(v, "texto") if not isinstance(v, str) else "texto"
                valores.append(ValorFuncionalidad(plan=planes[clave], estado=estado, texto=v if isinstance(v, str) else "", fuente=FUENTE))
            func.valores = valores
            func.save()
        for i, x in enumerate(d["sectors"], 1):
            Sector.objects.create(sitio=s, titulo=x["title"], texto=x["text"], icono=x["icon"], orden=i)
        for t in d["testimonials"]:
            tt = Testimonio(sitio=s, empresa=t["company"], texto=t.get("text") or "", estado="pendiente", nota=(t.get("pending") or "")[:200], live=False)
            tt.save()
            self.publicar(tt)
        for origen, destino in d["redirects"]:
            Redireccion.objects.create(sitio=s, origen=origen, destino=destino)
        self.log(f"  GERP: {len(planes)} planes, {len(d['features'])} funcionalidades del comparador, {len(d['sectors'])} sectores, "
                 f"{len(d['testimonials'])} testimonios pendientes de autorización, {len(d['redirects'])} redirecciones")

    def planes_simples(self, sitios):
        for clave, lista in PLANES_SIMPLES.items():
            s = sitios[clave]
            if Plan.objects.filter(sitio=s).exists():
                continue
            for datos in lista:
                p = Plan(sitio=s, live=False, **datos)
                p.save()
                self.publicar(p)
            self.log(f"  {s.nombre}: {len(lista)} plan(es)")
