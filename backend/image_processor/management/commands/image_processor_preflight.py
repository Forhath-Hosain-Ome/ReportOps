"""Read-only physical schema evidence; never adopts or fakes migrations."""
import json
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.db.models import Count
from django.db.migrations.recorder import MigrationRecorder
from image_processor.models import FolderReport


class Command(BaseCommand):
    help = "Inspect Image Processor physical schema, migration history and duplicate report identities without changing data."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default")

    def handle(self, *args, **options):
        alias = options["database"]
        connection = connections[alias]
        with transaction.atomic(using=alias):
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
            evidence = {"database_vendor": connection.vendor, "tables": {}, "applied_migrations": [], "duplicate_identities": None}
            with connection.cursor() as cursor:
                tables = connection.introspection.table_names(cursor)
                for table in sorted(name for name in tables if name.startswith("image_processor_")):
                    fields = connection.introspection.get_table_description(cursor, table)
                    evidence["tables"][table] = {
                        "fields": [{"name": field.name, "type": connection.introspection.get_field_type(field.type_code, field),
                                    "nullable": field.null_ok, "default": field.default} for field in fields],
                        "constraints": connection.introspection.get_constraints(cursor, table),
                    }
            if "django_migrations" in tables:
                evidence["applied_migrations"] = list(MigrationRecorder.Migration.objects.using(alias).filter(
                    app="image_processor").values("name", "applied"))
            if "image_processor_folderreport" in tables:
                evidence["duplicate_identities"] = FolderReport.objects.using(alias).values(
                    "batch_id", "folder_name").annotate(count=Count("pk")).filter(count__gt=1).count()
        self.stdout.write(json.dumps(evidence, indent=2, default=str))
        if evidence["duplicate_identities"]:
            raise CommandError("Report identity duplicates require a reviewed reconciliation migration. Nothing was changed.")
