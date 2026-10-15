from django.db import migrations


def flujo(apps, schema_editor):
    """La configuración del blog sigue el mismo flujo de aprobación que los demás contenidos."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Workflow = apps.get_model("wagtailcore", "Workflow")
    WorkflowContentType = apps.get_model("wagtailcore", "WorkflowContentType")
    wf = Workflow.objects.filter(active=True).first()
    if wf:
        ct, _ = ContentType.objects.get_or_create(app_label="editorial", model="configblog")
        WorkflowContentType.objects.get_or_create(content_type=ct, defaults={"workflow": wf})


class Migration(migrations.Migration):
    dependencies = [("editorial", "0001_initial"), ("wagtailcore", "0083_workflowcontenttype")]
    operations = [migrations.RunPython(flujo, migrations.RunPython.noop)]
