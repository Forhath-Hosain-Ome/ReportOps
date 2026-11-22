"""
------------------------------------------------------------------
Single source of truth for which Excel template backs each
(report_type, stage) combination in the Final Summary export.

Two independent axes
---------------------
  report_type  defect-column family  — BuyerFactoryPair.report_type
               KNIT_35 / WOVEN_37 / SWEATER_37 / WOVEN_78
  stage        inspection stage      — AvailableReport
               FINAL / RE_FINAL / RANDOM / INLINE / SAMPLE / CMF

Templates live in media/templates/final_summary/. Each file has
exactly ONE data sheet, named after its stage (Final-37.xlsx →
sheet "Final", SPI-Random-78.xlsx → sheet "Random", etc).

To onboard a new format: drop the .xlsx in that folder and add one
line to TEMPLATE_REGISTRY. Nothing else in the export pipeline needs
to change — no code touches column numbers; those are resolved from
each template's own header row at export time (see utils/summary_writer.py).

Run `python manage.py check_export_templates` after editing this file
to verify every configured entry exists on disk and print the full
coverage matrix.
------------------------------------------------------------------
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

from django.conf import settings

TEMPLATE_DIR = Path(settings.TEMPLATE_ROOT) / "final_summary"

# Sheet name inside each template file, keyed by canonical stage.
SHEET_NAME_MAP: Dict[str, str] = {
    "FINAL":    "Final",
    "RE_FINAL": "Re-Final",
    "RANDOM":   "Random",
    "INLINE":   "INLINE",
    "SAMPLE":   "Sample",   # no template built yet — safe to leave mapped
    "CMF":      "CMF",      # no template built yet — safe to leave mapped
}

# Sheets appear in the merged output workbook in this order, regardless
# of what order records came back from the DB.
STAGE_ORDER = ["FINAL", "RE_FINAL", "RANDOM", "INLINE", "SAMPLE", "CMF"]

# (report_type, stage) -> filename in TEMPLATE_DIR.
# None = deliberately not built yet. resolve_template() raises a clear,
# actionable error instead of silently falling back to some other file.
TEMPLATE_REGISTRY: Dict[Tuple[str, str], Optional[str]] = {
    # ---- KNIT_35 --------------------------------------------------------
    # NOTE: extraction already treats this as a 31-item template
    # (see final_summary/extraction/core/defect_master.py TEMPLATE_31).
    # No export template exists for this family yet.
    ("KNIT_35",    "FINAL"):    None,
    ("KNIT_35",    "RE_FINAL"): None,
    ("KNIT_35",    "RANDOM"):   None,
    ("KNIT_35",    "INLINE"):   None,

    # ---- WOVEN_37 / SWEATER_37 (shared "General 37" family) -------------
    ("WOVEN_37",   "FINAL"):    "Final-37.xlsx",
    ("WOVEN_37",   "RE_FINAL"): "Re-Final-37.xlsx",
    ("WOVEN_37",   "RANDOM"):   None,
    ("WOVEN_37",   "INLINE"):   None,

    ("SWEATER_37", "FINAL"):    "Final-37.xlsx",
    ("SWEATER_37", "RE_FINAL"): "Re-Final-37.xlsx",
    ("SWEATER_37", "RANDOM"):   None,
    ("SWEATER_37", "INLINE"):   None,

    # ---- WOVEN_78 (SPI family) -------------------------------------------
    ("WOVEN_78",   "FINAL"):    "SPI-Final-78.xlsx",
    ("WOVEN_78",   "RE_FINAL"): "SPI-Re-Final-78.xlsx",
    ("WOVEN_78",   "RANDOM"):   "SPI-Random-78.xlsx",
    ("WOVEN_78",   "INLINE"):   "In-Line-78.xlsx",
}


class TemplateNotConfiguredError(Exception):
    """(report_type, stage) has no template mapped, or the mapped file
    is missing from disk. Carries enough detail for the API layer to
    report exactly what's missing."""

    def __init__(self, report_type: str, stage: str, reason: str) -> None:
        self.report_type = report_type
        self.stage = stage
        self.reason = reason
        super().__init__(
            f"No export template for report_type={report_type!r} "
            f"stage={stage!r}: {reason}"
        )


def resolve_template(report_type: str, stage: str) -> Path:
    """Return the on-disk Path for (report_type, stage).

    Raises TemplateNotConfiguredError if the combination isn't in the
    registry, or the mapped file is missing on disk.
    """
    filename = TEMPLATE_REGISTRY.get((report_type, stage))
    if filename is None:
        raise TemplateNotConfiguredError(
            report_type, stage,
            "not yet configured — add the .xlsx to "
            f"{TEMPLATE_DIR} and add a row to TEMPLATE_REGISTRY",
        )
    path = TEMPLATE_DIR / filename
    if not path.exists():
        raise TemplateNotConfiguredError(
            report_type, stage,
            f"registry points at '{filename}' but it's missing from {TEMPLATE_DIR}",
        )
    return path
