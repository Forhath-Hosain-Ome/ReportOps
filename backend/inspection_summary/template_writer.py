"""Populate sanitized canonical OOXML; leave dashboard presentation untouched."""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
import io
import re
from textwrap import wrap

import openpyxl
from openpyxl.utils.cell import column_index_from_string, coordinate_from_string, get_column_letter, range_boundaries
from openpyxl.utils.datetime import to_excel

from . import canonical as tpl
from .parser import ratio, semantic, total
from .report_data import (OutputVerificationError, dashboard_scope, detail_values, manpower_text,
                          ranked_groups, raw_columns, same_value, defect_indices, field_value, report_sheets, available_sections, dashboard_equivalence)
from .workbook_security import validate_workbook

ERRORS = {"#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!"}


def scalar(value):
    if isinstance(value, (date, datetime)):
        return to_excel(value)
    return float(value) if isinstance(value, Decimal) else value


def decoded(parts, root, address):
    cell = root.find(f"m:sheetData/m:row/m:c[@r='{address}']", tpl.NS)
    if cell is None:
        return None
    if cell.get("t") == "inlineStr":
        return "".join(cell.itertext())
    value = cell.find("m:v", tpl.NS)
    if value is None:
        return None
    if cell.get("t") == "s":
        item = list(tpl.parse(parts["xl/sharedStrings.xml"]))[int(value.text)]
        return "".join(item.itertext())
    return float(value.text)


def chart_values(values, formula, kind):
    address = formula.rsplit("!", 1)[-1]
    low, first, high, last = range_boundaries(address)
    return [scalar(values.get(f"{get_column_letter(col)}{row}"))
            for row in range(first, last + 1) for col in range(low, high + 1)]


def add_type(parts, name, content_type):
    root = tpl.parse(parts["[Content_Types].xml"])
    if not any(n.get("PartName") == "/" + name for n in root):
        tpl.ET.SubElement(root, "{" + tpl.T + "}Override", PartName="/" + name, ContentType=content_type)
    parts["[Content_Types].xml"] = tpl.xml(root)


def drawing_info(parts, sheet_part):
    rels = tpl.parse(parts[tpl.relationships(sheet_part)])
    name = next(tpl.target(sheet_part, n.get("Target")) for n in rels if n.get("Type").endswith("/drawing"))
    links = tpl.parse(parts[tpl.relationships(name)])
    lookup = {n.get("Id"): tpl.target(name, n.get("Target")) for n in links}
    return name, tpl.parse(parts[name]), links, lookup


def relocate_row(row, destination):
    result = deepcopy(row)
    result.set("r", str(destination))
    for cell in result:
        if tpl.ET.QName(cell).localname == "c":
            cell.set("r", re.sub(r"\d+$", str(destination), cell.get("r")))
    return result


def set_values(root, values):
    for address, value in values.items():
        tpl.set_cell(root, address, scalar(value))


def dashboard_values(blocks):
    styles, final, raw = dashboard_scope(blocks)
    days = sorted({r["date"] for b in (raw, final) if b for r in b.records})
    factories = list(dict.fromkeys(r["factory"] for r in (raw.records if raw else []) if r["factory"]))
    items = list(dict.fromkeys(r["item"] for r in (raw.records if raw else []) if r["item"]))
    values = {address: None for address in tpl.DASH_DYNAMIC}
    if final is None or raw is None:
        values["I12"] = "Final report not provided"
        return values, styles
    values.update(C3=", ".join(factories) or None,
                  P3=", ".join(items) or None,
                  U3=(f"{days[0]:%d %b %Y} to {days[-1]:%d %b %Y}"
                      if days else None), G6=raw.inspection_days, G8=len(styles),
                  G9=raw.inspected_qty, G10=raw.pass_qty, G11=raw.defect_qty, G12=raw.defect_ratio,
                  W6=final.inspection_days if final else 0, W7=len(styles),
                  W8=final.shipment_qty if final else 0, W9=final.inspected_qty if final else 0,
                  W10=final.defect_qty if final else 0, W11=final.defect_ratio if final else None,
                  Z3=raw.defect_ratio, Z4=final.defect_ratio if final else None)
    # Persons and team leaders have no source-backed canonical aggregate rule.
    values["I12"] = (f"{raw.defect_ratio:.2%} → {final.defect_ratio:.2%}"
                      if final and raw.defect_ratio is not None and final.defect_ratio is not None
                      else "No exact style matches" if not styles else "Comparison unavailable")
    grouped = []
    for side, label_col, ratio_col, qty_col in ((raw, "B", "K", "L"), (final, "N", "W", "X")):
        groups = ranked_groups(side) if side else []
        grouped.append(groups)
        for i, (qty, defects) in enumerate(groups):
            row = 17 + i
            values[f"{label_col}{row}"] = ", ".join(d.label for d in defects)
            values[f"{ratio_col}{row}"] = ratio(qty, side.inspected_qty)
            values[f"{qty_col}{row}"] = qty
    for groups, address, side in zip(grouped, ("E22", "R22"), (raw, final)):
        qty = sum(q for q, _ in groups)
        percentage = ratio(qty, side.defect_qty) if side else None
        values[address] = f"Top 5 total = {qty} defects" + (f", {percentage:.1%} of all defects" if percentage is not None else "")
    comparison = dashboard_equivalence(final, raw)
    factor = comparison['inspection_factor']
    values["T26"] = factor
    values["T27"] = comparison['final_defect_qty']
    for i, (qty, defects) in enumerate(grouped[1]):
        row = 26 + i
        values[f"B{row}"] = ", ".join(d.label for d in defects)
        values[f"H{row}"] = qty
        values[f"I{row}"] = f"{qty * factor:.2f} ≈ {round(qty * factor)} pcs" if factor is not None else None
    values["H31"] = sum(q for q, _ in grouped[1])
    values["I31"] = (f"{values['H31'] * factor:.2f} ≈ {round(values['H31'] * factor)} pcs" if factor is not None else None)
    values["T28"] = comparison['equivalent_calculation']
    values["T29"] = comparison['equivalent_findings']
    values["O30"] = comparison['equivalent_summary']
    return values, styles


def prototype_index(block):
    return 4 if block.kind == "raw" else {"Final": 0, "Re-Final": 1, "Random": 2,
                                         "INLINE-SPL": 3, "INLINE": 3}.get(block.source_sheet, 0)


def block_title(parts, prototype, block, start):
    if block.kind == "raw" or block.source_sheet in {"Final", "Re-Final", "Random"}:
        return decoded(parts, prototype, f"A{start}")
    return "In-Line - " + block.report_name if block.source_sheet in {"INLINE", "INLINE-SPL"} else block.report_name


def render_blocks(parts, sheet_name, blocks):
    part = tpl.sheet_parts(parts)[sheet_name]
    prototype = tpl.parse(parts[part]); root = deepcopy(prototype)
    sheet_data = root.find("m:sheetData", tpl.NS)
    source_rows = {int(r.get("r")): r for r in sheet_data}
    for row in list(sheet_data): sheet_data.remove(row)
    sheet_data.append(deepcopy(source_rows[1]))
    merges = root.find("m:mergeCells", tpl.NS)
    source_merges = list(merges)
    for n in list(merges): merges.remove(n)
    tpl.ET.SubElement(merges, "{" + tpl.M + "}mergeCell", ref="A1:M1")
    drawing_part, drawing, old_rels, links = drawing_info(parts, part)
    old_anchors = list(drawing)
    new_drawing = deepcopy(drawing)
    for n in list(new_drawing): new_drawing.remove(n)
    new_rels = deepcopy(old_rels)
    for n in list(new_rels): new_rels.remove(n)
    values = {"A1": ", ".join(dict.fromkeys(name for b in blocks for name in b.factories)) or None}
    manifests, start_row = [], 2
    for index, block in enumerate(blocks):
        old_start, old_end = tpl.BLOCKS[sheet_name][prototype_index(block)]
        old_header = old_start + (5 if sheet_name == "Analysis" and block.kind == "raw" else 4)
        offset = old_header - old_start
        groups = ranked_groups(block) if not block.empty_state else []
        count = max(1, len(groups))
        end_row = start_row + offset + count
        for i in range(offset + 1 + count):
            source = source_rows[min(old_start + i, old_end)]
            sheet_data.append(relocate_row(source, start_row + i))
        shift = start_row - old_start
        for n in source_merges:
            low, first, high, last = range_boundaries(n.get("ref"))
            if first < old_start or last > old_end:
                continue
            last = old_header + count if low == high == 1 and first == old_header else last
            if first > old_header:
                continue
            tpl.ET.SubElement(merges, "{" + tpl.M + "}mergeCell",
                             ref=f"{get_column_letter(low)}{first + shift}:{get_column_letter(high)}{last + shift}")
        title = block_title(parts, prototype, block, old_start)
        r = start_row
        values.update({f"A{r}": title, f"C{r+1}": ", ".join(block.factories) or None,
                       f"F{r+1}": (f"{block.date_start:%d %b %Y} to {block.date_end:%d %b %Y}" if block.date_start else None),
                       f"H{r+1}": f"({block.inspection_days:02d} Days)", f"L{r+1}": None,
                       f"A{r+2}": f"Total: {len(block.styles) if block.kind == 'raw' else block.inspection_count:02d}-" + ("Style" if block.kind == "raw" else "Audit"),
                       f"E{r+2}": block.inspected_qty if block.kind == "raw" else block.shipment_qty,
                       f"H{r+2}": block.pass_qty if block.kind == "raw" else block.inspected_qty,
                       f"K{r+2}": block.defect_qty, f"M{r+2}": block.defect_ratio,
                       f"B{r+3}": ", ".join(block.items) or None, f"J{r+3}": None})
        if block.kind == "raw":
            values[f"I{r+1}"] = "Persons :" if sheet_name == "Analysis" else None
            values[f"J{r+1}"] = None
            if sheet_name == "Analysis": values[f"C{r+4}"] = manpower_text(block)
        header = start_row + offset
        denominator = block.inspected_qty if sheet_name == "Analysis" else block.defect_qty
        basis = "inspected" if sheet_name == "Analysis" else "defect"
        values[f"G{header}"] = f"Each top 5 defect items are prorated based on the total {basis} qty of " + (f"{denominator} Pcs" if denominator is not None else "not provided")
        for i, (qty, defects) in enumerate(groups):
            row = header + 1 + i
            values.update({f"B{row}": i + 1, f"C{row}": ", ".join(dict.fromkeys(d.category or "" for d in defects)),
                           f"D{row}": ", ".join(d.label for d in defects), f"E{row}": qty,
                           f"F{row}": ratio(qty, denominator)})
        if block.empty_state:
            values[f"D{header+1}"] = "No inspection records found for this section."
        # Clone a canonical chart belonging to this prototype and rebind its cells.
        for anchor in old_anchors:
            ref = anchor.find(".//c:chart", tpl.NS)
            if ref is None:
                continue
            old_chart = links[ref.get("{" + tpl.R + "}id")]
            chart = tpl.parse(parts[old_chart])
            formulas = [n.text for n in chart.findall(".//c:val/c:numRef/c:f", tpl.NS)]
            if not any(old_header < int(re.findall(r"\$?(\d+)", f)[0]) <= old_end for f in formulas if f and "#REF!" not in f):
                continue
            first, last = header + 1, header + count
            def rebind(kind, formula):
                col = "D" if kind == "strRef" else "F"
                return f"'{sheet_name}'!${col}${first}:${col}${last}"
            tpl.refresh_chart(chart, lambda f, k: chart_values(values, f, k), rebind=rebind)
            chart_name = f"xl/charts/generated_{sheet_name}_{index}.xml"
            parts[chart_name] = tpl.xml(chart)
            add_type(parts, chart_name, "application/vnd.openxmlformats-officedocument.drawingml.chart+xml")
            old_chart_rels = tpl.relationships(old_chart)
            if old_chart_rels in parts:
                rels = tpl.parse(parts[old_chart_rels])
                for rel in rels: rel.set("Target", "/" + tpl.target(old_chart, rel.get("Target")))
                parts[tpl.relationships(chart_name)] = tpl.xml(rels)
            node = deepcopy(anchor)
            for tag in ("from", "to"):
                row = node.find(f"d:{tag}/d:row", tpl.NS)
                if row is not None: row.text = str(int(row.text) + shift)
            identifier = f"chart{index}"
            node.find(".//c:chart", tpl.NS).set("{" + tpl.R + "}id", identifier)
            new_drawing.append(node)
            tpl.ET.SubElement(new_rels, "{" + tpl.P + "}Relationship", Id=identifier, Type=tpl.R + "/chart", Target="/" + chart_name)
            break
        manifests.append((block.report_name, start_row, end_row))
        start_row = end_row + 2
    # Source rows carry only styles/fixed labels; values are always source-derived.
    set_values(root, values)
    for row in sheet_data:
        r = int(row.get("r"))
        text = values.get(f"D{r}")
        if isinstance(text, str) and r not in {s + 2 for _, s, _ in manifests}:
            required = max(1, len(wrap(text, 45))) * 13 + 6
            row.set("ht", str(min(409, max(float(row.get("ht", "15")), required))))
            row.set("customHeight", "1")
    merges.set("count", str(len(merges)))
    root.find("m:dimension", tpl.NS).set("ref", f"A1:M{manifests[-1][2]}")
    parts[part] = tpl.xml(root)
    parts[drawing_part], parts[tpl.relationships(drawing_part)] = tpl.xml(new_drawing), tpl.xml(new_rels)
    return values, manifests


def detail_spec(block):
    fields=raw_columns(block); defects=defect_indices(block)
    ratio_col=next((i for i,label in enumerate(block.raw_headers) if i not in defects and semantic(label)=='defectratio'),None)
    core=[fields['date'],fields.get('factory'),fields['style'],fields['inspected'],*defects,fields['defect'],fields.get('pass'),ratio_col]
    return core+[i for i in range(len(block.raw_headers)) if i not in core and block.raw_headers[i]]


def detail_rows(block):
    spec=detail_spec(block);result=[]
    for kind,source in detail_values(block):
        cells=[source[index] if index is not None else None for index in spec]
        if kind!='detail': cells[0]=source.label;cells[1]=cells[2]=None
        result.append((kind,cells))
    return result


def render_detail(parts, block):
    part = tpl.sheet_parts(parts)["100%"]
    root = tpl.parse(parts[part])
    from .detail_layout import prepare_detail
    defect_end,core_end=prepare_detail(root,block)
    data = root.find("m:sheetData", tpl.NS)
    source_rows = {int(r.get("r")): deepcopy(r) for r in data}
    for row in list(data): data.remove(row)
    for number in (1, 2, 3): data.append(deepcopy(source_rows[number]))
    merges = root.find("m:mergeCells", tpl.NS)
    for node in list(merges):
        _, first, _, last = range_boundaries(node.get("ref"))
        if last > 3 or node.get("ref") == "A1:C3": merges.remove(node)
    tpl.ET.SubElement(merges, "{" + tpl.M + "}mergeCell", ref="A1:C2")
    spec = detail_spec(block); width = len(spec)
    styles = tpl.parse(parts['xl/styles.xml'])
    xfs = styles.find('m:cellXfs', tpl.NS)
    date_style = deepcopy(xfs[int(source_rows[4].find("m:c[@r='A4']", tpl.NS).get('s', '0'))])
    date_style.set('numFmtId', '14'); date_style.set('applyNumberFormat', '1')
    date_style_id = len(xfs); xfs.append(date_style); xfs.set('count', str(len(xfs)))
    parts['xl/styles.xml'] = tpl.xml(styles)
    labels = [block.raw_headers[i] if i is not None else "" for i in spec]
    labels[0:3] = ["Inspection Date", "Factory Name", "Style No"]
    values = {"A1": ", ".join(block.factories) + " - 100% inspection detail"}
    for col, label in enumerate(labels, 1):
        if col in (4, defect_end+1, defect_end+2, defect_end+3):
            continue  # Canonical vertically merged quantity headers remain exact.
        address = f"{get_column_letter(col)}3"
        values[address] = label
        if col <= 3 or col > core_end:
            existing = data[2].find(f"m:c[@r='{address}']", tpl.NS)
            if existing is not None: data[2].remove(existing)
            cell = deepcopy(source_rows[3].find("m:c[@r='E3']", tpl.NS))
            cell.set("r", address); tpl.clear_cell(cell); data[2].append(cell)
    for col in range(5, defect_end+1): values[f"{get_column_letter(col)}2"] = col - 4
    cols = root.find("m:cols", tpl.NS)
    # B/C were hidden calendar helpers, now actual Factory/Style fields.
    for node in list(cols):
        if int(node.get("min")) > core_end: cols.remove(node)
        elif int(node.get("min")) == 1:
            node.set('width', '14')
        elif int(node.get("min")) in (2, 3):
            node.set("hidden", "0"); node.set("width", "28")
    for col in range(core_end+1, width + 1):
        tpl.ET.SubElement(cols, "{" + tpl.M + "}col", min=str(col), max=str(col), width="18", customWidth="1")
        tpl.ET.SubElement(merges, "{" + tpl.M + "}mergeCell", ref=f"{get_column_letter(col)}1:{get_column_letter(col)}2")
    for number, (kind, cells) in enumerate(detail_rows(block), 4):
        prototype = source_rows[4 if kind == "detail" else 6 if kind == "subtotal" else 41]
        row = relocate_row(prototype, number)
        if kind == 'detail':
            row.find(f"m:c[@r='A{number}']", tpl.NS).set('s', str(date_style_id))
        # Remove old calendars/side panels, retaining canonical styles per column.
        for cell in list(row):
            if tpl.ET.QName(cell).localname == "c" and column_index_from_string(coordinate_from_string(cell.get("r"))[0]) > core_end:
                row.remove(cell)
            elif tpl.ET.QName(cell).localname == "c": tpl.clear_cell(cell)
        for col in range(core_end+1, width + 1):
            style = prototype.find(f"m:c[@r='D{prototype.get('r')}']", tpl.NS)
            cell = deepcopy(style); cell.set("r", f"{get_column_letter(col)}{number}"); tpl.clear_cell(cell); row.append(cell)
        data.append(row)
        for col, value in enumerate(cells, 1): values[f"{get_column_letter(col)}{number}"] = value
        # Grand/subtotal labels belong in A and do not become detail dates.
        if kind != "detail":
            values[f"A{number}"] = "Grand Total" if kind == "total" else next(
                value for value in cells if isinstance(value, str) and value.startswith("Weekly Subtotal"))
            values[f"B{number}"] = values[f"C{number}"] = None
            tpl.ET.SubElement(merges, "{" + tpl.M + "}mergeCell", ref=f"A{number}:C{number}")
    total_row = len(detail_rows(block)) + 3
    last_row = total_row + 1
    percent = relocate_row(source_rows[42], last_row)
    for cell in percent: tpl.clear_cell(cell)
    data.append(percent)
    values[f"A{last_row}"] = "Defect%"
    for col, qty in enumerate(block.defect_totals, 5):
        values[f"{get_column_letter(col)}{last_row}"] = ratio(qty, block.defect_qty)
    for ref in (f"A{last_row}:D{last_row}", f"{get_column_letter(defect_end+1)}{last_row}:{get_column_letter(core_end)}{last_row}"):
        tpl.ET.SubElement(merges, "{" + tpl.M + "}mergeCell", ref=ref)
    set_values(root, values)
    # Two live canonical charts use fresh table totals / a regenerated Top 5 helper band.
    helpers = {}
    helper_start=max(width+15,69)
    for i, (qty, defects) in enumerate(ranked_groups(block)):
        helpers[f"{get_column_letter(helper_start+i)}5"] = ", ".join(d.label for d in defects)
        helpers[f"{get_column_letter(helper_start+i)}7"] = ratio(qty, block.defect_qty)
    set_values(root, helpers); values.update(helpers)
    root.find("m:dimension", tpl.NS).set("ref", f"A1:{get_column_letter(helper_start+4)}{last_row}")
    view = root.find("m:sheetViews/m:sheetView", tpl.NS)
    old_pane = view.find("m:pane", tpl.NS)
    if old_pane is not None: view.remove(old_pane)
    pane = tpl.ET.Element("{" + tpl.M + "}pane", xSplit="4", ySplit="3", topLeftCell="E4", activePane="bottomRight", state="frozen")
    view.insert(0, pane)
    auto = root.find("m:autoFilter", tpl.NS)
    if auto is None:
        auto = tpl.ET.Element("{" + tpl.M + "}autoFilter")
        root.insert(list(root).index(merges), auto)
    auto.set("ref", f"A3:{get_column_letter(width)}{last_row}")
    # Added source fields widen the canonical calendar table: fit the complete
    # operational schema across one page, without retaining obsolete page breaks.
    for tag in ('rowBreaks', 'colBreaks'):
        node = root.find('m:' + tag, tpl.NS)
        if node is not None: root.remove(node)
    setup = root.find('m:pageSetup', tpl.NS)
    setup.attrib.pop('scale', None)
    setup.set('fitToWidth', '1'); setup.set('fitToHeight', '1')
    properties = root.find('m:sheetPr', tpl.NS)
    fit = properties.find('m:pageSetUpPr', tpl.NS)
    if fit is None: fit = tpl.ET.SubElement(properties, '{' + tpl.M + '}pageSetUpPr')
    fit.set('fitToPage', '1')
    merges.set("count", str(len(merges)))
    parts[part] = tpl.xml(root)
    drawing_name, drawing, _, links = drawing_info(parts, part)
    chart_end = last_row
    for anchor in drawing:
        for tag in ("from", "to"):
            row = anchor.find(f"d:{tag}/d:row", tpl.NS)
            if row is not None: row.text = str(int(row.text) + last_row - 42)
        last_anchor = anchor.find("d:to/d:row", tpl.NS)
        if last_anchor is not None: chart_end = max(chart_end, int(last_anchor.text) + 1)
        for col_node in anchor.findall("d:from/d:col",tpl.NS)+anchor.findall("d:to/d:col",tpl.NS):
            col_node.text=str(round(int(col_node.text)*core_end/42))
        ref = anchor.find(".//c:chart", tpl.NS)
        if ref is None: continue
        chart_part = links[ref.get("{" + tpl.R + "}id")]
        chart = tpl.parse(parts[chart_part])
        pie = chart.find(".//c:pieChart", tpl.NS) is not None
        if not pie:
            for text in chart.findall('c:chart/c:title//a:t', tpl.NS):
                text.text = 'Raw inspection defect distribution'
        def rebind(kind, formula):
            if pie: return f"'100%'!${get_column_letter(helper_start)}${5 if kind == 'strRef' else 7}:${get_column_letter(helper_start+4)}${5 if kind == 'strRef' else 7}"
            return f"'100%'!$E$3:${get_column_letter(defect_end)}$3" if kind == "strRef" else f"'100%'!$E${last_row}:${get_column_letter(defect_end)}${last_row}"
        tpl.refresh_chart(chart, lambda f, k: chart_values(values, f, k), rebind=rebind)
        parts[chart_part] = tpl.xml(chart)
    parts[drawing_name] = tpl.xml(drawing)
    return values, last_row, width, chart_end


def compose(blocks):
    raw = [b for b in blocks if b.kind == "raw" and b.report_name == "100%"]
    if len(raw)>1 or not blocks:
        raise OutputVerificationError("Report authority is empty or ambiguous.")
    sheet_names=report_sheets(blocks)
    parts = tpl.read_package(tpl.ASSET)
    selected = tpl.sheet_parts(parts)
    if 'QC Dashboard' in sheet_names:
        dashboard, _ = dashboard_values(blocks)
        root = tpl.parse(parts[selected["QC Dashboard"]]); set_values(root, dashboard)
        parts[selected["QC Dashboard"]] = tpl.xml(root)
        _, drawing, _, links = drawing_info(parts, selected["QC Dashboard"])
        for anchor in drawing:
            ref = anchor.find(".//c:chart", tpl.NS)
            if ref is not None:
                name = links[ref.get("{" + tpl.R + "}id")]; chart = tpl.parse(parts[name])
                tpl.refresh_chart(chart, lambda f, k: chart_values(dashboard, f, k))
                parts[name] = tpl.xml(chart)
    maps, manifests = ({"QC Dashboard": dashboard} if "QC Dashboard" in sheet_names else {}), {}
    for name in ("Analysis", "Summary"):
        maps[name], manifests[name] = render_blocks(parts, name, blocks)
    if raw:
        maps["100%"], last, width, chart_end = render_detail(parts, raw[0])
    workbook = tpl.parse(parts["xl/workbook.xml"])
    sheets=workbook.find('m:sheets',tpl.NS)
    for sheet in list(sheets):
        if sheet.get('name') not in sheet_names: sheets.remove(sheet)
    rels=tpl.parse(parts['xl/_rels/workbook.xml.rels'])
    kept={sheet.get('{'+tpl.R+'}id') for sheet in sheets}
    for rel in list(rels):
        if rel.get('Type').endswith('/worksheet') and rel.get('Id') not in kept: rels.remove(rel)
    parts['xl/_rels/workbook.xml.rels']=tpl.xml(rels)
    selected={k:v for k,v in selected.items() if k in sheet_names}
    old_names = workbook.find("m:definedNames", tpl.NS)
    if old_names is not None: workbook.remove(old_names)
    names = tpl.ET.Element("{" + tpl.M + "}definedNames")
    tpl.insert_names(workbook, names)
    for view in workbook.findall("m:bookViews/m:workbookView", tpl.NS): view.set("activeTab", "0")
    for index, name in enumerate(sheet_names):
        end = 39 if name == "QC Dashboard" else last if name == "100%" else manifests[name][-1][2] + 1
        column = "X" if name == "QC Dashboard" else get_column_letter(width) if name == "100%" else "M"
        n = tpl.ET.SubElement(names, "{" + tpl.M + "}definedName", name="_xlnm.Print_Area", localSheetId=str(index))
        n.text = f"'{name}'!$A$1:${column}${end}"
        if name == "100%":
            n.text += f",'100%'!$A${last+1}:${get_column_letter(len(raw[0].defect_schema)+7)}${chart_end}"
            n = tpl.ET.SubElement(names, "{" + tpl.M + "}definedName", name="_xlnm.Print_Titles", localSheetId=str(index))
            n.text = "'100%'!$1:$3"
        if name in manifests:
            for i, (label, first, _) in enumerate(manifests[name]):
                n = tpl.ET.SubElement(names, "{" + tpl.M + "}definedName",
                                     name=("InspectionBlock_" if name == "Summary" else "AnalysisBlock_") + f"{i:03d}", comment=label)
                n.text = f"'{name}'!$A${first}"
    parts["xl/workbook.xml"] = tpl.xml(workbook)
    for part in selected.values():
        root = tpl.parse(parts[part]); data = root.find("m:sheetData", tpl.NS)
        for row in data:
            cells = list(row)
            if all(tpl.ET.QName(c).localname == "c" for c in cells):
                row[:] = sorted(cells, key=lambda c: column_index_from_string(coordinate_from_string(c.get("r"))[0]))
        data[:] = sorted(data, key=lambda r: int(r.get("r")))
        parts[part] = tpl.xml(root)
    # Application metadata must not advertise removed historical worksheets.
    if "docProps/app.xml" in parts:
        app = tpl.parse(parts["docProps/app.xml"])
        for node in list(app):
            if tpl.ET.QName(node).localname == "HeadingPairs":
                for child in list(node): node.remove(child)
                ns = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
                vector = tpl.ET.SubElement(node, "{" + ns + "}vector", size="2", baseType="variant")
                label = tpl.ET.SubElement(vector, "{" + ns + "}variant")
                tpl.ET.SubElement(label, "{" + ns + "}lpstr").text = "Worksheets"
                count = tpl.ET.SubElement(vector, "{" + ns + "}variant")
                tpl.ET.SubElement(count, "{" + ns + "}i4").text = str(len(sheet_names))
            if tpl.ET.QName(node).localname == "TitlesOfParts":
                for child in list(node): node.remove(child)
                ns = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
                vector = tpl.ET.SubElement(node, "{" + ns + "}vector", size=str(len(sheet_names)), baseType="lpstr")
                for name in sheet_names: tpl.ET.SubElement(vector, "{" + ns + "}lpstr").text = name
        parts["docProps/app.xml"] = tpl.xml(app)
    return tpl.prune(parts), maps, manifests


def write_report(blocks, path):
    parts, _, _ = compose(blocks)
    tpl.write_package(parts, path)


def verify_report(path, blocks):
    try:
        with open(path, "rb") as stream: validate_workbook(stream)
        actual = tpl.read_package(path)
        expected, _, _ = compose(blocks)
        if actual != expected:
            raise ValueError("Canonical presentation or source-backed values changed")
        for name in tpl.sheet_parts(actual).values():
            coordinates = [c.get("r") for c in tpl.parse(actual[name]).findall(".//m:c", tpl.NS)]
            if len(coordinates) != len(set(coordinates)):
                raise ValueError("Duplicate worksheet cell coordinates")
        wb = openpyxl.load_workbook(path, data_only=False, keep_links=False)
        try:
            if wb.sheetnames != report_sheets(blocks) or any(s.sheet_state != "visible" for s in wb):
                raise ValueError("Conditional sheet contract")
            for sheet in wb:
                for row in sheet:
                    for cell in row:
                        if cell.data_type in {"f", "e"} or (isinstance(cell.value, str) and cell.value in ERRORS):
                            raise ValueError("Unsupported formula or Excel error")
            if any(b.kind=='raw' for b in blocks):
                block = next(b for b in blocks if b.kind == "raw")
                from .detail_verification import verify_detail
                verify_detail(actual, wb['100%'], block)
                fields = raw_columns(block); rows = block.raw_rows
                if (len(rows) != block.inspection_count or len({r[fields['date']] for r in rows}) != block.inspection_days
                        or total([r[fields['inspected']] for r in rows]) != block.inspected_qty
                        or total([field_value(r,fields,'pass') for r in rows]) != block.pass_qty
                        or total([r[fields['defect']] for r in rows]) != block.defect_qty
                        or sum(sum(r[i] for i in defect_indices(block)) for r in rows) != block.defect_qty):
                    raise ValueError("Raw reconciliation")
        finally:
            wb.close()
    except (ValueError, KeyError, IndexError, tpl.ET.XMLSyntaxError) as exc:
        raise OutputVerificationError("Generated canonical report failed verification.") from exc
