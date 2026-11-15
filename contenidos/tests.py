"""Web institucional de GENEOS: contenido por sección (piloto: home).

Comprueba que sin datos la web no cambia, que lo importado como borrador no se publica, que publicar lo importado da la
misma web, que los cambios de Wagtail se reflejan campo por campo y que los campos vacíos conservan el texto original.
"""
import datetime
import filecmp
import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings

from contenidos.models import LogoCliente, PaginaWeb
from publicacion.motor import generar
from sitios.models import SitioWeb

VAR = Path(tempfile.mkdtemp(prefix="gwa-test-geneos-"))
ORIGEN = Path(settings.GENEOS_WEB_DIR)


def iguales(a, b):
    c = filecmp.dircmp(a, b)
    if c.left_only or c.right_only or c.diff_files or c.funny_files:
        return False
    _ok, mal, raros = filecmp.cmpfiles(a, b, c.common_files, shallow=False)
    return not mal and not raros and all(iguales(Path(a) / d, Path(b) / d) for d in c.common_dirs)


@override_settings(GWA_VAR_DIR=VAR, MEDIA_ROOT=str(VAR / "media"), GENEOS_WEB_DIR=VAR / "GW")
class HomeAdministrable(TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ORIGEN / "build.py").exists() or "def seccion(" not in (ORIGEN / "build.py").read_text():
            raise __import__("unittest").SkipTest("GENEOS WEB con secciones administrables no está disponible")
        # Copia de GENEOS WEB con su build.py de referencia (la web tal como la genera hoy, sin administrador)
        cls.gw = VAR / "GW"
        shutil.copytree(ORIGEN, cls.gw, ignore=shutil.ignore_patterns("public", "__pycache__"), dirs_exist_ok=True)
        subprocess.run([sys.executable, "build.py"], cwd=cls.gw, capture_output=True, check=True)
        cls.referencia = cls.gw / "public"
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(VAR, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        with override_settings(GWA_VAR_DIR=VAR):
            call_command("inicializar", "--sin-publicar", stdout=io.StringIO())
        cls.geneos = SitioWeb.objects.get(clave="geneos")
        cls.clara = User.objects.create_superuser("clara", "clara@example.com", "x")

    def home(self):
        return PaginaWeb.objects.get(pk=next(p.pk for p in PaginaWeb.objects.filter(ruta_publica="")
                                              if p.get_parent().specific_class is not PaginaWeb and p.url_path.count("/") <= 3
                                              and "geneos" in (p.get_site().sitio_web.clave if p.get_site() else "")))

    def importar(self):
        out = io.StringIO()
        call_command("importar_contenido_geneos", "--guardar", stdout=out)
        return out.getvalue()

    def web(self):
        destino = VAR / f"web-{datetime.datetime.now().timestamp()}"
        carpeta, _datos, _r = generar(self.geneos, destino)
        return carpeta

    def publicar_cambios(self, **cambios):
        p = self.home().get_latest_revision_as_object()
        secciones = cambios.pop("secciones", None)
        for k, v in cambios.items():
            setattr(p, k, v)
        if secciones:
            raw = p.secciones.get_prep_value()
            for b in raw:
                secciones(b["value"])
            p.secciones = raw
        p.save_revision(user=self.clara).publish(user=self.clara)

    # ------------------------------------------------------------------------------------------ sin datos, sin cambios
    def test_sin_datos_e_importado_en_borrador_la_web_es_identica(self):
        self.assertTrue(iguales(self.referencia, self.web()), "sin datos administrados la web debe ser idéntica a build.py")
        salida = self.importar()
        self.assertIn("Guardado como borrador", salida)
        self.assertFalse(self.home().hero_titulo)  # lo publicado sigue vacío
        self.assertEqual(LogoCliente.objects.filter(live=True).count(), 0)
        self.assertEqual(LogoCliente.objects.filter(estado="pendiente").count(), 22)
        self.assertTrue(iguales(self.referencia, self.web()), "los borradores no cambian la web")
        # Publicar lo importado tal cual da la misma web (12 páginas, imágenes, enlaces, SEO y apariencia)
        self.home().get_latest_revision().publish(user=self.clara)
        self.assertEqual(self.home().hero_titulo, "Soluciones que hacen crecer tu organización")
        self.assertTrue(iguales(self.referencia, self.web()), "publicar los textos importados no cambia la web")

    def test_importar_no_pisa_lo_cargado(self):
        p = self.home().get_latest_revision_as_object()
        p.hero_titulo = "Título ya cargado"
        p.save_revision(user=self.clara)
        salida = self.importar()
        self.assertIn("Se conserva lo cargado en Wagtail: hero_titulo", salida)
        self.assertEqual(self.home().get_latest_revision_as_object().hero_titulo, "Título ya cargado")
        segunda = io.StringIO()
        call_command("importar_contenido_geneos", "--guardar", stdout=segunda)
        self.assertIn("0 para cargar", segunda.getvalue())  # los logos no se duplican
        self.assertEqual(LogoCliente.objects.count(), 22)

    # ------------------------------------------------------------------------------------------ cambios desde Wagtail
    def test_titulo_bajada_boton_y_tarjeta(self):
        self.importar()

        def secciones(v):
            if v["clave"] == "soluciones":
                v["bajada"] = "Sistemas **propios** para cada sector."
                for t in [x.get("value", x) for x in v["items"]]:
                    if t["clave"] == "gema":
                        t["texto"] = "Texto nuevo de GEMA."
                    if t["clave"] == "gerp":
                        t["titulo"], t["texto"] = "", ""  # vacíos: conservan
            if v["clave"] == "software-libre":
                v["titulo"] = ""  # vacío: conserva
        self.publicar_cambios(hero_titulo="Software libre que hace crecer tu organización", hero_bajada="",
                              boton1_texto="Ver productos", boton1_enlace="", secciones=secciones)
        carpeta = self.web()
        html = (carpeta / "index.html").read_text()
        ref = (self.referencia / "index.html").read_text()
        self.assertIn('<span class="hx-h1-main">Software libre que hace crecer tu organización</span>', html)
        self.assertIn("Desarrollamos productos propios y soluciones a medida", html)  # bajada vacía: se conserva
        self.assertIn('<a class="btn btn-solid" href="#soluciones">Ver productos', html)  # enlace vacío: se conserva
        self.assertIn('<p class="hx-sub">Sistemas <strong>propios</strong> para cada sector.</p>', html)
        self.assertIn("<p>Texto nuevo de GEMA.</p>", html)
        self.assertIn("<h3>GERP</h3>", html)
        self.assertIn("Sistema integral de gestión empresarial basado en Odoo", html)
        self.assertIn("Software libre para un futuro más tuyo", html)
        # Fuera de lo editado, la home y las otras 11 páginas no cambian
        self.assertEqual(len(html.splitlines()), len(ref.splitlines()))
        distintas = [a for a, b in zip(html.splitlines(), ref.splitlines()) if a != b]
        self.assertEqual(len(distintas), 4)
        for f in self.referencia.rglob("index.html"):
            if f.parent != self.referencia:
                self.assertEqual(f.read_text(), (carpeta / f.relative_to(self.referencia)).read_text(), f)

    def test_textos_se_escapan(self):
        self.importar()
        self.publicar_cambios(hero_titulo="<script>alert(1)</script>", hero_bajada="a <b>b</b>")
        html = (self.web() / "index.html").read_text()
        self.assertNotIn("<script>alert(1)", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("a &lt;b&gt;b&lt;/b&gt;", html)

    def test_orden_y_secciones_ocultas(self):
        self.importar()
        p = self.home().get_latest_revision_as_object()
        raw = p.secciones.get_prep_value()
        pos = {b["value"]["clave"]: i for i, b in enumerate(raw)}
        raw[pos["soluciones"]], raw[pos["cooperativas"]] = raw[pos["cooperativas"]], raw[pos["soluciones"]]
        p.secciones = raw
        p.secciones_ocultas = ["clientes", "software-libre"]
        p.save_revision(user=self.clara).publish(user=self.clara)
        html = (self.web() / "index.html").read_text()
        self.assertLess(html.index('class="section theme-white coop"'), html.index('class="section theme-gray-light hx-products"'))
        self.assertNotIn("hx-free", html)
        self.assertNotIn("hx-clients-head", html)
        self.assertIn('id="contacto"', html)
        self.assertLess(html.index("hx-products"), html.index('id="contacto"'))  # contacto siempre al final

    def test_formulario_valida_secciones(self):
        home = self.home()
        Form = PaginaWeb.get_edit_handler().get_form_class()
        form = Form(instance=home, parent_page=home.get_parent(), for_user=self.clara)
        self.assertIn("secciones", form.fields)
        opciones = [c for c, _n in form.fields["secciones_ocultas_sel"].choices]
        self.assertIn("software-libre", opciones)
        self.assertNotIn("contacto", opciones)  # destino de los botones: no se oculta
        self.assertNotIn("comparar", opciones)  # opciones de GERP: no aplican a la home de GENEOS
        gerp = PaginaWeb.objects.filter(ruta_publica="").exclude(pk=home.pk).first()
        if gerp is not None:
            otro = Form(instance=gerp, parent_page=gerp.get_parent(), for_user=self.clara)
            for campo in ("secciones", "hero_destacados", "hero_antetitulo"):
                self.assertNotIn(campo, otro.fields)

    # ------------------------------------------------------------------------------------------ logos de clientes
    def test_logos_actuales_se_conservan_y_los_nuevos_requieren_autorizacion(self):
        self.importar()
        actual = LogoCliente.objects.get(archivo_web="2024/03/CIEP.png")
        actual.estado, actual.autorizado_por, actual.autorizado_el = "autorizado", "Clara", datetime.date(2026, 10, 27)
        actual.save_revision(user=self.clara).publish(user=self.clara)
        nuevo = LogoCliente(sitio=self.geneos, organizacion="Organización Nueva", imagen=actual.imagen, paginas=[""], orden=99)
        nuevo.save()
        nuevo.save_revision(user=self.clara).publish(user=self.clara)
        carpeta = self.web()
        self.assertTrue(iguales(self.referencia, carpeta), "autorizar un logo que ya está o publicar uno pendiente no cambia la web")
        nuevo.estado, nuevo.autorizado_por, nuevo.autorizado_el = "autorizado", "Clara", datetime.date(2026, 10, 27)
        nuevo.save_revision(user=self.clara).publish(user=self.clara)
        carpeta = self.web()
        html = (carpeta / "index.html").read_text()
        self.assertIn('src="/assets/img/admin/logos/organizacion-nueva.webp" alt="Logo de Organización Nueva"', html)
        self.assertTrue((carpeta / "assets/img/admin/logos/organizacion-nueva.webp").exists())
        self.assertEqual(html.count('<li><img src="/assets/img/2024/'), (self.referencia / "index.html").read_text().count('<li><img src="/assets/img/2024/'))
