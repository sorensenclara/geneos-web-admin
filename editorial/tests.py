"""Blog y noticias universal: configuración por sitio, una sola URL por artículo, menú, SEO, tendencias, ideas e IA desactivada.

    python manage.py test editorial
"""
import datetime
import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from contenidos.models import ArticuloPage, AutorBlog, BlogIndexPage, CategoriaBlog, PreguntaFrecuente, Redireccion
from publicacion.exportar import datos_sitio
from publicacion.motor import generar, validar
from sitios.models import LineaProducto, SitioWeb

from . import ia
from .estado import estado_blog
from .ideas import actualizar_ideas, blog_general, crear_borrador, importar_trends, leer_csv_trends
from .models import ConfigBlog, ConsumoIA, IdeaEditorial

VAR = Path(tempfile.mkdtemp(prefix="gwa-test-blog-"))
BLOG = "/admin/blog/"

CSV_CLASICO = """Category: All categories

TOP
siembra de soja,100
cosecha de trigo,64
precio de la hacienda,40

RISING
fertilización de maíz,Breakout
poda de vid,+250%
"""
CSV_ES = "﻿Categoría: Todas las categorías\n\nPRINCIPALES\nmonitoreo de plagas,100\n\nEN AUMENTO\nriego por goteo en viñedos,+120 %\n"


@override_settings(GWA_VAR_DIR=VAR, MEDIA_ROOT=str(VAR / "media"))
class BlogUniversal(TestCase):
    @classmethod
    def setUpTestData(cls):
        with override_settings(GWA_VAR_DIR=VAR):
            call_command("inicializar", "--sin-publicar", stdout=open("/dev/null", "w"))
        cls.geagro = SitioWeb.objects.get(clave="geagro")
        cls.gema = SitioWeb.objects.get(clave="gema")
        cls.gerp = SitioWeb.objects.get(clave="gerp")
        cls.cereales = LineaProducto.objects.get(sitio=cls.geagro, clave="cereales")
        cls.vid = LineaProducto.objects.get(sitio=cls.geagro, clave="vid")
        cls.clara = User.objects.create_superuser("clara", "clara@example.com", "x")
        cls.editor_gema = User.objects.create_user("editor_gema", password="x")
        cls.editor_gema.groups.add(Group.objects.get(name="GEMA · Editor"))

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(VAR, ignore_errors=True)

    # ---------------------------------------------------------------------------------------------- helpers
    def activar(self, sitio, **campos):
        c = ConfigBlog.objects.filter(sitio=sitio).first() or ConfigBlog.nueva(sitio)
        c.activo = True
        for k, v in campos.items():
            setattr(c, k, v)
        c.save()
        c.save_revision(user=self.clara).publish(user=self.clara)
        return c

    def articulo(self, sitio, titulo, lineas=(), publicar=True, **campos):
        padre = blog_general(sitio)
        a = ArticuloPage(title=titulo, slug=titulo.lower().replace(" ", "-"), resumen=f"Resumen de {titulo}", fecha=datetime.date(2026, 10, 1), live=False,
                         cuerpo=[("h2", "Subtítulo"), ("parrafo", "<p>Texto de prueba.</p>")], **campos)
        padre.add_child(instance=a)
        if lineas:
            a.lineas = list(lineas)
            a.save()
        rev = a.save_revision(user=self.clara)
        if publicar:
            rev.publish(user=self.clara)
            a.refresh_from_db()
        return a

    def generar(self, sitio):
        destino = VAR / f"web-{sitio.clave}-{datetime.datetime.now().timestamp()}"
        carpeta, datos, _r = generar(sitio, destino)
        return carpeta, datos

    # ---------------------------------------------------------------------------------------------- Sin aprobación no cambia nada
    def test_existentes_intactos_y_sin_blog_publico(self):
        # Los tres blogs de GEAGRO siguen en borrador y la web no tiene blog ni enlace en el menú
        self.assertEqual(BlogIndexPage.objects.filter(live=True).count(), 0)
        self.assertEqual(BlogIndexPage.objects.count(), 3)
        archivos, _ = datos_sitio(self.geagro)
        self.assertEqual(archivos["geagro.admin.json"]["blog"], {})
        # Activar en borrador (sin aprobar) tampoco publica
        c = ConfigBlog.nueva(self.geagro)
        c.activo = True
        c.save()
        c.save_revision(user=self.clara)
        archivos, _ = datos_sitio(self.geagro)
        self.assertEqual(archivos["geagro.admin.json"]["blog"], {})
        self.assertEqual(estado_blog(self.geagro)[0], "configurado")
        carpeta, _ = self.generar(self.geagro)
        self.assertFalse((carpeta / "blog").exists())
        self.assertNotIn(">Blog<", (carpeta / "index.html").read_text())
        self.assertFalse((carpeta / "assets/css/blog.css").exists())

    # ---------------------------------------------------------------------------------------------- Una sola URL por artículo
    def test_geagro_url_unica_y_listados_por_linea(self):
        self.activar(self.geagro, menu_posicion=5)
        a1 = self.articulo(self.geagro, "Nota cereales", [self.cereales])
        a2 = self.articulo(self.geagro, "Nota vid", [self.vid])
        a3 = self.articulo(self.geagro, "Nota de ambas", [self.cereales, self.vid])
        self.articulo(self.geagro, "Nota sin aprobar", [self.vid], publicar=False)
        self.assertEqual(a1.ruta_publica, "blog/nota-cereales/")
        carpeta, datos = self.generar(self.geagro)
        blog = datos["geagro.admin.json"]["blog"]
        rutas = [b["path"] for b in blog["indexes"]]
        self.assertEqual(rutas, ["blog/", "cereales/blog/", "vid/blog/"])
        por_ruta = {b["path"]: [p["path"] for p in b["posts"]] for b in blog["indexes"]}
        self.assertEqual(len(por_ruta["blog/"]), 3)
        self.assertEqual(set(por_ruta["cereales/blog/"]), {"blog/nota-cereales/", "blog/nota-de-ambas/"})
        self.assertEqual(set(por_ruta["vid/blog/"]), {"blog/nota-vid/", "blog/nota-de-ambas/"})
        # Cada artículo existe una sola vez, bajo /blog/
        self.assertEqual(sorted(p["path"] for p in blog["posts"]), ["blog/nota-cereales/", "blog/nota-de-ambas/", "blog/nota-vid/"])
        self.assertFalse((carpeta / "cereales/blog/nota-cereales").exists())
        self.assertTrue((carpeta / "blog/nota-de-ambas/index.html").exists())
        self.assertNotIn("nota-sin-aprobar", json.dumps(blog))
        self.assertEqual(validar(self.geagro, carpeta, datos), [])
        # Menú: «Blog» en la posición elegida, en todas las páginas (también el menú del celular, que es el mismo)
        for pagina in ("index.html", "cereales/index.html", "blog/nota-vid/index.html"):
            html = (carpeta / pagina).read_text()
            self.assertIn(">Blog</a>", html)
        nav = (carpeta / "index.html").read_text().split('id="menu"')[1].split("</nav>")[0]
        self.assertLess(nav.index(">Planes<"), nav.index(">Blog<"))
        self.assertLess(nav.index(">Blog<"), nav.index(">Preguntas<"))
        # SEO del artículo: canonical propio, og:type article, BlogPosting y sitemap con fecha real
        html = (carpeta / "blog/nota-vid/index.html").read_text()
        self.assertIn('<link rel="canonical" href="https://geagro.ar/blog/nota-vid/">', html)
        self.assertIn('property="og:type" content="article"', html)
        self.assertIn('"@type": "BlogPosting"', html)
        sitemap = (carpeta / "sitemap.xml").read_text()
        self.assertIn("https://geagro.ar/blog/nota-vid/</loc><lastmod>", sitemap)
        self.assertNotIn("nota-cereales/</loc><lastmod>2000", sitemap)
        self.assertIn('<meta name="robots" content="index', (carpeta / "cereales/blog/index.html").read_text())

    def test_no_se_crean_articulos_en_listados_de_linea(self):
        linea_idx = BlogIndexPage.objects.get(linea=self.cereales)
        general = BlogIndexPage.objects.get(linea__isnull=True, ruta_publica="blog/", url_path__startswith="/geagro/")
        self.assertFalse(ArticuloPage.can_create_at(linea_idx))
        self.assertTrue(ArticuloPage.can_create_at(general))

    def test_noticias_ruta_configurable_y_redireccion(self):
        self.activar(self.gema, nombre_menu="Noticias", ruta="noticias", titulo="Noticias de GEMA")
        a = self.articulo(self.gema, "Primera nota")
        self.assertEqual(a.ruta_publica, "noticias/primera-nota/")
        _carpeta, datos = self.generar(self.gema)
        blog = datos["gema.admin.json"]["blog"]
        self.assertEqual(blog["menu"], {"label": "Noticias", "href": "/noticias/", "position": 0})
        self.assertEqual([b["path"] for b in blog["indexes"]], ["noticias/"])
        # Cambiar la dirección de un artículo aprobado deja una redirección 301
        rev = a.get_latest_revision_as_object()
        rev.slug = "primera-nota-nueva"
        rev.save_revision(user=self.clara).publish(user=self.clara)
        r = Redireccion.objects.get(sitio=self.gema, origen="noticias/primera-nota/")
        self.assertEqual(r.destino, "noticias/primera-nota-nueva/")

    def test_paginacion_destacado_y_opciones(self):
        self.activar(self.gerp, articulos_por_pagina=2, mostrar_autor=False, mostrar_relacionados=False)
        autor = AutorBlog.objects.create(sitio=self.gerp, nombre="Ana Prueba")
        for i in range(5):
            self.articulo(self.gerp, f"Nota {i}", autor=autor)
        archivos, _ = datos_sitio(self.gerp)
        blog = archivos["gerp.admin.json"]["blog"]
        self.assertEqual([b["path"] for b in blog["indexes"]], ["blog/", "blog/pagina/2/", "blog/pagina/3/"])
        self.assertIsNone(blog["indexes"][0]["robots"])
        self.assertIsNone(blog["indexes"][1]["robots"])  # la paginación se indexa, con canonical propio
        self.assertEqual([b["sitemap"] for b in blog["indexes"]], [True, False, False])  # pero no va al sitemap
        self.assertTrue(blog["indexes"][0]["featured"])
        self.assertFalse(blog["indexes"][1]["featured"])
        self.assertEqual(len(blog["indexes"][0]["index"]), 5)  # el buscador abarca todas las páginas
        self.assertEqual(blog["posts"][0]["author"], "")  # autor oculto por configuración
        self.assertEqual(blog["posts"][0]["related"], [])
        self.assertEqual(blog["posts"][0]["schema"]["author"]["@type"], "Organization")

    def test_vista_previa_de_articulo_con_blog_inactivo(self):
        a = self.articulo(self.gema, "Borrador para ver", publicar=False)
        archivos, _ = datos_sitio(self.gema, overrides=[a.get_latest_revision_as_object()])
        self.assertEqual([p["path"] for p in archivos["gema.admin.json"]["blog"]["posts"]], ["blog/borrador-para-ver/"])
        # …pero la web real no lo tiene
        self.assertEqual(datos_sitio(self.gema)[0]["gema.admin.json"]["blog"], {})

    def test_geneos_noticias_con_su_propio_diseno(self):
        from django.conf import settings
        if not (Path(settings.GENEOS_WEB_DIR) / "build.py").exists():
            self.skipTest("GENEOS WEB no está disponible")
        geneos = SitioWeb.objects.get(clave="geneos")
        c = self.activar(geneos, menu_posicion=4)
        self.assertEqual((c.nombre_menu, c.ruta), ("Noticias", "noticias"))
        self.articulo(geneos, "Primera noticia")
        carpeta, datos = self.generar(geneos)
        self.assertEqual(carpeta.name, "geneos-web")
        self.assertEqual(validar(geneos, carpeta, datos), [])
        html = (carpeta / "index.html").read_text()
        menu = html.split('id="menu"')[1].split("</nav>")[0]
        self.assertLess(menu.index(">Recursos<"), menu.index(">Noticias<"))
        self.assertLess(menu.index(">Noticias<"), menu.index(">Contacto<"))
        nota = (carpeta / "noticias/primera-noticia/index.html").read_text()
        self.assertIn('property="og:type" content="article"', nota)
        self.assertIn('class="site-header head-claro"', nota)  # encabezado y pie de la web de GENEOS (claro: predeterminado)
        self.assertIn("/noticias/primera-noticia/</loc>", (carpeta / "sitemap.xml").read_text())

    def test_geneos_apariencia_del_encabezado(self):
        """La apariencia elegida en Sitios y contacto se aplica a todas las páginas; una página puede usar otra."""
        from contenidos.models import PaginaWeb
        from sitios.models import SitioWeb
        geneos = SitioWeb.objects.get(clave="geneos")
        self.assertEqual(geneos.encabezado, "claro")
        carpeta, _ = self.generar(geneos)
        self.assertIn('class="site-header head-claro"', (carpeta / "index.html").read_text())
        geneos.encabezado = "oscuro"
        geneos.save()
        raiz = geneos.site.root_page.specific
        pagina = PaginaWeb(title="Staff Augmentation", slug="staff-prueba-encabezado", ruta_publica="staff-augmentation/", encabezado="claro")
        raiz.add_child(instance=pagina)
        pagina.save_revision().publish()
        carpeta, datos = self.generar(geneos)
        self.assertIn('class="site-header head-oscuro"', (carpeta / "index.html").read_text())
        self.assertIn('class="site-header head-claro"', (carpeta / "staff-augmentation/index.html").read_text())
        # El campo solo aparece en las páginas de GENEOS
        Form = PaginaWeb.get_edit_handler().get_form_class()
        self.assertIn("encabezado", Form(instance=pagina, parent_page=raiz, for_user=self.admin if hasattr(self, "admin") else None).fields)
        otra = PaginaWeb.objects.exclude(pk=pagina.pk).exclude(path__startswith=raiz.path).first()
        if otra is not None:
            self.assertNotIn("encabezado", Form(instance=otra, parent_page=otra.get_parent(), for_user=None).fields)

    # ---------------------------------------------------------------------------------------------- Pantalla Blog y noticias
    def test_pantalla_selector_y_estado_vacio(self):
        self.client.force_login(self.clara)
        html = self.client.get(BLOG + "?sitio=geagro").content.decode()
        for clave in ("geneos", "gerp", "geagro", "gema"):
            self.assertIn(f"gwa/marca/{clave}-isologo", html)
        self.assertIn("Blog de GEAGRO", html)
        self.assertIn("Actualidad e ideas para publicar", html)
        self.assertIn("todavía no tiene artículos", html)
        self.assertIn('aria-current="page">Todas</a>', html)  # filtro por línea de GEAGRO
        self.assertEqual(self.client.session["gwa_blog_sitio"], "geagro")
        # La elección se mantiene al volver sin parámetro
        self.assertIn("Blog de GEAGRO", self.client.get(BLOG).content.decode())
        html = self.client.get(BLOG + "?sitio=gema").content.decode()
        self.assertNotIn("Cereales</a>", html)

    def test_nuevo_articulo_usa_sitio_y_linea(self):
        self.client.force_login(self.clara)
        r = self.client.post(f"{BLOG}gema/nuevo/")
        padre = blog_general(self.gema, crear=False)
        self.assertIsNotNone(padre)
        self.assertFalse(padre.live)  # el blog nuevo queda en borrador
        self.assertEqual(r["Location"], f"/admin/pages/add/contenidos/articulopage/{padre.pk}/")
        r = self.client.post(f"{BLOG}geagro/nuevo/", {"linea": str(self.vid.pk)})
        html = self.client.get(r["Location"]).content.decode()
        self.assertRegex(html, rf'value="{self.vid.pk}"[^>]*checked|checked[^>]*value="{self.vid.pk}"')
        for pestaña in ("Artículo", "Organización", "SEO", "Publicación", "Así podría verse en Google"):
            self.assertIn(pestaña, html)

    def test_permisos_por_sitio(self):
        self.client.force_login(self.editor_gema)
        html = self.client.get(BLOG + "?sitio=geagro").content.decode()
        self.assertIn("Blog de GEMA", html)  # no puede elegir GEAGRO: queda en su sitio
        self.assertNotIn("gwa/marca/geagro-isologo", html)
        # Wagtail responde a un permiso denegado volviendo al inicio del administrador, sin hacer nada
        n = IdeaEditorial.objects.count()
        for r in (self.client.post(f"{BLOG}geagro/nuevo/"), self.client.post(f"{BLOG}geagro/actualizar/"), self.client.get(f"{BLOG}geagro/configurar/")):
            self.assertIn(r.status_code, (302, 403))
            if r.status_code == 302:
                self.assertEqual(r["Location"], "/admin/")
        self.assertEqual(IdeaEditorial.objects.count(), n)
        self.assertFalse(ConfigBlog.objects.filter(sitio=self.geagro).exists())

    def test_configurar_crea_borrador_desactivado(self):
        self.client.force_login(self.clara)
        r = self.client.post(f"{BLOG}gerp/configurar/")
        c = ConfigBlog.objects.get(sitio=self.gerp)
        self.assertEqual(r["Location"], f"/admin/snippets/editorial/configblog/edit/{c.pk}/")
        self.assertFalse(c.live)
        self.assertFalse(c.activo)
        self.assertEqual(self.client.get(r["Location"]).status_code, 200)

    # ---------------------------------------------------------------------------------------------- Tendencias e ideas
    def test_csv_de_trends(self):
        self.assertEqual(leer_csv_trends(CSV_CLASICO)[3], ("fertilización de maíz", "en_aumento", "Breakout"))
        self.assertEqual(leer_csv_trends(CSV_ES), [("monitoreo de plagas", "principal", "100"), ("riego por goteo en viñedos", "en_aumento", "+120 %")])
        ConfigBlog.nueva(self.geagro).save()  # excluye ganadería y hacienda
        imp, creadas, descartadas = importar_trends(self.geagro, CSV_CLASICO, datetime.date(2026, 10, 14), self.clara, termino="cultivos")
        self.assertEqual((creadas, descartadas), (4, 1))
        idea = IdeaEditorial.objects.get(sitio=self.geagro, titulo="poda de vid")
        self.assertEqual((idea.tipo, idea.dato, idea.consultado), ("tendencia", "+250%", datetime.date(2026, 10, 14)))
        self.assertIn("trends.google.com", idea.fuente_url)
        self.assertEqual(IdeaEditorial.objects.get(titulo="fertilización de maíz").dato, "Aumento puntual")
        # Desde la pantalla
        self.client.force_login(self.clara)
        r = self.client.post(f"{BLOG}geagro/importar/", {"archivo": SimpleUploadedFile("t.csv", CSV_ES.encode()), "consultado": "2026-10-13",
                                                          "linea": str(self.vid.pk), "region": "Argentina"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(IdeaEditorial.objects.get(titulo="riego por goteo en viñedos").linea, self.vid)
        html = self.client.get(BLOG + "?sitio=geagro").content.decode()
        self.assertIn("Tendencia de búsqueda", html)
        self.assertIn("Actualidad e ideas para publicar", html)

    def test_ideas_editoriales_sin_repetir(self):
        n = actualizar_ideas(self.gema)
        self.assertGreater(n, 0)
        tipos = set(IdeaEditorial.objects.filter(sitio=self.gema).values_list("tipo", flat=True))
        self.assertEqual(tipos, {"idea"})  # sin datos externos: ninguna se presenta como tendencia
        titulos = list(IdeaEditorial.objects.filter(sitio=self.gema).values_list("titulo", flat=True))
        self.assertFalse(any("probar" in t.lower() or "pago" in t.lower() for t in titulos))  # preguntas comerciales fuera
        idea = IdeaEditorial.objects.filter(sitio=self.gema).first()
        idea.estado = "descartada"
        idea.save()
        actualizar_ideas(self.gema)
        self.assertEqual(IdeaEditorial.objects.filter(sitio=self.gema, clave=idea.clave).count(), 1)

    def test_crear_borrador_desde_idea(self):
        importar_trends(self.geagro, CSV_CLASICO, datetime.date(2026, 10, 14), self.clara, linea=self.cereales)
        idea = IdeaEditorial.objects.get(titulo="siembra de soja")
        self.client.force_login(self.clara)
        r = self.client.post(f"{BLOG}idea/{idea.pk}/borrador/")
        a = ArticuloPage.objects.get(title="Qué hay que saber sobre siembra de soja")
        self.assertEqual(r["Location"], f"/admin/pages/{a.pk}/edit/")
        self.assertFalse(a.live)  # nunca se publica sola
        v = a.get_latest_revision_as_object()
        self.assertEqual([l.pk for l in v.lineas.all()], [self.cereales.pk])
        tipos = [b.block_type for b in v.cuerpo]
        self.assertEqual([t for t in tipos if t != "parrafo"], ["h2", "h2", "h2", "h3", "h3", "h2"])
        self.assertIn("[Completar", v.cuerpo[1].value.source)  # consignas para el redactor
        self.assertIn("Google Trends (archivo exportado)", v.fuentes)
        self.assertEqual(v.origen, "tendencia")
        self.assertEqual(v.palabras_clave, "siembra de soja")
        idea.refresh_from_db()
        self.assertEqual((idea.estado, idea.articulo_id), ("usada", a.pk))

    def test_actualidad_tipos_periodo_y_borrador_desde_noticia(self):
        hoy = datetime.date.today()
        def nueva(**kw):
            base = dict(sitio=self.geagro, fuente="Medio de prueba", consultado=hoy, fuente_tipo="medio", tipo="noticia")
            base.update(kw)
            return IdeaEditorial.objects.create(**base)
        reciente = nueva(titulo="Avanza la siembra de maíz", publicado=hoy - datetime.timedelta(days=2), fuente_url="https://ejemplo.com/nota",
                         resumen="Resumen propio.", descripcion="Relacionado con la planificación de campaña.", propuesta="Cómo planificar la siembra de maíz",
                         linea=self.cereales)
        vieja = nueva(titulo="Nota de hace un mes", publicado=hoy - datetime.timedelta(days=20))
        nueva(titulo="Feria que ya pasó", tipo="evento", fuente_tipo="evento", publicado=hoy - datetime.timedelta(days=3), evento_fecha=hoy - datetime.timedelta(days=1))
        idea = nueva(titulo="Tema propio", tipo="idea", fuente_tipo="interno", publicado=None, consultado=hoy - datetime.timedelta(days=60))
        self.client.force_login(self.clara)
        html = self.client.get(BLOG + "?sitio=geagro").content.decode()
        self.assertIn("Avanza la siembra de maíz", html)
        self.assertIn("Tema propio", html)  # las ideas editoriales no vencen
        self.assertNotIn("Nota de hace un mes", html)  # fuera de los últimos 7 días
        self.assertNotIn("Feria que ya pasó", html)
        html30 = self.client.get(BLOG + "?sitio=geagro&periodo=30").content.decode()
        self.assertIn("Nota de hace un mes", html30)
        solo_ideas = self.client.get(BLOG + "?sitio=geagro&contenido=idea").content.decode()
        self.assertNotIn("Avanza la siembra de maíz", solo_ideas)
        todas = self.client.get(f"{BLOG}geagro/actualidad/?periodo=30").content.decode()
        self.assertIn("Nota de hace un mes", todas)
        # Descartar vuelve a la página de origen
        r = self.client.post(f"{BLOG}idea/{vieja.pk}/descartar/", {"next": f"{BLOG}geagro/actualidad/?periodo=30"})
        self.assertEqual(r["Location"], f"{BLOG}geagro/actualidad/?periodo=30")
        self.assertNotIn("Nota de hace un mes", self.client.get(f"{BLOG}geagro/actualidad/?periodo=30").content.decode())
        # Borrador desde una noticia: título propuesto, línea, fuente enlazada al final; sin copiar el texto de la nota
        r = self.client.post(f"{BLOG}idea/{reciente.pk}/borrador/")
        a = ArticuloPage.objects.get(title="Cómo planificar la siembra de maíz")
        v = a.get_latest_revision_as_object()
        self.assertFalse(a.live)
        self.assertEqual([l.pk for l in v.lineas.all()], [self.cereales.pk])
        tipos = [b.block_type for b in v.cuerpo]
        self.assertEqual(tipos[-2:], ["h3", "parrafo"])
        self.assertIn('href="https://ejemplo.com/nota"', v.cuerpo[-1].value.source)
        self.assertIn("https://ejemplo.com/nota", v.fuentes)
        self.assertEqual(v.origen, "noticia")
        self.assertNotIn("Avanza la siembra", " ".join(b.value for b in v.cuerpo if b.block_type in ("h2", "h3")))  # no repite el titular
        # Un borrador con consignas sin completar no puede salir a la web
        self.activar(self.geagro)
        v.save_revision(user=self.clara).publish(user=self.clara)
        carpeta, datos = self.generar(self.geagro)
        self.assertTrue(any("[Completar" in e for e in validar(self.geagro, carpeta, datos)))
        idea.refresh_from_db()
        self.assertEqual(idea.estado, "sugerida")

    # ---------------------------------------------------------------------------------------------- IA
    def test_ia_desactivada_por_defecto(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for k in ("GWA_IA_PROVEEDOR", "GWA_IA_MODELO", "GWA_IA_LIMITE_USD", "ANTHROPIC_API_KEY"):
                os.environ.pop(k, None)
            self.assertFalse(ia.estado()["activa"])
            with self.assertRaises(ia.IADesactivada):
                ia.sugerir_ideas(self.gema, enviar=lambda c: self.fail("no debe llamar"))

    def test_ia_con_limite_y_validacion(self):
        env = {"GWA_IA_PROVEEDOR": "anthropic", "GWA_IA_MODELO": "claude-sonnet-prueba", "GWA_IA_LIMITE_USD": "1", "ANTHROPIC_API_KEY": "x"}
        respuesta = {"usage": {"input_tokens": 1000, "output_tokens": 500}, "content": [{"type": "text", "text": json.dumps([
            {"titulo": "Cómo organizar los vencimientos del taller", "motivo": "Tema frecuente", "palabras_clave": "vencimientos"},
            {"titulo": "El 80% de los talleres usa planillas", "motivo": "dato inventado"}])}]}
        with mock.patch.dict(os.environ, env):
            ideas = ia.sugerir_ideas(self.gema, enviar=lambda c: respuesta)
            self.assertEqual([i.titulo for i in ideas], ["Cómo organizar los vencimientos del taller"])  # la cifra se descarta
            self.assertEqual((ideas[0].tipo, ideas[0].generada_ia), ("idea", True))
            consumo = ConsumoIA.objects.get()
            self.assertEqual((consumo.tokens_entrada, consumo.tokens_salida), (1000, 500))
            ConsumoIA.objects.create(proveedor="anthropic", modelo="x", tarea="x", costo_usd=1)
            with self.assertRaises(ia.LimiteAlcanzado):
                ia.sugerir_ideas(self.gema, enviar=lambda c: self.fail("no debe llamar"))


class GeneosGeneradorComun(TestCase):
    """GENEOS pasa por el generador común sin cambiar nada de su web: build.py de GENEOS WEB se ejecuta tal cual."""

    def test_salida_identica_a_build_py(self):
        import filecmp
        import subprocess
        import sys
        from django.conf import settings
        origen = Path(settings.GENEOS_WEB_DIR)
        if not (origen / "build.py").exists():
            self.skipTest("GENEOS WEB no está disponible")
        tmp = Path(tempfile.mkdtemp(prefix="gwa-geneos-"))
        try:
            copia = tmp / "GW"
            shutil.copytree(origen, copia, ignore=shutil.ignore_patterns("public", "__pycache__"))
            subprocess.run([sys.executable, "build.py"], cwd=copia, capture_output=True, check=True)
            env = dict(os.environ, GENEOS_WEB_DIR=str(copia))
            env.pop("WEB_DATA_DIR", None)
            subprocess.run([sys.executable, str(Path(settings.GWA_RENDERER_DIR) / "export_geneos.py"), "--out", str(tmp / "B")],
                           env=env, capture_output=True, check=True)

            def iguales(a, b):
                c = filecmp.dircmp(a, b)
                if c.left_only or c.right_only or c.diff_files or c.funny_files:
                    return False
                _ok, mal, raros = filecmp.cmpfiles(a, b, c.common_files, shallow=False)
                return not mal and not raros and all(iguales(Path(a) / d, Path(b) / d) for d in c.common_dirs)
            self.assertTrue(iguales(copia / "public", tmp / "B" / "geneos-web"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
