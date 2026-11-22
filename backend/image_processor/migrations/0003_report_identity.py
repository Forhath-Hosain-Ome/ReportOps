from django.db import migrations, models
from django.db.models import Count


def require_unique_reports(apps, schema_editor):
    # Keep writers out between the preflight and constraint creation on PostgreSQL.
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute('LOCK TABLE "image_processor_folderreport" IN SHARE ROW EXCLUSIVE MODE')
    Report = apps.get_model("image_processor", "FolderReport")
    duplicates = Report.objects.using(schema_editor.connection.alias).values("batch_id", "folder_name").annotate(
        count=Count("pk")).filter(count__gt=1)
    if duplicates.exists():
        raise RuntimeError("Duplicate Image Processor report identities exist. A reviewed reconciliation migration is required; no data was rewritten.")


class Migration(migrations.Migration):
    dependencies = [("image_processor", "0002_reliability")]
    operations = [
        migrations.RunPython(require_unique_reports, migrations.RunPython.noop),
        migrations.AddConstraint(model_name="folderreport", constraint=models.UniqueConstraint(
            fields=("batch", "folder_name"), name="image_report_identity")),
    ]
