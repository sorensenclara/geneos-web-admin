"""Generador de los sitios comerciales: base propia, independencia de carpetas externas, recursos y reproducibilidad.

Estas pruebas no usan la base de datos: generan GERP, GEAGRO y GEMA con los datos de renderer/data/ y la base
versionada de renderer/base/, como lo haría cualquier computadora con solo este repositorio.
"""
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from publicacion.comparar import comparar, referencias_rotas, sin_diferencias, texto_visible

RENDERER = Path(settings.GWA_RENDERER_DIR)
REPO = RENDERER.parent
SITIOS = {"gerp": "gerp-web", "gema": "gema-web", "geagro": "geagro-web"}

# Se ejecuta en lugar de export.py: registra cada archivo que se abre dentro de la carpeta personal real
# y fuera de este repositorio y de la salida (donde estaban GENEOS WEB y la copia local de GEAGRO).
VIGIA = '''
import os, sys, runpy
casa = os.path.realpath(os.environ["VIGIA_CASA"])
permitidas = [os.path.realpath(p) for p in os.environ["VIGIA_PERMITIDAS"].split(os.pathsep)]
registro = open(os.environ["VIGIA_REGISTRO"], "a")
def vigia(evento, args):
    if evento in ("open", "os.listdir", "os.scandir") and args and isinstance(args[0], (str, bytes, os.PathLike)):
        p = os.path.realpath(os.fsdecode(args[0]))
        if p.startswith(casa + os.sep) and not any(p == a or p.startswith(a + os.sep) for a in permitidas):
            registro.write(p + "\\n")
sys.addaudithook(vigia)
sys.argv = [os.environ["VIGIA_EXPORT"]] + sys.argv[1:]
runpy.run_path(os.environ["VIGIA_EXPORT"], run_name="__main__")
'''

def huellas(carpeta):
    return {f.relative_to(carpeta).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted(Path(carpeta).rglob("*")) if f.is_file()}


class BaseComercial(SimpleTestCase):
    """Genera los tres sitios una vez sin acceso a carpetas externas; las pruebas leen ese resultado."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = Path(tempfile.mkdtemp(prefix="gwa-base-"))
        vigia = cls.tmp / "vigia.py"
        vigia.write_text(VIGIA)
        casa_falsa = cls.tmp / "casa"
        casa_falsa.mkdir()
        cls.resultado = {}
        for corrida in ("a", "b"):
            for clave in SITIOS:
                registro = cls.tmp / f"abiertos-{clave}-{corrida}.txt"
                registro.write_text("")
                env = {k: v for k, v in os.environ.items() if k not in ("WEB_DATA_DIR", "GENEOS_WEB_DIR", "GEAGRO_SRC_DIR")}
                env.update(HOME=str(casa_falsa), GENEOS_WEB_DIR="/no/existe/GENEOS WEB", GEAGRO_SRC_DIR="/no/existe/geagro",
                           VIGIA_CASA=str(Path.home()), VIGIA_PERMITIDAS=os.pathsep.join([str(REPO), str(cls.tmp), sys.prefix, sys.base_prefix]),
                           VIGIA_REGISTRO=str(registro), VIGIA_EXPORT=str(RENDERER / "export.py"), PYTHONDONTWRITEBYTECODE="1")
                r = subprocess.run([sys.executable, str(vigia), clave, "--out", str(cls.tmp / corrida), "--no-project-files"],
                                   capture_output=True, text=True, env=env, timeout=600, cwd=str(cls.tmp))
                cls.resultado[(clave, corrida)] = (r, registro.read_text().split())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        super().tearDownClass()

    def test_base_coincide_con_origen(self):
        spec = importlib.util.spec_from_file_location("actualizar_base", REPO / "scripts" / "actualizar_base_comercial.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.verificar(), [])
        for clave, (manifiesto, carpeta) in mod.FUENTES.items():
            _archivos, faltan = mod.listar(mod.BASE / carpeta, manifiesto)
            self.assertEqual(faltan, [], f"{manifiesto}: patrones sin archivos en la base")

    def test_genera_sin_carpetas_externas(self):
        for clave in SITIOS:
            r, abiertos = self.resultado[(clave, "a")]
            self.assertEqual(r.returncode, 0, f"{clave}: el generador falló\n{r.stderr[-2000:]}")
            self.assertNotIn("FALTAN", r.stdout, f"{clave}: recursos faltantes\n{r.stdout[-2000:]}")
            self.assertEqual(abiertos, [], f"{clave}: leyó archivos fuera del repositorio")

    def test_recursos_referenciados_existen(self):
        for clave, carpeta in SITIOS.items():
            web = self.tmp / "a" / carpeta
            self.assertTrue((web / "index.html").exists(), clave)
            self.assertEqual(referencias_rotas(web), [], f"{clave}: referencias a archivos que no están")

    def test_dos_generaciones_dan_los_mismos_archivos(self):
        for carpeta in SITIOS.values():
            a, b = huellas(self.tmp / "a" / carpeta), huellas(self.tmp / "b" / carpeta)
            self.assertEqual(sorted(a), sorted(b), f"{carpeta}: cambian los archivos")
            distintos = [k for k in a if a[k] != b[k]]
            self.assertEqual(distintos, [], f"{carpeta}: cambia el contenido de estos archivos entre dos generaciones")

    def test_secciones_y_seo_completos(self):
        for clave, carpeta in SITIOS.items():
            web = self.tmp / "a" / carpeta
            for f in web.rglob("index.html"):
                html = f.read_text()
                if 'http-equiv="refresh"' in html:
                    continue
                rel = f.relative_to(web)
                self.assertEqual(len(re.findall(r"<h1[\s>]", html)), 1, f"{clave} {rel}: un solo H1")
                self.assertRegex(html, r"<title>[^<]+</title>", f"{clave} {rel}: título")
                self.assertRegex(html, r'<meta name="description" content="[^"]+"', f"{clave} {rel}: descripción")
                if clave != "gema":  # GEMA todavía no tiene dominio comercial definido: sin canónica hasta definirlo
                    self.assertRegex(html, r'<link rel="canonical" href="https?://', f"{clave} {rel}: canónica")
            self.assertTrue((web / "404.html").exists() and (web / "robots.txt").exists(), clave)


class Comparacion(SimpleTestCase):
    def test_texto_visible_ignora_scripts_estilos_e_iconos(self):
        html = ("<h1>Hola <b>mundo</b></h1><script>var a='<p>no</p>'</script><style>p{}</style>"
                "<p>Uno<br>dos &amp; tres</p><svg><text>icono</text></svg>")
        self.assertEqual(texto_visible(html), ["Hola mundo", "Uno", "dos & tres"])

    def test_detecta_texto_y_paginas_distintas(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            for raiz, texto in ((a, "Precio $100"), (b, "Precio $200")):
                Path(raiz, "lite").mkdir()
                Path(raiz, "index.html").write_text(f"<p>{texto}</p>")
                Path(raiz, "lite", "index.html").write_text("<p>Lite</p>")
            Path(b, "plus").mkdir()
            Path(b, "plus", "index.html").write_text("<p>Plus</p>")
            res = comparar(b, a)
            self.assertEqual(res["texto"], {"": ["-Precio $100", "+Precio $200"]})
            self.assertEqual(res["paginas_nuevas"], ["plus/"])
            self.assertFalse(sin_diferencias(res))
            self.assertTrue(sin_diferencias(comparar(a, a)))
