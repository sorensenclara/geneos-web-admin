from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contenidos", "0017_contenido_por_seccion_geneos"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="titulo_caracteristicas",
            field=models.CharField(blank=True, help_text="Encabezado de la lista en la tarjeta (GEMA), por ejemplo «Funciones incluidas» o «Todo lo de Básico, más». Vacío: sin título.", max_length=80, verbose_name="Título de las características"),
        ),
    ]
