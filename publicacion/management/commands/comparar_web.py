"""Compara la web que generaría el administrador (contenido aprobado) con una web publicada o una carpeta.

  manage.py comparar_web gerp https://sorensenclara.github.io/web-gerp/
  manage.py comparar_web gema ../gema-web

No publica nada: genera en una carpeta temporal y la borra al terminar. Sale con código 1 si hay diferencias,
para usarlo antes de una publicación o en una verificación automática.
"""
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from publicacion.comparar import comparar, sin_diferencias
from publicacion.motor import ErrorGeneracion, NoConectado, generar, validar
from sitios.models import SitioWeb


class Command(BaseCommand):
    help = "Compara lo que generaría el administrador con una web publicada (URL) o una carpeta."

    def add_arguments(self, parser):
        parser.add_argument("sitio", help="gerp, geagro, gema")
        parser.add_argument("referencia", help="URL base de la web publicada o carpeta local")
        parser.add_argument("--archivos", action="store_true", help="listar también los archivos que sobran o faltan")

    def handle(self, sitio, referencia, archivos=False, **_):
        try:
            s = SitioWeb.objects.get(clave=sitio)
        except SitioWeb.DoesNotExist:
            raise CommandError(f"No existe el sitio «{sitio}».")
        Path(settings.GWA_VAR_DIR).mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="gwa-comparar-", dir=settings.GWA_VAR_DIR))
        try:
            try:
                carpeta, datos, registro = generar(s, tmp)
            except (NoConectado, ErrorGeneracion) as e:
                raise CommandError(str(e))
            for e in validar(s, carpeta, datos):
                self.stdout.write(self.style.WARNING(f"Control: {e}"))
            if "FALTAN:" in registro:
                self.stdout.write(self.style.WARNING("Recursos faltantes:\n" + registro))
            res = comparar(carpeta, referencia)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        for clave, titulo in (("paginas_nuevas", "Páginas que se agregarían"), ("paginas_faltantes", "Páginas que se quitarían")):
            if res[clave]:
                self.stdout.write(f"{titulo}: " + ", ".join("/" + r for r in res[clave]))
        for ruta, d in res["texto"].items():
            self.stdout.write(f"\n/{ruta}: {len(d)} renglones distintos (- publicado, + administrador)")
            self.stdout.write("\n".join("  " + x[:200] for x in d[:60]))
        if archivos:
            for clave, titulo in (("archivos_nuevos", "Archivos que se agregarían"), ("archivos_faltantes", "Archivos que se quitarían")):
                if res[clave]:
                    self.stdout.write(f"\n{titulo} ({len(res[clave])}):\n  " + "\n  ".join(res[clave][:80]))
        if sin_diferencias(res):
            self.stdout.write(self.style.SUCCESS(f"{s.nombre}: el texto de todas las páginas coincide con {referencia}"))
        else:
            raise SystemExit(1)
