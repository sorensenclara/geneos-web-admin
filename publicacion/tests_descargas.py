"""Descarga con dirección fija desde Drive (/descargas/<sitio>/<ruta>/): nombre exacto, archivo más reciente,
nuevo ID al volver a subir, fallas de Drive y validaciones del recurso. Drive se simula: no hay red en las pruebas."""
from unittest import mock

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from contenidos.models import Recurso, carpeta_drive_id
from publicacion import drive
from sitios.models import SitioWeb

CARPETA = "1pRbw46EytRqZBP3mNmI4HqxvsfKtDJJ2"
URL = "/descargas/gema/brochure/"


def archivo(id_, nombre="Brochure GEMA.pdf", fecha="2026-11-01T10:00:00.000Z", mime=drive.PDF):
    return {"id": id_, "name": nombre, "mimeType": mime, "modifiedTime": fecha, "size": "8155877"}


@override_settings(GWA_DRIVE_API_KEY="clave-de-prueba", GWA_DRIVE_CACHE_SEGUNDOS=300)
class DescargaDesdeDrive(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gema = SitioWeb.objects.get_or_create(clave="gema", defaults={"nombre": "GEMA"})[0]
        cls.recurso = Recurso.objects.create(sitio=cls.gema, titulo="Brochure GEMA", clave="brochure",
                                             drive_carpeta=f"https://drive.google.com/drive/folders/{CARPETA}?usp=sharing",
                                             drive_nombre="Brochure GEMA.pdf")

    def setUp(self):
        cache.clear()

    def _get(self, archivos=None, error=None):
        with mock.patch.object(drive, "consultar", side_effect=error, return_value={"files": archivos or []}) as m:
            return self.client.get(URL), m

    def test_nombre_exacto_y_el_mas_reciente(self):
        r, m = self._get([
            archivo("viejo", fecha="2026-10-01T10:00:00.000Z"),
            archivo("vigente", fecha="2026-11-20T10:00:00.000Z"),
            archivo("copia", nombre="Brochure GEMA (1).pdf", fecha="2026-11-23T10:00:00.000Z"),
            archivo("minusculas", nombre="brochure gema.pdf", fecha="2026-11-23T10:00:00.000Z"),
            archivo("doc", mime="application/vnd.google-apps.document", fecha="2026-11-23T10:00:00.000Z"),
        ])
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "https://drive.google.com/uc?export=download&id=vigente")
        params = m.call_args[0][0]
        self.assertEqual(params["q"], f"'{CARPETA}' in parents and name = 'Brochure GEMA.pdf' and trashed = false")
        self.assertEqual(params["key"], "clave-de-prueba")
        self.recurso.refresh_from_db()
        self.assertEqual(self.recurso.drive_archivo_id, "vigente")

    def test_pdf_nuevo_con_el_mismo_nombre_y_otro_id(self):
        self._get([archivo("primero")])
        r, m = self._get([archivo("primero")])  # dentro del tiempo de caché no se vuelve a consultar
        self.assertEqual(m.call_count, 0)
        cache.clear()  # pasó el tiempo de caché
        r, _ = self._get([archivo("primero", fecha="2026-11-01T10:00:00.000Z"), archivo("segundo", fecha="2026-11-24T18:00:00.000Z")])
        self.assertEqual(r["Location"], drive.url_descarga("segundo"))

    def test_si_drive_falla_usa_el_ultimo_archivo(self):
        self._get([archivo("vigente")])
        cache.clear()
        r, _ = self._get(error=drive.DriveError("Drive respondió 500"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], drive.url_descarga("vigente"))

    def test_sin_archivo_ni_documento(self):
        r, _ = self._get([archivo("otro", nombre="Brochure GERP.pdf")])
        self.assertEqual(r.status_code, 503)
        self.assertIn("no está disponible", r.content.decode())

    @override_settings(GWA_DRIVE_API_KEY="")
    def test_sin_clave_de_api_no_consulta(self):
        r, m = self._get([archivo("vigente")])
        self.assertEqual(m.call_count, 0)
        self.assertEqual(r.status_code, 503)

    def test_solo_recursos_cargados_y_visibles(self):
        self.assertEqual(self.client.get("/descargas/gema/otro/").status_code, 404)
        self.assertEqual(self.client.get("/descargas/gerp/brochure/").status_code, 404)
        Recurso.objects.filter(pk=self.recurso.pk).update(visible=False)
        self.assertEqual(self.client.get(URL).status_code, 404)
        self.assertEqual(self.client.post(URL).status_code, 405)

    def test_validaciones_del_recurso(self):
        self.assertEqual(carpeta_drive_id(f"https://drive.google.com/drive/folders/{CARPETA}?usp=sharing"), CARPETA)
        self.assertEqual(carpeta_drive_id(CARPETA), CARPETA)
        self.assertEqual(carpeta_drive_id("https://example.com/"), "")
        for datos in ({"drive_carpeta": CARPETA}, {"drive_nombre": "Brochure GEMA.pdf"}, {},
                      {"drive_carpeta": CARPETA, "drive_nombre": "Brochure GEMA.pdf"}):  # el último sin ruta fija
            with self.assertRaises(ValidationError):
                Recurso(sitio=self.gema, titulo="x", **datos).full_clean()

    def test_comillas_en_el_nombre(self):
        with mock.patch.object(drive, "consultar", return_value={"files": []}) as m:
            with self.assertRaises(drive.NoEncontrado):
                drive.ultimo_pdf(CARPETA, "Brochure d'GEMA.pdf", "k")
        self.assertIn("name = 'Brochure d\\'GEMA.pdf'", m.call_args[0][0]["q"])
