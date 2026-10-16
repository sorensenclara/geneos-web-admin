"""«Cargar novedad oficial»: función complementaria para las publicaciones de organismos que no tienen RSS ni API (INAES, ARCA,
Boletín Oficial, SRT…). Se pega el enlace y se completan título, organismo y fecha; no se descarga ni se copia la página.

Solo se marca como «Publicación oficial» si el enlace es de un dominio oficial reconocido. Cualquier otro enlace queda como
noticia periodística. En ningún caso se afirma vigencia ni se interpretan obligaciones: el borrador lo recuerda.
"""
from urllib.parse import urlsplit

from django.utils import timezone
from django.utils.dateparse import parse_date

from .lector import huella
from .models import IdeaEditorial

DOCUMENTOS = ["Resolución", "Resolución general", "Disposición", "Decreto", "Ley", "Comunicado", "Norma técnica", "Circular", "Otro"]
NORMATIVOS = {"Resolución", "Resolución general", "Disposición", "Decreto", "Ley", "Norma técnica", "Circular"}
# Dominios de organismos e instituciones que publican sus propias novedades (sufijos).
DOMINIOS_OFICIALES = (".gob.ar", ".gov.ar", "gob.ar", "boletinoficial.gob.ar", "arca.gob.ar", "afip.gob.ar", "iram.org.ar",
                      "bomberosra.org.ar", "inta.gob.ar", "facttic.org.ar", "ica.coop", "aciamericas.coop", "coviar.ar", "senasa.gob.ar")


class ErrorNovedad(Exception):
    pass


def es_oficial(url):
    host = urlsplit(url).netloc.lower().split(":")[0].removeprefix("www.")
    return any(host == d.lstrip(".") or host.endswith("." + d.lstrip(".")) for d in DOMINIOS_OFICIALES)


def crear_novedad(sitio, d, usuario, lineas):
    url = d.get("url", "")
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ErrorNovedad("Pegá el enlace completo de la publicación (https://…).")
    if not d.get("titulo") or not d.get("organismo"):
        raise ErrorNovedad("Completá el título y el organismo que la publicó.")
    publicado = parse_date(d.get("publicado", ""))
    if publicado is None or publicado > timezone.localdate():
        raise ErrorNovedad("Indicá la fecha de publicación que figura en el documento.")
    clave = huella(url)
    if IdeaEditorial.objects.filter(sitio=sitio, clave=clave).exists():
        raise ErrorNovedad("Esa publicación ya está cargada.")
    oficial = es_oficial(url)
    documento = d.get("documento") if d.get("documento") in DOCUMENTOS else "Otro"
    linea = next((l for l in lineas if str(l.pk) == d.get("linea")), None)
    relacion = (f"{documento} publicada por {d['organismo']} en su sitio oficial." if oficial else
                f"Enlace cargado a mano ({p.netloc}); no es un sitio oficial reconocido: verificar con el documento original.")
    return IdeaEditorial.objects.create(
        sitio=sitio, linea=linea, tipo="noticia", fuente_tipo="oficial" if oficial else "medio",
        naturaleza="oficial" if oficial else "periodistica", titulo=d["titulo"][:200], resumen=d.get("resumen", "")[:600],
        relacion=relacion[:300], fuente=d["organismo"][:120], fuente_url=url[:600], publicado=publicado, consultado=timezone.localdate(),
        menciona_normativa=documento in NORMATIVOS, prioritaria=oficial, cargada_por=usuario, palabras_clave=d["titulo"][:250],
        intencion="Informativa", estado="guardada", clave=clave)
