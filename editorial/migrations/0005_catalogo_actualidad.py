"""Catálogo inicial de fuentes (en prueba: no muestran nada hasta verificarse) y agenda de eventos.
Las tarjetas de ejemplo de la etapa anterior quedan descartadas (no son datos reales)."""
from datetime import datetime, timezone as tz

from django.db import migrations


def sembrar(apps, schema_editor):
    from editorial.catalogo import sembrar as cargar
    Idea = apps.get_model("editorial", "IdeaEditorial")
    for tipo, nat in (("idea", "idea"), ("tendencia", "tendencia"), ("noticia", "periodistica"), ("evento", "evento")):
        Idea.objects.filter(tipo=tipo, naturaleza="").update(naturaleza=nat)
    Idea.objects.filter(titulo__icontains="(Ejemplo)").update(estado="descartada")
    cargar(apps.get_model("editorial", "FuenteActualidad"), Idea, apps.get_model("sitios", "SitioWeb"), apps.get_model("sitios", "LineaProducto"))
    apps.get_model("editorial", "CerrojoActualidad").objects.get_or_create(pk=1, defaults={"hasta": datetime(2000, 1, 1, tzinfo=tz.utc)})


class Migration(migrations.Migration):
    dependencies = [("editorial", "0004_lectura_automatica"), ("sitios", "0003_colores_oficiales")]
    operations = [migrations.RunPython(sembrar, migrations.RunPython.noop)]
