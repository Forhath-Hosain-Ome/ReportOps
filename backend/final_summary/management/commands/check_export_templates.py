"""
python manage.py check_export_templates

Prints the full (report_type x stage) template coverage matrix and
exits non-zero if any *configured* entry points at a missing file.
Entries that are simply not configured (None) are shown as gaps, not
errors — that's an intentional "not built yet" state.

Run this after editing final_summary/templates_registry.py or after
deploying new template files, to catch a typo'd filename or a missing
copy in media/templates/final_summary/ before a factory export fails
at request time.
"""
from django.core.management.base import BaseCommand

from final_summary.models.buyer_factory_pair import ReportType, AvailableReport
from final_summary.templates_registry import TEMPLATE_DIR, TEMPLATE_REGISTRY


class Command(BaseCommand):
    help = "Print the export template coverage matrix (report_type x stage)."

    def handle(self, *args, **options):
        report_types = [c.value for c in ReportType]
        stages       = [c.value for c in AvailableReport]

        self.stdout.write(f"Template directory: {TEMPLATE_DIR}\n")

        col_width = max(len(rt) for rt in report_types) + 2
        header = " " * col_width + "".join(f"{s:<12}" for s in stages)
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        missing_files = []
        for rt in report_types:
            row = f"{rt:<{col_width}}"
            for stage in stages:
                filename = TEMPLATE_REGISTRY.get((rt, stage))
                if filename is None:
                    mark = "—"
                elif (TEMPLATE_DIR / filename).exists():
                    mark = "OK"
                else:
                    mark = "MISSING"
                    missing_files.append((rt, stage, filename))
                row += f"{mark:<12}"
            self.stdout.write(row)

        self.stdout.write("")
        self.stdout.write("OK = template configured and file present")
        self.stdout.write("—  = not configured (expected gap, not an error)")
        self.stdout.write("MISSING = configured but file not found on disk (real problem)")

        if missing_files:
            self.stdout.write("")
            self.stderr.write(self.style.ERROR("Missing template files:"))
            for rt, stage, filename in missing_files:
                self.stderr.write(f"  ({rt}, {stage}) -> {filename}")
            raise SystemExit(1)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("All configured templates found on disk."))
