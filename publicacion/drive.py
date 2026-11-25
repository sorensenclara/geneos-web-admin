"""Busca en una carpeta pública de Google Drive el PDF con un nombre exacto y devuelve el más reciente.

Usa la API de Drive v3 con una clave de API (GWA_DRIVE_API_KEY): no hace falta iniciar sesión ni una cuenta de servicio,
porque la carpeta está compartida como «Cualquier persona con el enlace». Solo se consultan las carpetas y nombres
cargados en «Recursos descargables»: nadie puede pedir otro archivo por esta vía.
"""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://www.googleapis.com/drive/v3/files"
DESCARGA = "https://drive.google.com/uc?export=download&id={id}"
PDF = "application/pdf"


class DriveError(Exception):
    """Drive no respondió o respondió con un error (clave inválida, cuota, carpeta no compartida…)."""


class NoEncontrado(DriveError):
    """La carpeta no tiene un PDF con ese nombre exacto."""


def _literal(texto):
    return texto.replace("\\", "\\\\").replace("'", "\\'")


def consultar(params, timeout=8):
    """GET a la API de Drive. Aparte para poder reemplazarla en las pruebas."""
    try:
        with urlopen(Request(f"{API}?{urlencode(params)}", headers={"Accept": "application/json"}), timeout=timeout) as r:
            return json.loads(r.read().decode())
    except HTTPError as e:
        try:
            detalle = json.loads(e.read().decode()).get("error", {}).get("message", "")
        except Exception:
            detalle = ""
        raise DriveError(f"Drive respondió {e.code}: {detalle}".strip(": ")) from e
    except (URLError, TimeoutError, ValueError) as e:
        raise DriveError(f"No se pudo consultar Drive: {e}") from e


def ultimo_pdf(carpeta_id, nombre, clave_api):
    """{id, name, modifiedTime, size} del PDF llamado exactamente `nombre` modificado más recientemente en la carpeta."""
    if not clave_api:
        raise DriveError("Falta GWA_DRIVE_API_KEY en la configuración del servidor.")
    datos = consultar({
        "q": f"'{_literal(carpeta_id)}' in parents and name = '{_literal(nombre)}' and trashed = false",
        "fields": "files(id,name,mimeType,modifiedTime,size)",
        "orderBy": "modifiedTime desc", "pageSize": "20",
        "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
        "key": clave_api,
    })
    # Drive compara nombres sin distinguir mayúsculas en algunos casos: se exige el nombre exacto y que sea PDF
    archivos = [f for f in datos.get("files", []) if f.get("name") == nombre and f.get("mimeType") == PDF]
    if not archivos:
        raise NoEncontrado(f"No hay un PDF llamado «{nombre}» en la carpeta.")
    return max(archivos, key=lambda f: f.get("modifiedTime", ""))


def url_descarga(archivo_id):
    return DESCARGA.format(id=archivo_id)
