"""Lectura automática de «Actualidad e ideas para publicar»: controles de verificación, registro de fallas, duplicados,
resultados conservados, prioridad, eventos confirmados, novedades oficiales y lectura sin bloquear.

    python manage.py test editorial.test_lector

Sin red: las respuestas de las fuentes se simulan (editorial.lector.descargar).
"""
import datetime
import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from sitios.models import LineaProducto, SitioWeb

from . import lector
from .catalogo import sembrar
from .ideas import crear_borrador
from .lector import ErrorLectura
from .models import ActualizacionActualidad, FuenteActualidad, IdeaEditorial
from .vistas import _ideas, eventos_por_confirmar

VAR = Path(tempfile.mkdtemp(prefix="gwa-test-lector-"))
BLOG = "/admin/blog/"
AHORA = timezone.now()


def rfc822(dias=0):
    return (AHORA - datetime.timedelta(days=dias)).strftime("%a, %d %b %Y %H:%M:%S +0000")


def rss(*items):
    cuerpo = "".join(f"<item><title>{t}</title><link>{u}</link><pubDate>{d}</pubDate><description>{r}</description></item>" for t, u, d, r in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>Prueba</title>{cuerpo}</channel></rss>'.encode()


ATOM = f"""<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>IRAM</title>
<entry><title>Nueva versión de la norma IRAM 3517 sobre extintores</title><link rel="alternate" href="https://www.iram.org.ar/novedades/3517/"/>
<updated>{(AHORA - datetime.timedelta(days=1)).isoformat()}</updated><summary>&lt;p&gt;Actualización de la norma de &lt;b&gt;matafuegos&lt;/b&gt;.&lt;/p&gt;</summary></entry>
</feed>""".encode()


class Red:
    """Respuestas simuladas por URL. robots.txt: 404 salvo que se indique."""

    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.pedidos = []

    def __call__(self, url, timeout=15):
        self.pedidos.append(url)
        for clave, valor in self.respuestas.items():
            if url.startswith(clave):
                if isinstance(valor, Exception):
                    raise valor
                return valor
        if url.endswith("/robots.txt"):
            raise ErrorLectura("El servidor respondió 404 (Not Found).")
        raise ErrorLectura("No se pudo conectar: sin respuesta simulada")


@override_settings(GWA_VAR_DIR=VAR, MEDIA_ROOT=str(VAR / "media"), ACTUALIDAD_EN_SEGUNDO_PLANO=False, YOUTUBE_API_KEY="")
class LecturaAutomatica(TestCase):
    @classmethod
    def setUpTestData(cls):
        with override_settings(GWA_VAR_DIR=VAR):
            call_command("inicializar", "--sin-publicar", stdout=open("/dev/null", "w"))
        sembrar()
        cls.gerp = SitioWeb.objects.get(clave="gerp")
        cls.gema = SitioWeb.objects.get(clave="gema")
        cls.geagro = SitioWeb.objects.get(clave="geagro")
        cls.geneos = SitioWeb.objects.get(clave="geneos")
        cls.vid = LineaProducto.objects.get(sitio=cls.geagro, clave="vid")
        cls.clara = User.objects.create_superuser("clara", "clara@example.com", "x")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(VAR, ignore_errors=True)

    def leer(self, respuestas, claves):
        red = Red(respuestas)
        with mock.patch.object(lector, "descargar", red), mock.patch.object(lector, "GDELT_PAUSA", 0):
            act = lector.actualizar_fuentes("comando", claves=claves)
        return act, red

    FISCALES = "https://www.ambito.com/rss/pages/novedades-fiscales.xml"

    def test_controles_y_registro_de_lo_que_funciona_y_lo_que_falla(self):
        respuestas = {
            self.FISCALES: rss(("ARCA extiende el vencimiento de la factura electrónica para monotributistas", "https://www.ambito.com/a1?utm_source=rss", rfc822(1), "Resolución general 5800 de ARCA."),
                               ("Dólar blue hoy: a cuánto cotiza", "https://www.ambito.com/a2", rfc822(0), "Cotización."),
                               ("Ganancias: nota vieja", "https://www.ambito.com/a3", rfc822(400), "")),
            "https://www.iprofesional.com/rss/impuestos": ErrorLectura("La red de este equipo no permite conectarse a ese sitio (proxy o lista de sitios permitidos)."),
            "https://www.iprofesional.com/robots.txt": b"User-agent: *\nAllow: /\n",
            "https://www.ambito.com/rss/pages/negocios.xml": rss(("Sin fecha", "https://www.ambito.com/a4", "", "")),
            "https://www.ambito.com/rss/pages/economia.xml": rss(("Partido de fútbol", "https://www.ambito.com/a5", rfc822(1), "")),
            "https://www.iprofesional.com/rss/legales": b"<html>no es un feed</html>",
            "https://www.iprofesional.com/rss/management": rss(("Gestión", "https://x/1", rfc822(200), "")),
        }
        claves = ["gerp-ambito-fiscales", "gerp-iprofesional-impuestos", "gerp-ambito-negocios", "gerp-ambito-economia", "gerp-iprofesional-legales",
                  "gerp-iprofesional-management", "gerp-cronista", "gerp-arca-youtube"]
        act, red = self.leer(respuestas, claves)
        self.assertEqual(act.estado, "parcial")
        f = {x.clave: x for x in FuenteActualidad.objects.filter(clave__in=claves)}
        self.assertEqual(f["gerp-ambito-fiscales"].estado, "activa")
        self.assertIsNotNone(f["gerp-ambito-fiscales"].verificada)
        self.assertIn("Verificada", f["gerp-ambito-fiscales"].motivo)
        self.assertEqual((f["gerp-ambito-fiscales"].items_leidos, f["gerp-ambito-fiscales"].items_relevantes), (3, 1))
        self.assertEqual(f["gerp-iprofesional-impuestos"].estado, "prueba")
        self.assertIn("La red de este equipo", f["gerp-iprofesional-impuestos"].motivo)
        self.assertIn("título, fecha y enlace", f["gerp-ambito-negocios"].motivo)
        self.assertIn("se relaciona con el producto", f["gerp-ambito-economia"].motivo)
        self.assertIn("no es un feed", f["gerp-iprofesional-legales"].motivo)
        self.assertIn("90 días", f["gerp-iprofesional-management"].motivo)
        # Descartadas y YouTube sin clave: no se consultan
        self.assertFalse(any("cronista" in u or "googleapis" in u for u in red.pedidos))
        self.assertEqual(f["gerp-cronista"].estado, "descartada")
        # Solo la nota relacionada, con fuente, fecha, enlace, resumen breve y relación; menciona normativa pero es periodística
        items = IdeaEditorial.objects.filter(fuente_actualidad__isnull=False)
        self.assertEqual(items.count(), 1)
        i = items.get()
        self.assertEqual((i.sitio, i.tipo, i.naturaleza, i.etiqueta), (self.gerp, "noticia", "periodistica", "Noticia periodística"))
        self.assertTrue(i.menciona_normativa)
        self.assertEqual(i.fuente, "Ámbito · Novedades Fiscales")
        self.assertIn("Menciona: arca", i.relacion)
        self.assertEqual(i.publicado, (AHORA - datetime.timedelta(days=1)).astimezone(timezone.get_current_timezone()).date())
        # En la pantalla: aviso de normativa; nada de las fuentes que no pasaron
        self.client.force_login(self.clara)
        html = self.client.get(BLOG + "?sitio=gerp").content.decode()
        self.assertIn("ARCA extiende el vencimiento", html)
        self.assertIn("no el documento oficial", html)
        self.assertIn("Noticia periodística", html)
        pagina = self.client.get(f"{BLOG}gerp/fuentes/").content.decode()
        self.assertIn("La red de este equipo no permite conectarse", pagina)
        self.assertIn("Pendiente de clave", pagina)

    def test_no_se_muestran_fuentes_sin_verificar_y_falla_conserva_resultados(self):
        f = FuenteActualidad.objects.get(clave="gema-iram")
        IdeaEditorial.objects.create(sitio=self.gema, tipo="noticia", naturaleza="oficial", titulo="Sin verificar", fuente="IRAM",
                                     publicado=timezone.localdate(), consultado=timezone.localdate(), fuente_actualidad=f)
        self.assertNotIn("Sin verificar", [i.titulo for i in _ideas(self.gema, None)])
        url = "https://www.iram.org.ar/novedades/category/institucional/feed/"
        self.leer({url: ATOM}, ["gema-iram"])
        f.refresh_from_db()
        self.assertEqual(f.estado, "activa")
        titulos = [i.titulo for i in _ideas(self.gema, None)]
        self.assertIn("Nueva versión de la norma IRAM 3517 sobre extintores", titulos)
        i = IdeaEditorial.objects.get(titulo__startswith="Nueva versión")
        self.assertEqual((i.etiqueta, i.prioritaria, i.resumen), ("Publicación oficial", True, "Actualización de la norma de matafuegos."))
        # La lectura siguiente falla: los resultados anteriores siguen y se registra el error
        self.leer({url: ErrorLectura("El sitio no respondió a tiempo.")}, ["gema-iram"])
        f.refresh_from_db()
        self.assertEqual(f.estado, "activa")
        self.assertEqual(f.ultimo_error, "El sitio no respondió a tiempo.")
        self.assertIn("Nueva versión de la norma IRAM 3517 sobre extintores", [x.titulo for x in _ideas(self.gema, None)])
        # Pausada: no se lee y no se muestra
        f.estado = "pausada"
        f.save()
        self.assertNotIn("Nueva versión de la norma IRAM 3517 sobre extintores", [x.titulo for x in _ideas(self.gema, None)])

    def test_robots_txt_y_duplicados(self):
        respuestas = {
            "https://www.losandes.com.ar/robots.txt": b"User-agent: *\nDisallow: /rss/\n",
            self.FISCALES: rss(("ARCA: nuevo régimen de facturación para pymes", "https://www.ambito.com/n1", rfc822(1), ""),
                               ("ARCA: nuevo régimen de facturación para pymes", "https://www.ambito.com/n1-copia", rfc822(1), "")),
            "https://www.ambito.com/rss/pages/negocios.xml": rss(("Otra nota sobre facturación de pymes", "https://ambito.com/n1/", rfc822(1), "")),
        }
        self.leer(respuestas, ["geneos-losandes-economia", "gerp-ambito-fiscales", "gerp-ambito-negocios"])
        self.assertIn("robots.txt", FuenteActualidad.objects.get(clave="geneos-losandes-economia").motivo)
        # Mismo título o mismo enlace (con o sin www, barra final): una sola tarjeta
        self.assertEqual(IdeaEditorial.objects.filter(sitio=self.gerp, fuente_actualidad__isnull=False).count(), 1)
        # Una segunda lectura no repite
        self.leer(respuestas, ["gerp-ambito-fiscales"])
        self.assertEqual(IdeaEditorial.objects.filter(sitio=self.gerp, fuente_actualidad__isnull=False).count(), 1)

    def test_gdelt_es_periodistica_aunque_mencione_un_organismo(self):
        datos = {"articles": [
            {"url": "https://www.argentina.gob.ar/noticias/inaes-cooperativas", "title": "El INAES anunció cambios para cooperativas de trabajo",
             "seendate": (AHORA - datetime.timedelta(hours=5)).strftime("%Y%m%dT%H%M%SZ"), "domain": "argentina.gob.ar", "language": "Spanish", "sourcecountry": "Argentina"},
            {"url": "https://diario.com.ar/futbol", "title": "Resultado del partido", "seendate": AHORA.strftime("%Y%m%dT%H%M%SZ"), "domain": "diario.com.ar"}]}
        act, red = self.leer({lector.GDELT_API: json.dumps(datos).encode()}, ["geneos-gdelt"])
        self.assertIn("sourcecountry%3Aargentina", red.pedidos[0])
        self.assertIn("sourcelang%3Aspanish", red.pedidos[0])
        i = IdeaEditorial.objects.get(sitio=self.geneos, fuente_actualidad__clave="geneos-gdelt")
        self.assertEqual((i.naturaleza, i.etiqueta, i.fuente), ("periodistica", "Noticia periodística", "argentina.gob.ar (vía GDELT)"))
        # GDELT devuelve texto cuando la consulta es inválida
        FuenteActualidad.objects.filter(clave="gerp-gdelt").update(estado="prueba")
        self.leer({lector.GDELT_API: b"Your search contained too many terms."}, ["gerp-gdelt"])
        self.assertIn("GDELT respondió", FuenteActualidad.objects.get(clave="gerp-gdelt").motivo)

    @override_settings(YOUTUBE_API_KEY="clave-de-prueba")
    def test_youtube_api_con_clave_en_el_servidor(self):
        canal = {"items": [{"snippet": {"title": "ARCA"}, "contentDetails": {"relatedPlaylists": {"uploads": "UUe0zC5Uf5U1YDDMF3_W-97A"}}}]}
        videos = {"items": [{"snippet": {"title": "Cómo emitir una factura electrónica", "publishedAt": AHORA.isoformat(), "description": "Tutorial oficial.",
                                         "resourceId": {"videoId": "abc123"}}}]}
        act, red = self.leer({lector.YOUTUBE_API + "channels": json.dumps(canal).encode(), lector.YOUTUBE_API + "playlistItems": json.dumps(videos).encode()},
                             ["gerp-arca-youtube"])
        i = IdeaEditorial.objects.get(fuente_actualidad__clave="gerp-arca-youtube")
        self.assertEqual((i.etiqueta, i.fuente, i.fuente_url), ("Publicación oficial", "ARCA · YouTube", "https://www.youtube.com/watch?v=abc123"))
        self.assertTrue(i.prioritaria)
        # La clave nunca llega al navegador
        self.client.force_login(self.clara)
        for url in (BLOG + "?sitio=gerp", f"{BLOG}gerp/fuentes/"):
            self.assertNotIn("clave-de-prueba", self.client.get(url).content.decode())
        # Cuota agotada: motivo legible y sin la clave
        with mock.patch.object(lector, "descargar", side_effect=ErrorLectura("Se agotó la cuota diaria gratuita de la API.")):
            lector.actualizar_fuentes("comando", claves=["gerp-arca-youtube"])
        f = FuenteActualidad.objects.get(clave="gerp-arca-youtube")
        self.assertIn("cuota", f.ultimo_error)
        self.assertNotIn("clave-de-prueba", f.ultimo_error + f.motivo)

    def test_prioridad_ordena_primero_lo_oficial_y_lo_prioritario(self):
        hoy = timezone.localdate()
        comun = dict(sitio=self.gerp, tipo="noticia", consultado=hoy, fuente="x")
        IdeaEditorial.objects.create(titulo="Nota general de hoy", naturaleza="periodistica", publicado=hoy, **comun)
        IdeaEditorial.objects.create(titulo="Comunicado de ARCA de ayer", naturaleza="oficial", publicado=hoy - datetime.timedelta(days=1), **comun)
        self.assertEqual([i.titulo for i in _ideas(self.gerp, None)][:2], ["Comunicado de ARCA de ayer", "Nota general de hoy"])
        # Marcar una fuente como prioritaria desde el administrador
        f = FuenteActualidad.objects.get(clave="gerp-ambito-fiscales")
        self.client.force_login(self.clara)
        self.client.post(f"{BLOG}fuente/{f.pk}/prioritaria/", {"sitio": "gerp"})
        f.refresh_from_db()
        self.assertTrue(f.prioritaria)

    def test_eventos_solo_confirmados_como_proximos(self):
        proximos = [i.titulo for i in _ideas(self.geneos, None)]
        self.assertIn("56° Congreso de Cooperativas de Río Negro", proximos)
        self.assertNotIn("CongregaCoop 2026 · Congreso Internacional de Cooperativismo", proximos)  # solo según prensa
        self.assertNotIn("FLISoL 2027", proximos)
        por_confirmar = [e.titulo for e in eventos_por_confirmar(self.geneos)]
        self.assertIn("FLISoL 2027", por_confirmar)
        self.assertIn("CongregaCoop 2026 · Congreso Internacional de Cooperativismo", por_confirmar)
        self.assertIn("Expoagro 2027", [i.titulo for i in _ideas(self.geagro, None)])
        self.assertEqual([i.titulo for i in _ideas(self.gerp, None, {"periodo": "7", "contenido": "evento", "fuente": ""})], [])
        e = IdeaEditorial.objects.get(clave="evento:expoagro-2027")
        self.assertEqual((e.evento_fecha, e.evento_fin), (datetime.date(2027, 3, 9), datetime.date(2027, 3, 12)))
        self.client.force_login(self.clara)
        html = self.client.get(f"{BLOG}geneos/actualidad/").content.decode()
        self.assertIn("Eventos por confirmar", html)
        # Un evento confirmado que ya terminó no aparece
        e.evento_fecha, e.evento_fin = datetime.date(2026, 3, 1), datetime.date(2026, 3, 4)
        e.save()
        self.assertNotIn("Expoagro 2027", [i.titulo for i in _ideas(self.geagro, None)])

    def test_novedad_oficial_manual(self):
        self.client.force_login(self.clara)
        hoy = timezone.localdate().isoformat()
        r = self.client.post(f"{BLOG}gerp/novedad-oficial/", {"url": "https://www.boletinoficial.gob.ar/detalleAviso/primera/123/20261015",
                                                              "titulo": "Resolución General 5800/2026", "organismo": "ARCA", "documento": "Resolución general",
                                                              "publicado": hoy})
        self.assertEqual(r.status_code, 302)
        i = IdeaEditorial.objects.get(titulo="Resolución General 5800/2026")
        self.assertEqual((i.naturaleza, i.prioritaria, i.menciona_normativa, i.estado, i.cargada_por), ("oficial", True, True, "guardada", self.clara))
        html = self.client.get(BLOG + "?sitio=gerp").content.decode()
        self.assertIn("revisá el texto oficial antes de afirmar vigencia", html)
        art = crear_borrador(i, self.clara)
        self.assertIn("No afirmar vigencia ni obligaciones", art.get_latest_revision_as_object().fuentes)
        # Un enlace que no es oficial no se presenta como oficial
        self.client.post(f"{BLOG}gerp/novedad-oficial/", {"url": "https://www.diario.com.ar/arca-cambia", "titulo": "ARCA cambia el régimen",
                                                          "organismo": "Diario", "documento": "Comunicado", "publicado": hoy})
        self.assertEqual(IdeaEditorial.objects.get(titulo="ARCA cambia el régimen").naturaleza, "periodistica")
        # Repetida o con fecha futura: no se carga
        r = self.client.post(f"{BLOG}gerp/novedad-oficial/", {"url": "https://www.boletinoficial.gob.ar/detalleAviso/primera/123/20261015",
                                                              "titulo": "x", "organismo": "ARCA", "publicado": hoy})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(IdeaEditorial.objects.filter(titulo="x").count(), 0)

    def test_cerrojo_24_horas_y_lectura_sin_bloquear(self):
        self.assertTrue(lector.tomar_cerrojo())
        self.assertFalse(lector.tomar_cerrojo())  # dos lecturas a la vez: no
        self.assertTrue(lector.en_curso())
        self.assertIsNone(lector.actualizar_fuentes("comando"))
        self.client.force_login(self.clara)
        self.assertEqual(self.client.post(f"{BLOG}lectura/auto/").json()["iniciada"], False)
        lector.soltar_cerrojo()
        self.assertTrue(lector.necesita_actualizar())
        with mock.patch.object(lector, "descargar", Red({})), mock.patch.object(lector, "GDELT_PAUSA", 0):
            self.assertTrue(self.client.post(f"{BLOG}lectura/auto/").json()["iniciada"])
        self.assertFalse(lector.necesita_actualizar())  # la siguiente, dentro de 24 horas
        self.assertFalse(self.client.post(f"{BLOG}lectura/auto/").json()["iniciada"])
        a = ActualizacionActualidad.objects.first()
        self.assertEqual((a.origen, a.estado), ("ingreso", "error"))  # sin red: todas fallan y queda registrado
        self.assertFalse(lector.en_curso())
        estado = self.client.get(f"{BLOG}lectura/estado/").json()
        self.assertFalse(estado["leyendo"])
        # «Actualizar ahora» lee aunque no hayan pasado 24 horas, sin esperar en la pantalla (en segundo plano en el servidor real)
        with mock.patch.object(lector, "iniciar", return_value=True) as ini:
            self.client.post(f"{BLOG}gerp/actualizar/", {"next": BLOG + "?sitio=gerp"})
        ini.assert_called_once()
        self.assertTrue(ini.call_args.kwargs["forzar"])
        # El administrador incluye el pedido liviano al ingresar
        self.assertIn("gwa/actualidad.js", self.client.get("/admin/").content.decode())

    def test_parseo_de_formatos(self):
        items = lector.leer_feed(ATOM)
        self.assertEqual(items[0]["url"], "https://www.iram.org.ar/novedades/3517/")
        rdf = b"""<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
          <item><title>T</title><link>https://a.com/1</link><dc:date>2026-10-15T10:00:00-03:00</dc:date></item></rdf:RDF>"""
        self.assertEqual(lector.leer_feed(rdf)[0]["fecha"].date(), datetime.date(2026, 10, 15))
        with self.assertRaises(ErrorLectura):
            lector.leer_feed(b"<html><body>hola</body></html>")
        self.assertEqual(lector.fecha("20261016T120000Z").hour, 12)
        self.assertEqual(lector.huella("https://www.ambito.com/a1/?utm_source=x"), lector.huella("http://ambito.com/a1"))
        self.assertEqual(lector.coincidencias("La AFIP y el IVA", ["afip", "iva", "ganancias"]), ["afip", "iva"])
        self.assertEqual(lector.coincidencias("Inversiones", ["iva"]), [])
