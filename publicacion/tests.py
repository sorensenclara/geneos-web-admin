"""Pruebas del circuito completo: permisos por sitio y línea, precios, publicación (bien y con error), vuelta atrás y formulario.

    python manage.py test
"""
import json
import shutil
import tempfile
import time
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.core import mail, signing
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from contenidos.models import Plan, PreguntaFrecuente
from formularios.models import SolicitudDemo
from formularios.views import SAL
from publicacion import despliegue
from publicacion.servicio import estado_sitio, publicar_sitio, volver_atras
from sitios.models import LineaProducto, SitioWeb
from sitios.permisos import SitioPermissionPolicy, puede

VAR = Path(tempfile.mkdtemp(prefix="gwa-test-"))


@override_settings(GWA_VAR_DIR=VAR, GWA_FORM_SEGUNDOS_MINIMOS=0, MEDIA_ROOT=str(VAR / "media"))
class Circuito(TestCase):
    @classmethod
    def setUpTestData(cls):
        with override_settings(GWA_VAR_DIR=VAR):
            call_command("inicializar", "--sin-publicar", stdout=open("/dev/null", "w"))
        cls.gerp = SitioWeb.objects.get(clave="gerp")
        cls.gema = SitioWeb.objects.get(clave="gema")
        cls.geagro = SitioWeb.objects.get(clave="geagro")

        def usuario(nombre, grupo):
            u = User.objects.create_user(nombre, password="x")
            u.groups.add(Group.objects.get(name=grupo))
            return u
        cls.editor_gema = usuario("editor_gema", "GEMA · Editor")
        cls.pub_gerp = usuario("pub_gerp", "GERP · Publicador")
        cls.ed_cereales = usuario("ed_cereales", "GEAGRO Cereales · Editor")
        cls.clara = User.objects.create_superuser("clara", "clara@example.com", "x")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(VAR, ignore_errors=True)

    # ---------------------------------------------------------------------------------------------- Interfaz (GENEOS UI)
    def test_esqueleto_sidebar_topbar_y_logos(self):
        self.client.force_login(self.clara)
        html = self.client.get("/admin/precios/").content.decode()
        self.assertIn('id="gu-sidebar"', html)
        self.assertIn('id="gu-menu-btn"', html)  # hamburguesa en el topbar, fuera del sidebar
        self.assertLess(html.index('id="gu-sidebar"'), html.index('class="gu-topbar"'))
        self.assertNotIn("data-wagtail-sidebar", html)  # el sidebar de Wagtail se reemplaza
        self.assertIn("gwa/marca/geneos-isologotipo-blanco.svg", html)
        self.assertIn("gwa/marca/geneos-isologo-color.svg", html)
        self.assertIn('action="/admin/logout/"', html)
        self.assertIn('href="/admin/account/"', html)
        self.assertIn('aria-current="page"', html)
        for clave in ("gerp", "geagro", "gema"):
            self.assertIn(f"gwa/marca/{clave}-isologo.svg", html)
        self.assertNotIn("Notificaciones", html)

    def test_colores_e_isologos_oficiales(self):
        from django.conf import settings
        esperados = {"gerp": "#1b4b8c", "geagro": "#0e8337", "gema": "#ec6c05"}
        for clave, color in esperados.items():
            s = SitioWeb.objects.get(clave=clave)
            self.assertEqual(s.marca["color"], color)
            original = (settings.BASE_DIR / "docs/marca/favicon-originales" / f"{clave.upper()}-favicon.svg").read_bytes()
            self.assertEqual((settings.BASE_DIR / "static/gwa/marca" / f"{clave}-isologo.svg").read_bytes(), original)

    def test_menu_respeta_permisos(self):
        self.client.force_login(self.editor_gema)
        html = self.client.get("/admin/").content.decode()
        self.assertIn("Actualizar precios", html)
        self.assertNotIn("Accesos por sitio", html)
        self.assertNotIn(">Usuarios<", html)

    def test_buscador_respeta_permisos(self):
        self.client.force_login(self.editor_gema)
        datos = self.client.get("/admin/buscar/?q=ge&formato=json").json()
        titulos = [it["titulo"] for g in datos["grupos"] for it in g["items"]]
        self.assertTrue(any("GEMA" in t for t in titulos))
        self.assertFalse(any(t.startswith(("GERP", "GEAGRO")) for t in titulos))
        self.client.force_login(self.clara)
        datos = self.client.get("/admin/buscar/?q=precios&formato=json").json()
        secciones = [it["titulo"] for g in datos["grupos"] if g["titulo"] == "Secciones" for it in g["items"]]
        self.assertIn("Actualizar precios", secciones)
        self.assertEqual(self.client.get("/admin/buscar/?q=plan").status_code, 200)

    def test_iconos_lineales(self):
        from wagtail.admin.icons import get_icons
        sprite = get_icons()
        self.assertIn('id="icon-tag"', sprite)
        self.assertIn("M12.586 2.586", sprite)  # trazo de Lucide «tag»
        # Todos los íconos son lineales: cada símbolo lleva el trazo de Lucide y ninguno es relleno
        self.assertEqual(sprite.count("<symbol"), sprite.count('stroke-width="1.8"'))
        self.assertIn('id="icon-megaphone"', sprite)

    # ---------------------------------------------------------------------------------------------- Permisos
    def test_roles_por_sitio(self):
        self.assertTrue(puede(self.editor_gema, self.gema.pk))
        self.assertFalse(puede(self.editor_gema, self.gerp.pk))
        self.assertFalse(puede(self.editor_gema, self.gema.pk, nivel=2))  # editor no aprueba
        self.assertTrue(puede(self.pub_gerp, self.gerp.pk, nivel=2))
        self.assertTrue(puede(self.clara, self.gerp.pk, nivel=3))

    def test_planes_visibles_solo_de_su_sitio(self):
        pol = SitioPermissionPolicy(Plan)
        planes = pol.instances_user_has_any_permission_for(self.editor_gema, ["change"])
        self.assertEqual({p.sitio.clave for p in planes}, {"gema"})
        plan_gerp = Plan.objects.filter(sitio=self.gerp).first()
        self.assertFalse(pol.user_has_permission_for_instance(self.editor_gema, "change", plan_gerp))
        self.assertFalse(pol.user_has_permission_for_instance(self.pub_gerp, "delete", plan_gerp))

    def test_linea_de_geagro(self):
        cereales = LineaProducto.objects.get(clave="cereales")
        vid = LineaProducto.objects.get(clave="vid")
        self.assertTrue(puede(self.ed_cereales, self.geagro.pk, cereales.pk))
        self.assertFalse(puede(self.ed_cereales, self.geagro.pk, vid.pk))
        pol = SitioPermissionPolicy(PreguntaFrecuente)
        faq_vid = PreguntaFrecuente.objects.filter(linea=vid).first()
        faq_cer = PreguntaFrecuente.objects.filter(linea=cereales).first()
        self.assertTrue(pol.user_has_permission_for_instance(self.ed_cereales, "change", faq_cer))
        self.assertFalse(pol.user_has_permission_for_instance(self.ed_cereales, "change", faq_vid))

    def test_pantallas_de_otro_sitio_bloqueadas(self):
        self.client.force_login(self.editor_gema)
        # Wagtail responde a «sin permiso» volviendo al inicio del panel con un aviso
        self.assertEqual(self.client.get("/admin/web/gerp/").status_code, 302)
        self.assertEqual(self.client.post("/admin/web/gema/publicar/").status_code, 302)  # editor no publica
        self.assertFalse(self.gema.despliegues.exists())
        plan_gerp = Plan.objects.filter(sitio=self.gerp).first()
        for url in (f"/admin/snippets/contenidos/plan/edit/{plan_gerp.pk}/", f"/admin/snippets/contenidos/plan/history/{plan_gerp.pk}/",
                    f"/admin/snippets/contenidos/plan/delete/{plan_gerp.pk}/", f"/admin/snippets/sitios/sitioweb/edit/{self.gerp.pk}/"):
            self.assertEqual(self.client.get(url).status_code, 302, url)
        # No puede crear contenido en otro sitio aunque arme el formulario a mano
        n = PreguntaFrecuente.objects.count()
        r = self.client.post("/admin/snippets/contenidos/preguntafrecuente/add/", {"sitio": self.gerp.pk, "pregunta": "¿Intruso?",
                                                                                  "respuesta": "{}", "orden": 1, "visible": "on"})
        self.assertEqual(PreguntaFrecuente.objects.count(), n)
        precios = self.client.get("/admin/precios/").content.decode()
        self.assertIn("GEMA", precios)
        self.assertNotIn("GERP Lite", precios)

    def test_sin_login_no_hay_panel_ni_vistas_previas(self):
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        self.assertEqual(self.client.get("/vista-previa/x/index.html").status_code, 403)
        self.assertEqual(self.client.get("/web-local/gerp/").status_code, 403)

    # ---------------------------------------------------------------------------------------------- Precios y publicación
    def test_precio_borrador_aprobado_y_publicado(self):
        d = publicar_sitio(self.geagro, self.clara)
        self.assertEqual(d.estado, "ok", d.registro)
        lite = Plan.objects.get(sitio=self.geagro, clave="lite")
        self.client.force_login(self.clara)
        # Borrador: no cambia lo aprobado
        self.client.post("/admin/precios/", self._form_precios(lite, precio="99.000", accion="borrador"))
        lite.refresh_from_db()
        self.assertEqual(lite.precio, "89.250")
        self.assertTrue(lite.has_unpublished_changes)
        self.assertEqual(estado_sitio(self.geagro)["situacion"], "al_dia")
        # Aprobado: queda pendiente de publicar
        self.client.post("/admin/precios/", self._form_precios(lite, precio="99.000", accion="aprobar"))
        lite.refresh_from_db()
        self.assertEqual(lite.precio, "99.000")
        self.assertEqual(estado_sitio(self.geagro)["situacion"], "pendiente")
        web = (despliegue.raiz(self.geagro) / "actual" / "index.html").read_text()
        self.assertNotIn("$99.000", web)  # todavía no está en la web
        d = publicar_sitio(self.geagro, self.clara)
        self.assertEqual(d.estado, "ok", d.registro)
        web = (despliegue.raiz(self.geagro) / "actual" / "index.html").read_text()
        self.assertIn("$99.000", web)
        self.assertIn("abono de $99.000 + IVA", web)  # la pregunta frecuente con el precio también se actualiza
        self.assertEqual(estado_sitio(self.geagro)["situacion"], "al_dia")

    def _form_precios(self, plan, accion, **cambios):
        d = {f"precio_{plan.pk}": plan.precio, f"implementacion_{plan.pk}": plan.implementacion, f"moneda_{plan.pk}": plan.moneda,
             f"leyenda_vigencia_{plan.pk}": plan.leyenda_vigencia, "accion": accion}
        if plan.mas_iva:
            d[f"mas_iva_{plan.pk}"] = "on"
        for k, v in cambios.items():
            d[f"{k}_{plan.pk}"] = v
        if cambios.get("mas_iva") is False:
            d.pop(f"mas_iva_{plan.pk}", None)
        return d

    def _web(self, sitio, ruta=""):
        d = publicar_sitio(sitio, self.clara)
        self.assertEqual(d.estado, "ok", d.registro)
        return (despliegue.raiz(sitio) / "actual" / ruta / "index.html").read_text()

    # ---------------------------------------------------------------------------------------------- Precios: fuente única
    def test_precio_unico_en_tarjetas_landing_faq_y_datos(self):
        core = Plan.objects.get(sitio=self.gerp, clave="core")
        self.client.force_login(self.clara)
        self.client.post("/admin/precios/", self._form_precios(core, precio="199.000", implementacion="999.000", accion="aprobar"))
        home, landing, lite = self._web(self.gerp), self._web(self.gerp, "core/"), self._web(self.gerp, "lite/")
        self.assertIn("$199.000", home)                       # tarjeta
        self.assertIn('"price": 199000', home)               # datos estructurados
        self.assertIn("costo único de $999.000 + IVA", landing)  # pregunta frecuente de la implementación
        self.assertIn("$199.000 + IVA / mes", lite)           # «otros planes» en otra landing
        self.assertNotIn("178.500", home + landing + lite)

    def test_moneda_iva_y_vigencia_editables(self):
        plan = Plan.objects.get(sitio=self.gema)
        faq = PreguntaFrecuente.objects.get(sitio=self.gema, pregunta__startswith="¿El pago es mensual")
        self.assertNotIn("89.250", faq.respuesta)            # la respuesta referencia al plan, no repite el importe
        self.assertIn("[precio:mensual]", faq.respuesta)
        html = self._web(self.gema)
        self.assertIn("el abono es de $89.250 + IVA por mes", html)
        self.assertNotIn("dólares", html)
        self.assertIn("(*) Precios válidos para octubre, noviembre y diciembre. Actualización trimestral.", html)
        self.client.force_login(self.clara)
        self.client.post("/admin/precios/", self._form_precios(plan, precio="95", moneda="USD", mas_iva=False, leyenda_vigencia="", accion="aprobar"))
        html = self._web(self.gema)
        self.assertIn("el abono es de US$95 por mes", html)
        self.assertIn('"priceCurrency": "USD"', html)
        self.assertNotIn("(*)", html)                         # sin leyenda no hay asterisco ni nota
        self.assertNotIn("+ IVA", html.split('id="planes"')[1].split("</section>")[0])

    def test_geagro_sin_leyenda_de_vigencia(self):
        self.assertFalse(Plan.objects.filter(sitio=self.geagro).exclude(leyenda_vigencia="").exists())
        self.assertFalse(Plan.objects.filter(sitio__in=[self.geagro, self.gema], vigente_hasta__isnull=False).exists())
        self.assertNotIn("(*)", self._web(self.geagro))

    def test_faq_no_acepta_importes_escritos(self):
        from django.core.exceptions import ValidationError
        f = PreguntaFrecuente(sitio=self.gema, pregunta="¿Cuánto sale?", respuesta="<p>Sale $89.250 + IVA.</p>")
        with self.assertRaises(ValidationError):
            f.full_clean()
        f.respuesta = "<p>Sale [precio:inexistente].</p>"
        with self.assertRaises(ValidationError):
            f.full_clean()
        f.respuesta = "<p>Sale [precio:mensual].</p>"
        f.full_clean()

    def test_comparador_sin_a_confirmar(self):
        home = self._web(self.gerp)
        self.assertNotIn("A confirmar", home)
        self.assertNotIn("Consultar", home)
        # La fila sin ningún dato confirmado se muestra igual, con sus celdas vacías
        import re
        fila = re.search(r"<tr[^>]*><th scope=\"row\">Facturación electrónica ARCA \(AFIP\)</th>(.*?)</tr>", home, re.S)
        self.assertIsNotNone(fila)
        self.assertEqual(re.sub(r"<td[^>]*></td>", "", fila.group(1)).strip(), "")
        self.assertIn("Lotes y vencimientos</th>", home)                       # fila con datos: las celdas sin confirmar quedan vacías
        from contenidos.models import ValorFuncionalidad
        self.assertTrue(ValorFuncionalidad.objects.filter(estado="a_confirmar").exists())  # siguen pendientes en el administrador

    def test_ultima_modificacion_interna(self):
        plan = Plan.objects.get(sitio=self.gema)
        self.client.force_login(self.clara)
        self.client.post("/admin/precios/", self._form_precios(plan, precio="91.000", accion="aprobar"))
        plan.refresh_from_db()
        self.assertEqual(plan.modificado_por, "clara")
        self.assertIsNotNone(plan.ultima_modificacion)
        pantalla = self.client.get("/admin/precios/").content.decode()
        self.assertIn("historial", pantalla)
        html = self._web(self.gema)
        self.assertNotIn("clara", html)
        self.assertNotIn("Última modificación", html)

    def test_navegacion_planes_gerp(self):
        import re
        home, lite = self._web(self.gerp), self._web(self.gerp, "lite/")
        menu = re.search(r'<li class="nav-dd[^"]*" data-dd>(.*?)</ul>\s*</li>', home, re.S).group(1)
        # «Planes» es un único botón que abre el desplegable (no un enlace)
        self.assertRegex(menu, r'<button type="button" class="nav-dd-btn" aria-expanded="false" aria-controls="(submenu-\d+)">Planes')
        self.assertNotIn('<a href="#planes">Planes</a>', menu)
        for href, texto in (("lite/", "GERP Lite"), ("core/", "GERP Core"), ("plus/", "GERP Plus"), ("./#planes", "Ver todos los planes")):
            self.assertIn(f'<a href="{href}">{texto}</a>', menu)
        self.assertNotIn("Comparar planes", menu)
        self.assertIn('<a href="../lite/" aria-current="page">GERP Lite</a>', lite)   # la landing marca su plan
        self.assertIn('<a href="../#planes">Ver todos los planes</a>', lite)          # vuelve a las tarjetas de la home
        # Tarjetas enteras como enlace, sin enlaces anidados, con los precios de siempre
        for clave in ("lite", "core", "plus"):
            tarjeta = re.search(rf'<article class="[^"]*is-link[^"]*" id="plan-{clave}".*?</article>', home, re.S).group(0)
            self.assertEqual(len(re.findall(r"<a\s", tarjeta)), 2)                   # «Solicitar demo» y «Conocer el plan»
            self.assertIn(f'class="pp-plan-more" href="{clave}/"', tarjeta)
        self.assertIn("$89.250", home)
        self.assertNotIn("is-link", re.search(r'id="precio".*?</section>', lite, re.S).group(0))  # en la landing la tarjeta no se enlaza a sí misma

    # ---------------------------------------------------------------------------------------------- Logos y favicon
    def _imagen(self, nombre, contenido):
        from django.core.files.base import ContentFile
        from wagtail.images.models import Image
        return Image.objects.create(title=nombre, file=ContentFile(contenido, name=nombre))

    def _png(self, w, h):
        import io
        from PIL import Image as PI
        b = io.BytesIO(); PI.new("RGBA", (w, h), (200, 30, 90, 255)).save(b, "PNG"); return b.getvalue()

    def test_identidad_logos_y_favicon(self):
        from contenidos.models import IdentidadSitio
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 80"><text y="50">LOGO NUEVO</text></svg>'
        logo, fav = self._imagen("logo.svg", svg), self._imagen("fav.png", self._png(600, 600))
        ident = IdentidadSitio.objects.get(sitio=self.gerp)
        ident.logo, ident.favicon = logo, fav
        ident.save_revision()                      # borrador: la web no cambia
        ident.refresh_from_db()
        self.assertIsNone(ident.logo_id)
        self.assertNotIn("identidad/", self._web(self.gerp))
        ident.latest_revision.publish()            # aprobado: queda pendiente de publicar
        self.assertIn("Logos y favicon", [p[0] for p in estado_sitio(self.gerp)["pendientes"]])
        home = self._web(self.gerp)
        self.assertRegex(home, r'class="brand"[^>]*><img src="assets/img/identidad/gerp-logo-[0-9a-f]{8}\.svg"')
        self.assertNotIn("favicon.svg", home)     # se cargó solo el PNG: no queda el SVG anterior tapándolo
        raiz = despliegue.raiz(self.gerp) / "actual"
        from PIL import Image as PI
        self.assertEqual(PI.open(raiz / "assets/icons/favicon/android-chrome-512x512.png").size, (512, 512))
        self.assertEqual(PI.open(raiz / "assets/icons/favicon/apple-touch-icon.png").size, (180, 180))
        self.assertIn((48, 48), PI.open(raiz / "favicon.ico").info["sizes"])
        lite = (raiz / "lite/index.html").read_text()
        self.assertIn("gerp-planes/gerp-lite-logo-blanco.svg", lite)   # la landing del plan conserva su logo
        # GEMA sin cambios: sigue con sus logos y favicon de siempre
        gema = self._web(self.gema)
        self.assertNotIn("identidad/", gema)
        self.assertIn("favicon.svg", gema)

    def test_identidad_validaciones(self):
        from django.core.exceptions import ValidationError
        from contenidos.models import IdentidadSitio
        ident = IdentidadSitio.objects.get(sitio=self.gema)
        for campo, img in (("favicon", self._imagen("rect.png", self._png(800, 400))),       # no cuadrado
                           ("favicon", self._imagen("chico.png", self._png(128, 128))),      # menos de 512 px
                           ("favicon_svg", self._imagen("no-svg.png", self._png(600, 600))),  # no es SVG
                           ("logo", self._imagen("logo-chico.png", self._png(120, 40)))):    # logo de baja resolución
            setattr(ident, campo, img)
            with self.assertRaises(ValidationError, msg=campo) as e:
                ident.full_clean()
            self.assertIn(campo, e.exception.message_dict)
            setattr(ident, campo, None)

    def test_icono_de_plan_como_imagen(self):
        plan = Plan.objects.get(sitio=self.gerp, clave="core")
        plan.icono_img = self._imagen("icono.svg", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 42"><circle cx="22" cy="21" r="20"/></svg>')
        plan.save_revision().publish()
        home = self._web(self.gerp)
        self.assertRegex(home, r'(?s)id="plan-core".*?<img src="assets/img/identidad/plan-core-icono-[0-9a-f]{8}\.svg"')

    def test_testimonio_autorizado_exige_datos(self):
        from django.core.exceptions import ValidationError
        from contenidos.models import Testimonio
        t = Testimonio.objects.filter(sitio=self.gerp).first()
        self.assertEqual(t.estado, "pendiente")
        t.estado = "autorizado"
        with self.assertRaises(ValidationError):
            t.full_clean()

    def test_publicacion_fallida_no_toca_la_web(self):
        ok = publicar_sitio(self.gema, self.clara)
        self.assertEqual(ok.estado, "ok", ok.registro)
        antes = despliegue.version_actual(self.gema)
        self.gema.destino, self.gema.comando_despliegue = "comando", "echo subiendo {carpeta}; exit 3"
        self.gema.save()
        mal = publicar_sitio(self.gema, self.clara)
        self.assertEqual(mal.estado, "fallo")
        self.assertIn("terminó con error", mal.registro)
        self.assertEqual(despliegue.version_actual(self.gema), antes)
        self.assertEqual(estado_sitio(self.gema)["situacion"], "error")

    def test_volver_a_la_version_anterior(self):
        v1 = publicar_sitio(self.gerp, self.clara)
        time.sleep(1.1)
        v2 = publicar_sitio(self.gerp, self.clara)
        self.assertEqual(despliegue.version_actual(self.gerp), v2.version)
        d = volver_atras(self.gerp, self.clara)
        self.assertEqual(d.estado, "ok", d.registro)
        self.assertEqual(despliegue.version_actual(self.gerp), v1.version)

    def test_testimonios_pendientes_no_se_publican(self):
        from publicacion.exportar import datos_sitio
        archivos, _ = datos_sitio(self.gerp)
        self.assertEqual(archivos["gerp.json"]["testimonials"], [])

    # ---------------------------------------------------------------------------------------------- Formulario de demo
    def _enviar(self, **extra):
        datos = {"token": signing.dumps({"s": "gema", "t": time.time() - 10}, salt=SAL), "sitio": "gema", "nombre": "Ana",
                 "email": "ana@example.com", "consentimiento": True, "producto": "GEMA"}
        datos.update(extra)
        return self.client.post("/api/formularios/demo/", json.dumps(datos), content_type="application/json")

    def test_formulario_valido_se_registra_y_avisa(self):
        cache.clear()
        r = self._enviar()
        self.assertEqual(r.status_code, 200, r.content)
        s = SolicitudDemo.objects.get()
        self.assertEqual((s.sitio.clave, s.estado), ("gema", "nuevo"))
        self.assertNotIn("127.0.0.1", s.ip_hash)
        self.assertEqual(len(mail.outbox), 1)

    def test_formulario_antispam(self):
        cache.clear()
        self.assertEqual(self._enviar(sitio_web="http://spam").status_code, 200)  # trampa: responde OK y no guarda
        self.assertEqual(self._enviar(token="falso").status_code, 400)
        self.assertEqual(self._enviar(consentimiento=False).status_code, 400)
        self.assertEqual(SolicitudDemo.objects.count(), 0)
        r = self.client.post("/api/formularios/demo/", "{}", content_type="application/json", HTTP_ORIGIN="https://otro-sitio.com")
        self.assertEqual(r.status_code, 403)
        for _ in range(5):
            self._enviar()
        self.assertEqual(self._enviar().status_code, 429)
