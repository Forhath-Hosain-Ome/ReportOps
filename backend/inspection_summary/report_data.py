"""Shared source-backed calculations for all canonical presentation sheets."""
import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import groupby
from dataclasses import replace
from .parser import ALIASES, ratio, semantic, total


def style_key(value):
    """Trim strings only: preserve suffixes, case, punctuation and leading zeros."""
    return value.strip() if isinstance(value, str) and value.strip() else None


def dashboard_scope(blocks):
    raw = next((b for b in blocks if b.kind == "raw"), None)
    final = next((b for b in blocks if b.kind == "ordinary" and b.source_sheet == "Final"), None)
    final_styles = {style_key(r["style"]) for r in final.records} if final else set()
    raw_styles = {style_key(r["style"]) for r in raw.records} if raw else set()
    matched = (final_styles & raw_styles) - {None}

    def subset(block):
        if block is None:
            return None
        rows = [r for r in block.records if style_key(r["style"]) in matched]
        counts = [sum(known) if (known := [r["categories"][i] for r in rows
                                          if r["categories"][i] is not None]) else (0 if not rows else None)
                  for i in range(len(block.defect_schema))]
        inspected, defects = total([r["inspected"] for r in rows]), total([r["defect"] for r in rows])
        return replace(block, records=rows, inspected_qty=inspected, defect_qty=defects,
                       pass_qty=total([r.get("pass") for r in rows]) if block.kind == "raw" else None,
                       shipment_qty=total([r.get("shipment") for r in rows]) if block.kind == "ordinary" else None,
                       defect_totals=counts, defect_ratio=ratio(defects, inspected),
                       inspection_days=len({r["date"] for r in rows}), inspection_count=len(rows))
    return sorted(matched), subset(final), subset(raw)


def dashboard_equivalence(final, hundred):
    """Final defect findings scaled to matched 100% inspection volume.

    Inputs are the exact-style subsets from dashboard_scope. This is the existing
    inspection-volume comparison, not an inspector-work/headcount estimate.
    Keep valid zero distinct from an unavailable quantity or denominator.
    """
    factor = (ratio(hundred.inspected_qty, final.inspected_qty)
              if final is not None and hundred is not None else None)
    defects = final.defect_qty if final is not None else None
    equivalent = defects * factor if defects is not None and factor is not None else None
    return {
        'inspection_factor': factor,
        'final_defect_qty': defects,
        'equivalent_quantity': equivalent,
        'equivalent_calculation': (f'{defects} × {factor:.2f} = {equivalent:.2f}'
                                   if equivalent is not None else None),
        'equivalent_findings': (f'{round(equivalent)} defect-equivalent pcs'
                                if equivalent is not None else None),
        'equivalent_summary': (f'{round(equivalent)} Defect-Equivalent Pcs'
                               if equivalent is not None else None),
    }


def manpower(block):
    """Date associations only. The user explicitly left aggregate persons unknown."""
    daily = {}
    for record in block.records:
        values = daily.setdefault(record["date"], [])
        value = record.get("person")
        if value not in values:
            values.append(value)
    return [(day, values) for day, values in sorted(daily.items())]


def manpower_text(block):
    def shown(value):
        if value is None:
            return "not provided"
        return str(value) + ("p" if str(value).isdigit() else "")
    return f"{block.inspection_days}days (" + ", ".join(
        f"{day:%d %b} - " + " / ".join(shown(v) for v in values) for day, values in manpower(block)) + ")"

class OutputVerificationError(RuntimeError):
    """An internal output invariant failed; the worker must remain observable."""
    code = "OUTPUT_VERIFICATION_FAILED"

def ranked_groups(block):
    """Five DISTINCT positive quantities, retaining schema order within every tie."""
    if len(block.defect_totals) != len(block.defect_schema):
        raise OutputVerificationError("Complete defect totals are required for ranking.")
    ranked = [(i, q) for i, q in enumerate(block.defect_totals) if q is not None and q > 0]
    ranked.sort(key=lambda pair: (-pair[1], pair[0]))
    groups = []
    for qty, members in groupby(ranked, key=lambda pair: pair[1]):
        groups.append((qty, [block.defect_schema[i] for i, _ in members]))
        if len(groups) == 5:
            break
    return groups

def available_sections(blocks):
    raw=any(b.kind=='raw' for b in blocks)
    final=any(b.kind=='ordinary' and b.source_sheet=='Final' for b in blocks)
    return {'qc_dashboard':raw and final,'analysis':True,'summary':True,'detail_100':raw}


def report_sheets(blocks):
    available=available_sections(blocks)
    return (['QC Dashboard'] if available['qc_dashboard'] else [])+['Analysis','Summary']+(['100%'] if available['detail_100'] else [])


def defect_indices(block):
    indices=[d.column-1 for d in block.defect_schema]
    if (not indices or len(indices)!=len(set(indices)) or indices!=sorted(indices)
            or any(i<0 or i>=len(block.raw_headers) for i in indices)
            or any(block.raw_headers[i]!=d.label for i,d in zip(indices,block.defect_schema))):
        raise OutputVerificationError('Complete ordered defect source mappings are required.')
    return indices


def raw_columns(block):
    if block.kind!='raw': raise OutputVerificationError('A 100% source is required.')
    defects=set(defect_indices(block))
    fields=block.field_columns or {key:next((i for i,label in enumerate(block.raw_headers) if i not in defects and semantic(label) in aliases),None) for key,aliases in ALIASES.items()}
    if any(fields.get(k) is None for k in ('date','inspected','defect','style')):
        raise OutputVerificationError('100% business-field authority is incomplete.')
    if any(i is not None and (i in defects or i<0 or i>=len(block.raw_headers)) for i in fields.values()):
        raise OutputVerificationError('Overlapping or invalid business-field mappings.')
    return fields


def field_value(row,fields,key):
    index=fields.get(key)
    return row[index] if index is not None else None


class AggregateValues(list):
    """An aggregate label is independent of the physical position of quantities."""
    def __init__(self,values,label):
        super().__init__(values)
        self.label=label


def aggregate_detail(block, rows, label):
    fields=raw_columns(block); defects=set(defect_indices(block))
    values=[None]*len(block.raw_headers)
    for col,header in enumerate(block.raw_headers):
        if col in defects:
            values[col]=total([row[col] for row in rows])
        elif col in {fields.get(k) for k in ('inspected','pass','defect')} or semantic(header) in {'orderqty','majordefectqty','minordefectqty'}:
            observed=[row[col] for row in rows]
            values[col]=sum(observed) if all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in observed) else None
        elif semantic(header)=='defectratio':
            values[col]=ratio(total([field_value(r,fields,'defect') for r in rows]),total([field_value(r,fields,'inspected') for r in rows]))
    if values[0] is None: values[0]=label
    return AggregateValues(values,label)


def detail_values(block):
    fields = raw_columns(block)
    if any(len(row) != len(block.raw_headers) for row in block.raw_rows):
        raise OutputVerificationError("Raw detail record width is incomplete.")

    def week(row):
        day = row[fields["date"]]
        return day + timedelta(days=(4 - day.weekday()) % 7)

    result = []
    # The reference closes weekly subtotals on Friday; no absent calendar records.
    for end, records in groupby(block.raw_rows, key=week):
        records = list(records)
        result.extend(("detail", row) for row in records)
        result.append(("subtotal", aggregate_detail(block, records, f"Weekly Subtotal to {end:%d %b %Y}")))
    result.append(("total", aggregate_detail(block, block.raw_rows, "Grand Total")))
    return result

def same_value(actual, expected):
    if isinstance(expected, (int, float, Decimal)) and not isinstance(expected, bool) and isinstance(actual, bool):
        return False
    if isinstance(actual, datetime) and isinstance(expected, date) and not isinstance(expected, datetime):
        actual = actual.date()
    if isinstance(expected, Decimal):
        return actual is not None and math.isclose(float(actual), float(expected), rel_tol=1e-12, abs_tol=1e-12)
    return actual == expected or (actual is None and expected == "")
