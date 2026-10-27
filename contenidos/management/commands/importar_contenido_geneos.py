"""Carga en Wagtail, como borrador, los textos actuales de la web de GENEOS (las plantillas rediseñadas de GENEOS WEB).

    python manage.py importar_contenido_geneos            # muestra qué haría, sin guardar nada
    python manage.py importar_contenido_geneos --guardar  # guarda borradores para revisar

Reglas:
  - Lee los textos de las plantillas: build.py los registra al generar (seccion(), logos_de()). GENEOS WEB no se modifica.
  - Nunca pisa un campo con contenido: si hay diferencias, las informa y las deja como están.
  - Guarda borradores (una revisión nueva de la página, logos sin publicar). No publica nada: la web no cambia.
  - Las imágenes de las secciones no se copian: un campo de imagen vacío mantiene la imagen actual de la web.
  - Los logos de clientes se cargan como «pendientes de autorización», con su archivo en la web actual (se conservan siempre).
"""
import html
import io
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from django.conf import settings
from django.core.files.images import ImageFile
from django.core.management.base import BaseCommand
from wagtail.images import get_image_model
from wagtail.models import Collection

from contenidos import geneos as G
from contenidos.models import LogoCliente, PaginaWeb, sitio_de_pagina
from sitios.models import SitioWeb


def a_texto(valor):
    """HTML de la plantilla a texto del administrador: <strong> → **, <br> → renglón nuevo."""
    t = re.sub(r"<br\s*/?>", "\n", valor or "")
    t = re.sub(r"</?strong>", "**", t)
    return html.unescape(re.sub(r"<[^>]+>", "", t)).strip()


class RutaTemporal(type(Path())):
    """build.py muestra cada archivo relativo a su carpeta; fuera de ella, la ruta completa."""

    def relative_to(self, *otros, **kw):
        try:
            return super().relative_to(*otros, **kw)
        except ValueError:
            return self


def leer_plantillas():
    """Genera GENEOS WEB en una carpeta temporal y devuelve los valores por defecto de cada sección."""
    raiz = Path(settings.GENEOS_WEB_DIR).resolve()
    previo = sys.modules.pop("build", None)
    sys.path.insert(0, str(raiz))
    try:
        import build as B  # noqa: E402  (GENEOS WEB/build.py: solo se lee)
    finally:
        sys.path.pop(0)
        sys.modules.pop("build", None)
        if previo is not None:
            sys.modules["build"] = previo
    if not hasattr(B, "SECCIONES_LEIDAS"):
        raise SystemExit("GENEOS WEB no tiene plantillas con secciones administrables (falta seccion() en build.py).")
    with tempfile.TemporaryDirectory() as tmp:
        B.OUT = RutaTemporal(tmp) / "public"
        with redirect_stdout(io.StringIO()):
            B.build()
    return B.SECCIONES_LEIDAS, raiz


class Command(BaseCommand):
    help = "Carga como borrador los textos actuales de la web de GENEOS (sin pisar contenido ni publicar)."

    def add_arguments(self, parser):
        parser.add_argument("--guardar", action="store_true", help="Guardar los borradores (sin esto solo muestra el plan).")

    def handle(self, *args, guardar=False, **kw):
        self.guardar = guardar
        leidas, raiz = leer_plantillas()
        sitio = SitioWeb.objects.get(clave="geneos")
        paginas = {p.ruta_publica: p for p in PaginaWeb.objects.all() if sitio_de_pagina(p) == sitio}
        for ruta in G.SECCIONES:
            if ruta not in paginas:
                self.stdout.write(f"Falta la página «{ruta or 'inicio'}» en Wagtail: no se importa.")
                continue
            self.pagina(paginas[ruta], leidas.get(ruta, {}))
        self.logos(sitio, leidas, raiz)
        if not guardar:
            self.stdout.write("\nNo se guardó nada. Para guardar los borradores: --guardar")

    # ------------------------------------------------------------------------------------------ páginas
    def pagina(self, live, defs):
        p = live.get_latest_revision_as_object()
        nombre = live.title
        cambios, conflictos = [], []

        def poner(campo, valor):
            actual = getattr(p, campo)
            if not valor:
                return
            if (actual or "").strip():
                if actual.strip() != valor.strip():
                    conflictos.append(f"{campo}: Wagtail «{actual.strip()[:60]}» / plantilla «{valor.strip()[:60]}»")
                return
            setattr(p, campo, valor)
            cambios.append(campo)

        hero = defs.get("hero") or {}
        poner("hero_antetitulo", a_texto(hero.get("antetitulo")))
        poner("hero_titulo", a_texto(hero.get("titulo")))
        poner("hero_bajada", a_texto(hero.get("bajada")))
        for n, b in enumerate(hero.get("botones") or [], 1):
            if n <= 2:
                poner(f"boton{n}_texto", a_texto(b.get("texto")))
                poner(f"boton{n}_enlace", b.get("enlace") or "")
        if hero.get("destacados"):
            if len(p.hero_destacados):
                conflictos.append("hero_destacados: ya tiene contenido; no se modifica")
            else:
                p.hero_destacados = [("destacado", {"clave": d.get("clave", ""), "icono": d.get("icono", ""), "texto": a_texto(d.get("texto"))})
                                     for d in hero["destacados"]]
                cambios.append("hero_destacados")

        if len(p.secciones):
            conflictos.append("secciones: ya tiene contenido; no se modifica")
        else:
            bloques = []
            for s in G.secciones_de(live.ruta_publica or ""):
                if s["clave"] == "hero":
                    continue
                d = defs.get(s["clave"])
                if s["tipo"] is None:
                    if s["mover"]:
                        bloques.append(("posicion", {"clave": s["clave"]}))
                    continue
                if d is None:
                    self.stdout.write(f"  Aviso: la plantilla no tiene la sección «{s['clave']}»")
                    continue
                v = {"clave": s["clave"], "antetitulo": a_texto(d.get("antetitulo")), "titulo": a_texto(d.get("titulo")),
                     "bajada": a_texto(d.get("bajada")), "boton_texto": a_texto((d.get("boton") or {}).get("texto")),
                     "boton_enlace": (d.get("boton") or {}).get("enlace", "")}
                if s["tipo"] == "texto_imagen":
                    v.update({"texto": a_texto(d.get("texto")), "imagen": None, "imagen_alt": a_texto(d.get("imagen_alt"))})
                if s["tipo"] == "tarjetas":
                    v["items"] = [{"clave": i.get("clave", ""), "icono": i.get("icono", ""), "titulo": a_texto(i.get("titulo")),
                                   "texto": a_texto(i.get("texto")), "imagen": None, "imagen_alt": a_texto(i.get("imagen_alt")),
                                   "enlace_texto": a_texto(i.get("enlace_texto")), "enlace": i.get("enlace", "")} for i in d.get("items") or []]
                bloques.append((s["tipo"], v))
            if bloques:
                p.secciones = bloques
                cambios.append(f"secciones ({len(bloques)})")

        self.stdout.write(f"\n{nombre} (/{live.ruta_publica}):")
        self.stdout.write("  Se completan: " + (", ".join(cambios) if cambios else "nada (ya tenía contenido o no hay textos)"))
        for c in conflictos:
            self.stdout.write("  Se conserva lo cargado en Wagtail: " + c)
        if self.guardar and cambios:
            p.save_revision(log_action=True)
            self.stdout.write("  Guardado como borrador (sin publicar).")

    # ------------------------------------------------------------------------------------------ logos
    def logos(self, sitio, leidas, raiz):
        Image = get_image_model()
        existentes = set(LogoCliente.objects.filter(sitio=sitio).values_list("archivo_web", flat=True))
        col = None
        nuevos = 0
        for ruta, defs in leidas.items():
            for clave, lista in defs.items():
                if not clave.startswith("logos:"):
                    continue
                for orden, item in enumerate(lista, 1):
                    archivo, enlace = (item[0], item[1]) if isinstance(item, (list, tuple)) else (item, "")
                    if archivo in existentes:
                        continue
                    nombre = re.sub(r"\s+\d+$", "", Path(archivo).stem.replace("Clientes-GENEOS_", "").replace("Busqueda", "Búsqueda")
                                    .replace("-", " ").replace("_", " "))
                    nuevos += 1
                    existentes.add(archivo)
                    if not self.guardar:
                        continue
                    origen = raiz / "static" / "assets" / "img" / Path(archivo).with_suffix(".webp")
                    if not origen.exists():
                        origen = raiz / "static" / "assets" / "img" / archivo
                    imagen = None
                    if origen.exists():
                        if col is None:
                            base = Collection.objects.filter(name="GENEOS", depth=2).first() or Collection.get_first_root_node()
                            col = base.get_children().filter(name="Logos de clientes (importados)").first() or base.add_child(
                                name="Logos de clientes (importados)")
                        with origen.open("rb") as f:
                            imagen = Image.objects.create(title=f"Logo {nombre}", collection=col, file=ImageFile(f, name=origen.name))
                    logo = LogoCliente(sitio=sitio, organizacion=nombre, imagen=imagen, enlace=enlace, paginas=[ruta], archivo_web=archivo,
                                       estado="pendiente", orden=orden, live=False,
                                       nota="Importado de la web actual: se conserva siempre. Falta registrar la autorización.")
                    logo.save()
                    logo.save_revision(log_action=True)
        self.stdout.write(f"\nLogos de clientes: {nuevos} para cargar como pendientes de autorización"
                          + (" (guardados como borrador)." if self.guardar else "."))
