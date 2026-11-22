"""Read-only report projection of retained, hash-verified source workbooks.

No persistence or workbook generation occurs here. Completed jobs retain inputs
under the same retention policy as their output; missing authority fails closed.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from .parser import parse_inspection_workbook, ratio, total
from .report_data import dashboard_scope, detail_values, manpower, ranked_groups, raw_columns, defect_indices, field_value, available_sections, report_sheets
from .services import validated_inputs
from .template_writer import dashboard_values, detail_spec, detail_rows


def value(item):
    if isinstance(item, (date, datetime, time)):
        return item.isoformat()
    if isinstance(item, timedelta):
        return str(item)
    if isinstance(item, Decimal):
        return float(item)
    return item


def top_groups(block, denominator):
    if block is None or block.empty_state:
        return []
    return [{"rank": rank, "quantity": qty, "ratio": ratio(qty, denominator),
             "defects": [{"category": d.category, "label": d.label, "ordinal":d.ordinal or block.defect_schema.index(d)+1,"occurrence":d.occurrence,"source_number":d.source_number} for d in defects]}
            for rank, (qty, defects) in enumerate(ranked_groups(block), 1)]


def block_preview(block, index, mode):
    result = {"id": f"block-{index}", "report_type": block.report_name,
              "title": block.report_name, "kind": block.kind, "empty": block.empty_state,
              "source_position": block.source_index, "factory_names": block.factories,
              "date_start": block.date_start, "date_end": block.date_end,
              "inspection_days": block.inspection_days,
              "count": len(block.styles) if block.kind == "raw" else block.inspection_count,
              "count_kind": "style" if block.kind == "raw" else "audit",
              "shipment_qty": block.shipment_qty, "inspected_qty": block.inspected_qty,
              "pass_qty": block.pass_qty, "defect_qty": block.defect_qty,
              "defect_ratio": block.defect_ratio, "items": block.items, "team_leader": None,
              "top_defects": top_groups(block, block.inspected_qty if mode == "analysis" else block.defect_qty)}
    if mode == "analysis" and block.kind == "raw":
        result["manpower"] = {"days": block.inspection_days, "aggregate_persons": None,
                              "entries": [{"date": day, "values": values} for day, values in manpower(block)]}
    return result


def dashboard_preview(blocks):
    styles, final, raw = dashboard_scope(blocks)
    # The canonical dashboard adapter owns equivalent-finding calculations.
    # Coordinates stay private to the adapter and never cross the API boundary.
    cells, _ = dashboard_values(blocks)
    available = final is not None
    def team(block):
        return {"duration_days": block.inspection_days if block and available else None,
                "inspected_qty": block.inspected_qty if block and available else None,
                "defect_qty": block.defect_qty if block and available else None,
                "defect_ratio": block.defect_ratio if block and available else None,
                "top_defects": top_groups(block, block.inspected_qty) if block and available else []}
    return {"matched_styles": styles, "matched_style_count": len(styles), "final_available": available,
            "team_100": {**team(raw), "style_count": len(styles) if available else None,
                         "passed_qty": raw.pass_qty if available else None},
            "final": {**team(final), "audit_count": final.inspection_count if final else None,
                      "shipment_qty": final.shipment_qty if final else None},
            "comparison": {"ratio_reduction": None, "inspection_factor": cells.get("T26"),
                           "equivalent_findings": cells.get("T29"),
                           "equivalent_calculation": cells.get("T28")}}


def detail_preview(raw):
    spec=detail_spec(raw);definitions={d.column-1:d for d in raw.defect_schema}
    columns=[]
    for position,index in enumerate(spec):
        defect=definitions.get(index)
        columns.append({'key':f'field-{position}','label':raw.raw_headers[index] if index is not None else '',
                        'group':defect.category if defect else 'Inspection','category':defect.category if defect else None,
                        'kind':'defect' if defect else 'metadata','number':defect.ordinal if defect else None,
                        'ordinal':defect.ordinal if defect else None,'occurrence':defect.occurrence if defect else None,
                        'source_number':defect.source_number if defect else None})
    columns[0]['label'],columns[1]['label'],columns[2]['label']='Inspection Date','Factory Name','Style No'
    rows=[{'kind':kind,'values':{c['key']:value(v) for c,v in zip(columns,cells)}} for kind,cells in detail_rows(raw)]
    return {'columns':columns,'rows':rows,'record_count':raw.inspection_count}


def reconciliation_preview(raw):
    fields = raw_columns(raw)
    details = raw.raw_rows
    category_total = sum(sum(row[i] for i in defect_indices(raw)) for row in details)
    checks = {"inspection_matches_detail": total([r[fields["inspected"]] for r in details]) == raw.inspected_qty,
              "pass_matches_detail": total([field_value(r,fields,"pass") for r in details]) == raw.pass_qty,
              "defect_matches_categories": category_total == raw.defect_qty,
              "record_count_valid": len(details) == raw.inspection_count}
    return {"inspection_qty": raw.inspected_qty, "pass_qty": raw.pass_qty,
            "defect_qty": raw.defect_qty, "defect_category_total": category_total,
            "record_count": raw.inspection_count, "inspection_day_count": raw.inspection_days,
            "style_count": len(raw.styles), "defect_field_count":len(raw.defect_schema),
            "defect_category_count":len({d.category for d in raw.defect_schema}), "hundred_percent_format":raw.format, "status": "passed" if all(checks.values()) else "failed", **checks}


def build_preview(job):
    blocks = parse_inspection_workbook(*validated_inputs(job))
    raw = next((b for b in blocks if b.kind == "raw"),None)
    reconciliation = reconciliation_preview(raw) if raw else None
    available=available_sections(blocks)
    return {"available_sections":available,
            "sources":{"inspection_summary":any(b.kind=="ordinary" for b in blocks),"hundred_percent":raw is not None,"hundred_percent_format":raw.format if raw else None},
            "overview": {"blocks": [{"id": f"block-{i}", "name": b.report_name,
                                      "source_position": b.source_index, "position": i,
                                      "kind": b.kind, "empty": b.empty_state} for i, b in enumerate(blocks)],
                         "sections": report_sheets(blocks),
                         "generation_status": job.status, "reconciliation_status": reconciliation["status"] if reconciliation else "not_available"},
            "dashboard": dashboard_preview(blocks) if available["qc_dashboard"] else None,
            "analysis": [block_preview(b, i, "analysis") for i, b in enumerate(blocks)],
            "summary": [block_preview(b, i, "summary") for i, b in enumerate(blocks)],
            "detail": detail_preview(raw) if raw else None, "reconciliation": reconciliation}
