"""
---------------------
GET /api/final-summary/export/

Generates and streams a filled Excel summary workbook. One sheet is
produced per inspection stage (Final, Re-Final, Random, Inline, ...)
actually present in the matched records — a factory that only ran
Inline and Re-Final inspections in the date range gets a 2-sheet file.
Template selection per (report_type, stage) is entirely owned by
final_summary/templates_registry.py; this view never touches a
template filename directly.

Query parameters
----------------
Required:
  factory    exact factory name
  client     exact client/buyer name
  date_from  YYYY-MM-DD
  date_to    YYYY-MM-DD

Optional:
  style      comma-separated partial matches on style_no (OR logic)
  po         comma-separated partial matches on po_no    (OR logic)

Filter logic
------------
  (factory AND client AND date_range)
  AND (style_1 OR style_2 OR ... OR po_1 OR po_2 OR ...)

Error responses (JSON)
----------------------
  400  missing required params
  404  no records found
  409  report_type mismatch between records (e.g. KNIT_35 mixed with WOVEN_37)
  422  defect item(s) have no matching template column, in any stage
  424  none of the present stages have a configured template yet
  500  server / generation error
"""

import logging
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.http import FileResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from final_summary.models import AuditReport, DefectEntry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Param helpers
# ---------------------------------------------------------------------------

def _parse_csv(value: str) -> list[str]:
    """'A001, B002' → ['A001', 'B002']"""
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _style_po_filter(styles: list[str], pos: list[str]) -> Q | None:
    """(style_A OR style_B OR po_X OR po_Y)"""
    if not styles and not pos:
        return None
    q = Q()
    for s in styles:
        q |= Q(style_no__icontains=s)
    for p in pos:
        q |= Q(po_no__icontains=p)
    return q


def _detect_format_mismatch(
    records: list[dict],
) -> tuple[str | None, list[dict]]:
    """Return (dominant_format, mismatched_records)."""
    if not records:
        return None, []
    from collections import Counter
    counts   = Counter(r["_report_type"] for r in records)
    dominant = counts.most_common(1)[0][0]
    mismatch = [r for r in records if r["_report_type"] != dominant]
    return dominant, mismatch


def _build_writer_data(
    reports,
) -> tuple[list[dict], dict[int, list[dict]]]:
    """Build records list + defect_map for summary_writer."""
    ids = [r.pk for r in reports]
 
    defect_map: dict[int, list[dict]] = {}
    for de in (
        DefectEntry.objects
        .filter(report_id__in=ids)
        .order_by("category", "defect_name")
    ):
        # Parse combined "category" ("CODE - LABEL") into parts
        cat_raw = (de.category or "").strip()
        if " - " in cat_raw:
            code, label = cat_raw.split(" - ", 1)
            code  = code.strip()
            label = label.strip()
        else:
            code  = cat_raw
            label = cat_raw

        defect_map.setdefault(de.report_id, []).append({
            "audit_report_id": de.report_id,
            "category":        de.category,
            "item":            de.defect_name,
            "major_count":     de.major,
            "minor_count":     de.minor,
            "comment":         de.comment,
        })

    records = []
    for r in reports:
        records.append({
            "report_id":             r.pk,
            "file_name":             r.file_name,
            "factory":               r.factory,
            "client":                r.client,
            "style_no":              r.style_no,
            "item_name":             r.item_name,
            "country":               r.country,
            "po_no":                 r.po_no,
            "inspection_type":       r.inspection_type,
            "date_of_issue":         str(r.date_of_issue) if r.date_of_issue else "",
            "audit_result":          r.audit_result,
            "ship_qty":              r.ship_qty,
            "audit_qty":             r.audit_qty,
            "defect_qty":            r.defect_qty,
            "defect_percentage":     r.defect_percentage,
            "inspector":             r.inspector,
            "person":                r.person,
            "po_qty_pcs":            r.po_qty_pcs,
            "po_qty_pack":           r.po_qty_pack,
            "po_qty_set":            r.po_qty_set,
            "po_wh":                 str(r.po_wh)    if r.po_wh    else "",
            "exf":                   str(r.exf)      if r.exf      else "",
            "po_edt":                str(r.po_edt)   if r.po_edt   else "",
            "plan_edt":              str(r.plan_edt) if r.plan_edt else "",
            "plan_wh":               str(r.plan_wh)  if r.plan_wh  else "",
            "factory_in":            r.factory_in_time,
            "factory_out":           r.factory_out_time,
            "factory_total_hours":   r.factory_total_hours,
            "audit_start":           r.audit_start_time,
            "audit_end":             r.audit_end_time,
            "audit_total_hours":     r.audit_total_hours,
            "acceptable_defect_qty": r.acceptable_defect_qty,
            # Internal — for mismatch detection only, stripped before writer
            "_report_type": r.batch.pair.report_type,
        })

    return records, defect_map


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

class AuditExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # ── 1. Params ─────────────────────────────────────────────────────
        factory   = request.query_params.get("factory",   "").strip()
        client    = request.query_params.get("client",    "").strip()
        date_from = request.query_params.get("date_from", "").strip()
        date_to   = request.query_params.get("date_to",   "").strip()
        styles    = _parse_csv(request.query_params.get("style", ""))
        pos       = _parse_csv(request.query_params.get("po",    ""))

        missing = [
            k for k, v in [
                ("factory", factory), ("client", client),
                ("date_from", date_from), ("date_to", date_to),
            ] if not v
        ]
        if missing:
            return Response(
                {"detail": f"Required parameters missing: {', '.join(missing)}"},
                status=400,
            )

        # ── 2. Query ──────────────────────────────────────────────────────
        try:
            qs = (
                AuditReport.objects
                .select_related("batch", "batch__pair", "batch__pair__buyer",
                                "batch__pair__factory")
                .filter(
                    factory__iexact=factory,
                    client__iexact=client,
                    date_of_issue__gte=date_from,
                    date_of_issue__lte=date_to,
                )
                .order_by("date_of_issue", "style_no")
            )

            sp = _style_po_filter(styles, pos)
            if sp is not None:
                qs = qs.filter(sp)

            reports = list(qs)
        except Exception as exc:
            logger.exception("Export query failed: %s", exc)
            return Response({"detail": "Query failed."}, status=500)

        if not reports:
            return Response(
                {"detail": "No records found for the given filters."},
                status=404,
            )

        # ── 3. Build writer data ──────────────────────────────────────────
        records, defect_map = _build_writer_data(reports)

        # ── 4. report_type mismatch check ───────────────────────────────────
        dominant_report_type, mismatched = _detect_format_mismatch(records)

        if mismatched:
            return Response(
                {
                    "detail": (
                        f"report_type mismatch: dominant='{dominant_report_type}' "
                        f"but {len(mismatched)} record(s) differ. "
                        f"Fix or skip via the Retry flow before exporting."
                    ),
                    "dominant_report_type": dominant_report_type,
                    "mismatch_count":       len(mismatched),
                    "mismatched_records": [
                        {
                            "file_name":   r["file_name"],
                            "report_type": r["_report_type"],
                            "expected":    dominant_report_type,
                        }
                        for r in mismatched
                    ],
                },
                status=409,
            )

        # Strip internal key
        for r in records:
            r.pop("_report_type", None)

        # ── 5. Generate Excel ────────────────────────────────────────────
        # One sheet per stage (Final, Re-Final, Random, Inline, ...) that
        # is actually present in `records` — template resolution for each
        # (dominant_report_type, stage) pair happens inside write_summary
        # via final_summary/templates_registry.py.
        output_dir = Path(settings.BASE_DIR) / "media" / "output" / "final_summary"
        output_dir.mkdir(parents=True, exist_ok=True)

        ts       = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = (
            f"audit_summary_"
            f"{factory.replace(' ', '_')}_"
            f"{client.replace(' ', '_')}_"
            f"{ts}.xlsx"
        )
        output_path = output_dir / filename

        try:
            from utils.summary_writer import write_summary, DefectMismatchError
            from final_summary.templates_registry import TemplateNotConfiguredError

            result = write_summary(
                records=records,
                defect_items_by_report=defect_map,
                output_path=output_path,
                report_type=dominant_report_type,
            )

        except DefectMismatchError as exc:
            logger.warning(
                "Defect mismatch on export: %d item(s) unmatched",
                len(exc.mismatches),
            )
            return Response(
                {
                    "detail": (
                        f"{len(exc.mismatches)} defect item(s) have no matching "
                        f"column in their stage's template. These items must "
                        f"exist in the template header row."
                    ),
                    "mismatch_count":     len(exc.mismatches),
                    "mismatched_defects": exc.mismatches,
                },
                status=422,
            )

        except TemplateNotConfiguredError as exc:
            logger.warning(
                "No usable template for export: report_type=%s stage=%s (%s)",
                exc.report_type, exc.stage, exc.reason,
            )
            return Response(
                {
                    "detail": (
                        f"No export template configured for report_type="
                        f"'{exc.report_type}' stage='{exc.stage}'. {exc.reason}"
                    ),
                    "report_type": exc.report_type,
                    "stage":       exc.stage,
                },
                status=424,
            )

        except (FileNotFoundError, ValueError) as exc:
            logger.error("Export error: %s", exc)
            return Response({"detail": str(exc)}, status=500)

        except Exception as exc:
            logger.exception("Summary generation failed: %s", exc)
            return Response(
                {"detail": f"Could not generate Excel file: {exc}"},
                status=500,
            )

        # ── 6. Stream ─────────────────────────────────────────────────────
        logger.info(
            "Export OK: factory=%r client=%r %s→%s report_type=%s "
            "stages_written=%s stages_skipped=%s records=%d",
            factory, client, date_from, date_to, dominant_report_type,
            result["stages_written"], [s["stage"] for s in result["stages_skipped"]],
            len(records),
        )
        response = FileResponse(
            open(output_path, "rb"),
            as_attachment=True,
            filename=filename,
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
        )
        if result["stages_skipped"]:
            # Surface partial-export info without failing the download —
            # some stages had records but no template yet.
            response["X-Skipped-Stages"] = ",".join(
                s["stage"] for s in result["stages_skipped"]
            )
        return response