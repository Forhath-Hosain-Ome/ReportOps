"""Normalize a positively recognized 100% source through shared validation."""
from collections import defaultdict
import re
from .workbook_security import WorkbookValidationError

from .parser import (ReportBlock, defect_columns, detect_header, fail, inspection_day,
                     normalize_label, optional_integer, ratio, read_cell, top_defects, total, workbook_pair)


def parse_raw_workbook(path):
    with workbook_pair(path) as (formula, values):
        from .hundred_formats import resolve_supported_mapping, detect_format
        candidates=[]
        for sheet in formula.worksheets:
            if sheet.sheet_state!='visible': continue
            mapping=resolve_supported_mapping(sheet)
            if mapping is not None: candidates.append((sheet,values[sheet.title],mapping))
        if not candidates:
            fail('UNSUPPORTED_100_FORMAT','No supported visible 100% detail table was found.',input='hundred_percent')
        if len(candidates)!=1:
            fail('AMBIGUOUS_100_FORMAT','Multiple authoritative 100% detail tables were found.',input='hundred_percent')
        ws,cached,mapping=candidates[0]
        adapter=detect_format(mapping,ws)
        from .monthly_100 import StructuredMonthly100Adapter
        if adapter is StructuredMonthly100Adapter:
            return adapter.parse(ws,cached,mapping)
        header,fields,schema=mapping.header,mapping.fields,list(mapping.defects)
        sparse=mapping.numbered
        records = []
        for row in range(header + 1, ws.max_row + 1):
            if all(ws.cell(row, col).value in (None, "") for col in range(1, ws.max_column + 1)):
                continue
            value = read_cell(ws, cached, row, fields["date"], input="hundred_percent")
            def is_total(item):
                return re.match(r"^(?:合計|total|subtotal|weekly subtotal)(?:$|\s)",str(item).strip(),re.I)
            # A valid dated record may legitimately have a style/item named Total.
            # Only undated or explicitly labelled summary rows can be excluded.
            if (value in (None, "") or is_total(value)) and any(
                    is_total(ws.cell(row,c).value) for c in (1,fields['date'])):
                continue
            day = inspection_day(value, ws=ws, cell=ws.cell(row, fields["date"]).coordinate, input="hundred_percent")
            record = {"date": day}
            for key in ("inspected", "defect", "pass"):
                col = fields.get(key)
                if col is None:
                    record[key] = None
                    continue
                record[key] = optional_integer(read_cell(ws, cached, row, col, input="hundred_percent"), ws=ws,
                                               cell=ws.cell(row, col).coordinate, input="hundred_percent", required=key != "pass")
            for key in ("item", "person", "factory"):
                col = fields.get(key)
                value = read_cell(ws, cached, row, col, input="hundred_percent") if col else None
                record[key] = None if value in (None, "") else str(value).strip()
            counts = []
            for d in schema:
                value = read_cell(ws, cached, row, d.column, input="hundred_percent")
                if value in (None, "") and sparse:
                    value = 0
                try:
                    counts.append(optional_integer(value,ws=ws,cell=ws.cell(row,d.column).coordinate,input="hundred_percent",required=True))
                except WorkbookValidationError as exc:
                    fail('DEFECT_QUANTITY_INVALID',exc.detail['detail'],ws,ws.cell(row,d.column).coordinate,'hundred_percent')
            if sum(counts) != record["defect"]:
                fail("DEFECT_TOTAL_MISMATCH", "Defect categories do not match the row Defect Qty.",
                     ws, ws.cell(row, fields["defect"]).coordinate, "hundred_percent")
            record["categories"] = counts
            # Expose consumed detail values for output, retaining source column order.
            # Only the already-validated sparse defect band is zero-filled.
            record["source_values"] = [read_cell(ws,cached,row,col,input="hundred_percent") for col in range(1,len(mapping.headers)+1)]
            for col in range(len(mapping.headers)+1,ws.max_column+1):
                if read_cell(ws,cached,row,col,input="hundred_percent") is not None:
                    fail('DEFECT_COLUMN_INVALID','Populated source data has no recognized header.',ws,ws.cell(row,col).coordinate,'hundred_percent')
            for col,label in enumerate(mapping.headers,1):
                if not label and record['source_values'][col-1] is not None:
                    fail('DEFECT_COLUMN_INVALID','Populated source data has no recognized header.',ws,ws.cell(row,col).coordinate,'hundred_percent')
            record['source_values'][fields['date']-1]=day
            for key in ('inspected','pass','defect'):
                if key in fields: record['source_values'][fields[key]-1]=record[key]
            for definition,qty in zip(schema,counts): record['source_values'][definition.column-1]=qty
            record["style"] = read_cell(ws, cached, row, fields["style"], input="hundred_percent")
            records.append(record)
        return normalize_hundred(ws,mapping,records,adapter.name,sparse)


def normalize_hundred(ws,mapping,records,format_name,sparse):
    """Existing shared date aggregation and ReportBlock construction for every adapter."""
    schema=list(mapping.defects)
    fields=mapping.fields
    daily = defaultdict(list)
    for r in records:
        daily[r["date"]].append(r)
    days = []
    for day, rows in sorted(daily.items()):
        counts = [sum(r["categories"][i] for r in rows) for i in range(len(schema))]
        defects = sum(r["defect"] for r in rows)
        if sum(counts) != defects:
            fail("DEFECT_TOTAL_MISMATCH", "Daily defect totals do not reconcile.", ws, input="hundred_percent")
        days.append({"date": day, "inspected": sum(r["inspected"] for r in rows),
                     "pass": total([r["pass"] for r in rows]), "defect": defects, "categories": counts})
    inspected = sum(r["inspected"] for r in records)
    defects = sum(r["defect"] for r in records)
    counts = [sum(r["categories"][i] for r in records) for i in range(len(schema))]
    if sum(counts) != defects or sum(d["defect"] for d in days) != defects:
        fail("DEFECT_TOTAL_MISMATCH", "Overall defect totals do not reconcile.", ws, input="hundred_percent")
    return ReportBlock("100%", -1, "100%", "raw", date_start=min(daily) if daily else None,
                       date_end=max(daily) if daily else None, inspection_count=len(records),
                       inspected_qty=inspected, defect_qty=defects, defect_ratio=ratio(defects, inspected),
                       items=list(dict.fromkeys(r["item"] for r in records if r["item"])),
                       personnel=list(dict.fromkeys(r["person"] for r in records if r["person"])),
                       factories=list(dict.fromkeys(r["factory"] for r in records if r["factory"])),
                       top_defects=top_defects(schema, counts, inspected), daily_rows=days,
                       empty_state=not records, defect_schema=schema,
                       inspection_days=len(daily), defect_totals=counts,
                       pass_qty=total([r["pass"] for r in records]),
                       styles=list(dict.fromkeys(str(r["style"]).strip() for r in records
                                                 if r["style"] not in (None, ""))),
                       raw_headers=list(mapping.headers),
                       raw_rows=[r["source_values"] for r in sorted(records, key=lambda r: r["date"])],
                       records=records, format=format_name, field_columns={k:v-1 for k,v in fields.items()},
                       blank_defects_are_zero=sparse)
