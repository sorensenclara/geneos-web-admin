"""Actualiza una base ya inicializada con los datos de precios publicados (octubre 2026):

- Leyenda de vigencia de GERP y GEMA, copiada de sus páginas actuales. GEAGRO queda sin leyenda.
- Preguntas frecuentes: los importes escritos pasan a ser referencias al plan ([precio:clave], [implementacion:clave]).
- GEMA: la respuesta que mencionaba «30 dólares oficiales» usa el precio vigente del plan.

En una base nueva no hace nada distinto de lo que ya carga `manage.py inicializar`.
"""
import re

from django.db import migrations

VIGENCIA = {
    "gerp": "Los valores informados son precios vigentes hasta diciembre 2026",
    "gema": "Precios válidos para Octubre, Noviembre y Diciembre. Actualización bimestral.",
}
RESPUESTA_GEMA = ("<p>El pago es mensual: el abono es de [precio:mensual] por mes e incluye actualizaciones "
                  "y soporte técnico sin costo adicional.</p>")


def adelante(apps, schema_editor):
    Plan = apps.get_model("contenidos", "Plan")
    Faq = apps.get_model("contenidos", "PreguntaFrecuente")
    for clave, texto in VIGENCIA.items():
        Plan.objects.filter(sitio__clave=clave, leyenda_vigencia="").update(leyenda_vigencia=texto)
    Plan.objects.filter(sitio__clave__in=["geagro", "gema"]).update(vigente_hasta=None)  # sin fecha publicada: no se inventa
    for sitio_id in Faq.objects.values_list("sitio_id", flat=True).distinct():
        planes = list(Plan.objects.filter(sitio_id=sitio_id))
        for f in Faq.objects.filter(sitio_id=sitio_id):
            r = f.respuesta
            if "dólares" in r or "dolares" in r:
                r = RESPUESTA_GEMA
            # Primero las implementaciones (pueden coincidir con el abono de otro plan), con «+ IVA» incluido en la referencia
            for campo, token in (("implementacion", "implementacion"), ("precio", "precio")):
                for p in planes:
                    valor = getattr(p, campo)
                    if valor and re.search(rf"\$\s?{re.escape(valor)}", r):
                        r = re.sub(rf"\$\s?{re.escape(valor)}(?:\s\+\s?IVA)?", f"[{token}:{p.clave}]", r)
            # Referencias de la versión anterior ($[precio:lite] + IVA): ahora la referencia ya incluye moneda e IVA
            r = re.sub(r"\$\[(precio|implementacion):([^\]]+)\](?:\s\+\s?IVA)?", r"[\1:\2]", r)
            if r != f.respuesta:
                f.respuesta = r
                f.save(update_fields=["respuesta"])


class Migration(migrations.Migration):
    dependencies = [("contenidos", "0003_precios_fuente_unica"), ("sitios", "0002_precios_fuente_unica")]
    operations = [migrations.RunPython(adelante, migrations.RunPython.noop)]
