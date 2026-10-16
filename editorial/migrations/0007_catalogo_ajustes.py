"""Ajustes después de la primera lectura real: fuentes nuevas para GEMA y GENEOS, Infocampo general y Los Andes Cuyo Agro
descartadas (duplicaban o no responden), idioma de las fuentes en inglés y clasificación de errores (técnico o de calidad).
Google Trends vuelve a prueba si no tuvo ninguna búsqueda relacionada (no debió verificarse)."""
from django.db import migrations


def ajustar(apps, schema_editor):
    from editorial.catalogo import sembrar
    Fuente = apps.get_model("editorial", "FuenteActualidad")
    sembrar(Fuente, apps.get_model("editorial", "IdeaEditorial"), apps.get_model("sitios", "SitioWeb"), apps.get_model("sitios", "LineaProducto"))
    for f in Fuente.objects.exclude(ultimo_error=""):
        f.tipo_error = "calidad" if f.items_leidos else "tecnico"
        f.save(update_fields=["tipo_error"])
    t = Fuente.objects.filter(clave="todos-trends", items_relevantes=0).first()
    if t and not apps.get_model("editorial", "IdeaEditorial").objects.filter(fuente_actualidad=t).exists():
        t.estado, t.verificada, t.tipo_error = "prueba", None, "calidad"
        t.motivo = "No pasó: ninguna de las búsquedas del día se relacionó con los productos."
        t.save()


class Migration(migrations.Migration):
    dependencies = [("editorial", "0006_ajustes_lectura")]
    operations = [migrations.RunPython(ajustar, migrations.RunPython.noop)]
