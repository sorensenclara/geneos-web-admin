from django.db import migrations, models

# Colores de los isologos oficiales (sitios/marca.py). Antes GEMA figuraba en rojo.
OFICIALES = {"geneos": "#128237", "gerp": "#1b4b8c", "geagro": "#0e8337", "gema": "#ec6c05"}


def adelante(apps, schema_editor):
    SitioWeb = apps.get_model("sitios", "SitioWeb")
    for clave, color in OFICIALES.items():
        SitioWeb.objects.filter(clave=clave).update(color=color)


class Migration(migrations.Migration):
    dependencies = [("sitios", "0002_precios_fuente_unica")]
    operations = [
        migrations.AlterField("sitioweb", "color", models.CharField(
            "Color del sitio", max_length=7, default="#128237",
            help_text="En GENEOS, GERP, GEAGRO y GEMA el administrador usa el color de su isologo oficial.")),
        migrations.RunPython(adelante, migrations.RunPython.noop),
    ]
