"""Lee las fuentes de «Actualidad e ideas para publicar» (lo mismo que «Actualizar ahora», sin esperar al navegador).

    python manage.py actualizar_actualidad              # solo si pasaron más de 24 horas desde la última lectura
    python manage.py actualizar_actualidad --forzar     # ahora
    python manage.py actualizar_actualidad --forzar --producto gema
    python manage.py actualizar_actualidad --forzar --fuente gerp-gdelt

Pensado también para una tarea programada futura (cron del servidor): no hace falta cambiar código.
"""
from django.core.management.base import BaseCommand

from editorial import lector
from editorial.catalogo import sembrar
from editorial.models import FuenteActualidad


class Command(BaseCommand):
    help = "Lee las fuentes de actualidad (RSS, GDELT, YouTube) y registra qué funciona y qué falla."

    def add_arguments(self, parser):
        parser.add_argument("--forzar", action="store_true", help="Leer aunque no hayan pasado 24 horas.")
        parser.add_argument("--producto", choices=["geneos", "gerp", "geagro", "gema"])
        parser.add_argument("--fuente", action="append", help="Clave de una fuente (se puede repetir).")
        parser.add_argument("--catalogo", action="store_true", help="Vuelve a cargar el catálogo (agrega fuentes y eventos nuevos).")

    def handle(self, *args, **o):
        if o["catalogo"]:
            sembrar()
        if not o["forzar"] and not lector.necesita_actualizar():
            self.stdout.write("La última lectura tiene menos de 24 horas. Usá --forzar para leer ahora.")
            return
        claves = o["fuente"]
        if o["producto"]:
            claves = list(FuenteActualidad.objects.filter(producto__in=[o["producto"], "todos"]).values_list("clave", flat=True))
        act = lector.actualizar_fuentes("comando", claves=claves)
        if act is None:
            self.stdout.write(self.style.WARNING("Ya hay una lectura en curso."))
            return
        for f in FuenteActualidad.objects.filter(clave__in=list(act.detalle)).order_by("producto", "orden"):
            r = act.detalle[f.clave]
            marca = self.style.SUCCESS("OK   ") if r["ok"] else self.style.ERROR("FALLA")
            extra = f"{r.get('leidos', 0)} leídas, {r.get('relevantes', 0)} relacionadas, {r.get('nuevos', 0)} nuevas" if r["ok"] else r.get("motivo", "")
            self.stdout.write(f"{marca} {f.producto:7} {f.nombre[:48]:48} {extra}")
        if not lector.youtube_configurado():
            self.stdout.write("YouTube: sin clave (YOUTUBE_API_KEY); sus canales no se consultaron.")
        self.stdout.write(f"Resultado: {act.estado} · {act.fuentes_ok} bien · {act.fuentes_error} con problemas · {act.nuevos} novedades.")
