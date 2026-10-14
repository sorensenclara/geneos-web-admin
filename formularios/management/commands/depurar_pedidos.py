"""Protección de datos: borra los pedidos de demo cerrados o descartados más antiguos que N meses."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from formularios.models import SolicitudDemo


class Command(BaseCommand):
    help = "Borra pedidos de demo cerrados o descartados con más de N meses (por defecto 24)."

    def add_arguments(self, parser):
        parser.add_argument("--meses", type=int, default=24)

    def handle(self, meses, **kwargs):
        limite = timezone.now() - timedelta(days=30 * meses)
        n, _ = SolicitudDemo.objects.filter(estado__in=["cerrado", "descartado"], actualizado__lt=limite).delete()
        self.stdout.write(f"Pedidos borrados: {n}")
