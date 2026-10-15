"""Crea la identidad visual (vacía) de cada sitio y la suma al flujo de aprobación existente."""
from django.db import migrations


def adelante(apps, schema_editor):
    SitioWeb = apps.get_model("sitios", "SitioWeb")
    Identidad = apps.get_model("contenidos", "IdentidadSitio")
    for s in SitioWeb.objects.all():
        Identidad.objects.get_or_create(sitio=s, defaults={"live": True})
    ContentType = apps.get_model("contenttypes", "ContentType")
    Workflow = apps.get_model("wagtailcore", "Workflow")
    WorkflowContentType = apps.get_model("wagtailcore", "WorkflowContentType")
    wf = Workflow.objects.filter(active=True).first()
    if wf:
        ct, _ = ContentType.objects.get_or_create(app_label="contenidos", model="identidadsitio")
        WorkflowContentType.objects.get_or_create(content_type=ct, defaults={"workflow": wf})


class Migration(migrations.Migration):
    dependencies = [("contenidos", "0006_identidad_visual"), ("wagtailcore", "0083_workflowcontenttype"), ("contenttypes", "0002_remove_content_type_name")]
    operations = [migrations.RunPython(adelante, migrations.RunPython.noop)]
