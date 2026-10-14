"""Ajustes aprobados (octubre 2026):

- GEMA: leyenda «Precios válidos para octubre, noviembre y diciembre. Actualización trimestral.» (sigue editable).
- GERP: la fila del comparador se llama «Facturación electrónica ARCA (AFIP)» y se muestra aunque sus celdas estén vacías.
"""
from django.db import migrations

VIEJA = "Precios válidos para Octubre, Noviembre y Diciembre. Actualización bimestral."
NUEVA = "Precios válidos para octubre, noviembre y diciembre. Actualización trimestral."


def adelante(apps, schema_editor):
    Plan = apps.get_model("contenidos", "Plan")
    Funcionalidad = apps.get_model("contenidos", "Funcionalidad")
    Plan.objects.filter(sitio__clave="gema", leyenda_vigencia__in=["", VIEJA]).update(leyenda_vigencia=NUEVA)
    Funcionalidad.objects.filter(sitio__clave="gerp", etiqueta="Facturación electrónica ARCA (ex AFIP)").update(
        etiqueta="Facturación electrónica ARCA (AFIP)")


class Migration(migrations.Migration):
    dependencies = [("contenidos", "0004_precios_datos_publicados")]
    operations = [migrations.RunPython(adelante, migrations.RunPython.noop)]
