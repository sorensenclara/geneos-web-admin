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


@override_settings(GWA_VAR_DIR=VAR, GWA_FORM_SEGUNDOS_MINIMOS=0)
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
        self.client.post("/admin/precios/", {f"precio_{lite.pk}": "99.000", f"impl_{lite.pk}": lite.implementacion, "accion": "borrador"})
        lite.refresh_from_db()
        self.assertEqual(lite.precio, "89.250")
        self.assertTrue(lite.has_unpublished_changes)
        self.assertEqual(estado_sitio(self.geagro)["situacion"], "al_dia")
        # Aprobado: queda pendiente de publicar
        self.client.post("/admin/precios/", {f"precio_{lite.pk}": "99.000", f"impl_{lite.pk}": lite.implementacion, "accion": "aprobar"})
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
