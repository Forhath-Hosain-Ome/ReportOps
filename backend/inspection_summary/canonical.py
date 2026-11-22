"""Trusted, sanitized OOXML templates. No uploaded package is edited here.

Preserve canonical drawing/image bytes instead of round-tripping them through a
workbook serializer. Only explicit cell inputs and chart caches are dynamic.
"""
from copy import deepcopy
import io
import json
import posixpath
from pathlib import Path
import zipfile

from lxml import etree as ET

M = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P = "http://schemas.openxmlformats.org/package/2006/relationships"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
D = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
T = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"m": M, "r": R, "p": P, "c": C, "d": D, "a": A}
SHEETS = ["QC Dashboard", "Analysis", "Summary", "100%"]
ASSET = Path(__file__).with_name("templates") / "canonical.xlsx"
MANIFEST = ASSET.with_suffix(".json")
BLOCKS = {"Analysis": [(2, 11), (13, 19), (21, 27), (29, 38), (40, 50)],
          "Summary": [(2, 11), (13, 19), (21, 27), (29, 38), (40, 49)]}
DASH_DYNAMIC = set("C3 G3 K3 P3 U3 I12 G6 G7 G8 G9 G10 G11 G12 G13 W6 W7 W8 W9 W10 W11 W12 Z3 Z4 E22 R22 H31 I31 T26 T27 T28 T29 O30".split())
DASH_DYNAMIC.update(f"{col}{row}" for col in ("B", "K", "L", "N", "W", "X") for row in range(17, 22))
DASH_DYNAMIC.update(f"{col}{row}" for col in ("B", "H", "I") for row in range(26, 31))


def parse(data):
    return ET.fromstring(data, ET.XMLParser(resolve_entities=False, no_network=True))


def xml(node):
    return ET.tostring(node, xml_declaration=True, encoding="UTF-8", standalone=True)


def insert_names(workbook, names):
    before = next((n for n in workbook if ET.QName(n).localname in {"calcPr", "oleSize", "customWorkbookViews", "extLst"}), None)
    workbook.insert(list(workbook).index(before) if before is not None else len(workbook), names)


def relationships(part):
    return posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")


def target(part, value):
    return posixpath.normpath(value.lstrip("/") if value.startswith("/") else
                             posixpath.join(posixpath.dirname(part), value))


def read_package(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist() if not n.endswith("/")}


def write_package(parts, stream):
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)


def sheet_parts(parts):
    rels = {n.get("Id"): target("xl/workbook.xml", n.get("Target"))
            for n in parse(parts["xl/_rels/workbook.xml.rels"])}
    return {n.get("name"): rels[n.get("{" + R + "}id")]
            for n in parse(parts["xl/workbook.xml"]).find("m:sheets", NS)}


def clear_cell(cell):
    for child in list(cell):
        if ET.QName(child).localname in {"v", "f", "is"}:
            cell.remove(child)
    cell.attrib.pop("t", None)


def set_cell(root, address, value):
    data = root.find("m:sheetData", NS)
    row_number = int("".join(c for c in address if c.isdigit()))
    row = data.find(f"m:row[@r='{row_number}']", NS)
    if row is None:
        row = ET.SubElement(data, "{" + M + "}row", r=str(row_number))
    cell = row.find(f"m:c[@r='{address}']", NS)
    if cell is None:
        cell = ET.SubElement(row, "{" + M + "}c", r=address)
    clear_cell(cell)
    if value is None:
        return cell
    if isinstance(value, str):
        cell.set("t", "inlineStr")
        text = ET.SubElement(ET.SubElement(cell, "{" + M + "}is"), "{" + M + "}t")
        text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        text.text = value
    elif isinstance(value, bool):
        cell.set("t", "b")
        ET.SubElement(cell, "{" + M + "}v").text = "1" if value else "0"
    else:
        ET.SubElement(cell, "{" + M + "}v").text = str(value)
    return cell


def refresh_chart(root, values, *, rebind=None):
    """Keep chart formatting/series, replacing only data refs/caches."""
    for kind in ("numRef", "strRef"):
        for ref in root.findall(".//c:" + kind, NS):
            formula = ref.find("c:f", NS)
            if rebind:
                formula.text = rebind(kind, formula.text)
            cache = ref.find("c:" + ("numCache" if kind == "numRef" else "strCache"), NS)
            if cache is None:
                cache = ET.SubElement(ref, "{" + C + "}" + ("numCache" if kind == "numRef" else "strCache"))
            for child in list(cache):
                if ET.QName(child).localname != "formatCode":
                    cache.remove(child)
            entries = values(formula.text, kind)
            ET.SubElement(cache, "{" + C + "}ptCount", val=str(len(entries)))
            for index, value in enumerate(entries):
                if value is None:
                    continue
                point = ET.SubElement(cache, "{" + C + "}pt", idx=str(index))
                ET.SubElement(point, "{" + C + "}v").text = str(value)


def prune(parts):
    """Drop unreachable historical worksheets, caches, drawings and metadata."""
    seen = set()

    def visit(part):
        if part in seen or (part and part not in parts):
            return
        seen.add(part)
        relpart = "_rels/.rels" if not part else relationships(part)
        if relpart in parts:
            seen.add(relpart)
            for rel in parse(parts[relpart]):
                if rel.get("TargetMode") != "External":
                    visit(target(part, rel.get("Target")))
    visit("")
    ct = parse(parts["[Content_Types].xml"])
    for node in list(ct):
        if node.tag.endswith("Override") and node.get("PartName").lstrip("/") not in seen:
            ct.remove(node)
    result = {n: v for n, v in parts.items() if n in seen or n == "[Content_Types].xml"}
    result["[Content_Types].xml"] = xml(ct)
    return result


def compact_strings(parts):
    """Retain only strings actually used by the sanitized four-sheet asset."""
    path = "xl/sharedStrings.xml"
    if path not in parts:
        return
    old = list(parse(parts[path])); used = {}
    for part in sheet_parts(parts).values():
        root = parse(parts[part])
        for cell in root.findall(".//m:c[@t='s']", NS):
            node = cell.find("m:v", NS)
            index = int(node.text)
            if index not in used:
                used[index] = len(used)
            node.text = str(used[index])
        parts[part] = xml(root)
    root = ET.Element("{" + M + "}sst", nsmap={None: M}, count=str(len(used)), uniqueCount=str(len(used)))
    for index in used:
        root.append(deepcopy(old[index]))
    parts[path] = xml(root)


def merge_styles(base, imported):
    """Append style components and remap indices, preserving all base style IDs."""
    a, b = parse(base), parse(imported)
    maps = {}
    for name in ("fonts", "fills", "borders", "cellStyleXfs", "cellXfs", "dxfs"):
        left, right = a.find("m:" + name, NS), b.find("m:" + name, NS)
        if left is None:
            left = ET.SubElement(a, "{" + M + "}" + name, count="0")
        maps[name] = len(left)
        if right is not None:
            for child in right:
                left.append(deepcopy(child))
        left.set("count", str(len(left)))
    custom = a.find("m:numFmts", NS)
    if custom is None:
        custom = ET.Element("{" + M + "}numFmts", count="0"); a.insert(0, custom)
    formats = {int(n.get("numFmtId")): n.get("formatCode") for n in custom}
    num_map = {}
    for node in b.findall("m:numFmts/m:numFmt", NS):
        code = node.get("formatCode")
        identifier = next((i for i, c in formats.items() if c == code), max([163, *formats]) + 1)
        if identifier not in formats:
            new = deepcopy(node); new.set("numFmtId", str(identifier)); custom.append(new); formats[identifier] = code
        num_map[int(node.get("numFmtId"))] = identifier
    custom.set("count", str(len(custom)))
    for name in ("cellStyleXfs", "cellXfs"):
        for xf in list(a.find("m:" + name, NS))[maps[name]:]:
            for attr, group in (("fontId", "fonts"), ("fillId", "fills"), ("borderId", "borders")):
                if attr in xf.attrib:
                    xf.set(attr, str(int(xf.get(attr)) + maps[group]))
            if "xfId" in xf.attrib:
                xf.set("xfId", str(int(xf.get("xfId")) + maps["cellStyleXfs"]))
            if int(xf.get("numFmtId", "0")) in num_map:
                xf.set("numFmtId", str(num_map[int(xf.get("numFmtId"))]))
    return xml(a), maps


def build_asset(reference, detail_reference, destination=ASSET):
    """Explicit offline build from user-authorized references; never on intake."""
    parts, extra = read_package(reference), read_package(detail_reference)
    if parts["xl/theme/theme1.xml"] != extra["xl/theme/theme1.xml"]:
        raise ValueError("Composite reference themes differ")
    selected = sheet_parts(parts); detail_source = sheet_parts(extra)["100%"]
    # Add the second workbook's detail graph under a collision-free namespace.
    mapping = {detail_source: "xl/worksheets/canonical100.xml"}
    imported = set()

    def copy_graph(source):
        if source in imported:
            return mapping[source]
        imported.add(source)
        dest = mapping.setdefault(source, "xl/detail_reference/" + source)
        parts[dest] = extra[source]
        relpath = relationships(source)
        if relpath in extra:
            rels = parse(extra[relpath])
            for rel in rels:
                if rel.get("TargetMode") == "External":
                    raise ValueError("External canonical detail relationship")
                rel.set("Target", "/" + copy_graph(target(source, rel.get("Target"))))
            parts[relationships(dest)] = xml(rels)
        return dest
    detail_dest = copy_graph(detail_source)
    parts["xl/styles.xml"], style_map = merge_styles(parts["xl/styles.xml"], extra["xl/styles.xml"])
    root = parse(parts[detail_dest])
    for cell in root.findall(".//m:c", NS):
        cell.set("s", str(int(cell.get("s", "0")) + style_map["cellXfs"]))
    # Convert only the retained detail header strings to inline rich text.
    strings = list(parse(extra["xl/sharedStrings.xml"])) if "xl/sharedStrings.xml" in extra else []
    for cell in root.findall(".//m:c[@t='s']", NS):
        index = int(cell.find("m:v", NS).text)
        clear_cell(cell); cell.set("t", "inlineStr")
        inline = ET.SubElement(cell, "{" + M + "}is")
        for child in strings[index]: inline.append(deepcopy(child))
    for row in root.findall("m:sheetData/m:row", NS):
        for cell in list(row):
            address = cell.get("r", "")
            letters = "".join(c for c in address if c.isalpha())
            col = 0
            for ch in letters: col = col * 26 + ord(ch) - 64
            if col > 42:
                row.remove(cell)
            elif int(row.get("r")) > 3 or address == "A1":
                clear_cell(cell)
    parts[detail_dest] = xml(root)
    # Retain precisely the three presentation sheets and the imported detail.
    workbook = parse(parts["xl/workbook.xml"]); sheets = workbook.find("m:sheets", NS)
    kept = [deepcopy(n) for n in sheets if n.get("name") in SHEETS[:3]]
    for n in list(sheets): sheets.remove(n)
    rels = parse(parts["xl/_rels/workbook.xml.rels"])
    keep_ids = {n.get("{" + R + "}id") for n in kept}
    for n in list(rels):
        if n.get("Type").endswith(("/worksheet", "/calcChain", "/externalLink")) and n.get("Id") not in keep_ids:
            rels.remove(n)
    for n in kept: n.set("state", "visible"); sheets.append(n)
    ET.SubElement(sheets, "{" + M + "}sheet", name="100%", sheetId="999", attrib={"{" + R + "}id": "canonicalDetail"})
    ET.SubElement(rels, "{" + P + "}Relationship", Id="canonicalDetail", Type=R + "/worksheet", Target="/" + detail_dest)
    # Preserve valid print names with new local scope IDs; discard historical names.
    names = workbook.find("m:definedNames", NS)
    print_names = ET.Element("{" + M + "}definedNames")
    if names is not None:
        original_order = list(selected)
        for node in names:
            scope = node.get("localSheetId")
            if scope is not None and int(scope) < len(original_order):
                name = original_order[int(scope)]
                if name in SHEETS[:3] and node.get("name") in {"_xlnm.Print_Area", "_xlnm.Print_Titles"}:
                    new = deepcopy(node); new.set("localSheetId", str(SHEETS.index(name))); print_names.append(new)
        workbook.remove(names)
    detail_book = parse(extra["xl/workbook.xml"])
    detail_order = list(sheet_parts(extra))
    for node in detail_book.findall("m:definedNames/m:definedName", NS):
        scope = node.get("localSheetId")
        if (scope is not None and detail_order[int(scope)] == "100%"
                and node.get("name") in {"_xlnm.Print_Area", "_xlnm.Print_Titles"}):
            new = deepcopy(node); new.set("localSheetId", "3"); print_names.append(new)
    insert_names(workbook, print_names)
    external = workbook.find("m:externalReferences", NS)
    if external is not None: workbook.remove(external)
    parts["xl/workbook.xml"] = xml(workbook); parts["xl/_rels/workbook.xml.rels"] = xml(rels)
    selected = sheet_parts(parts)
    dashboard = parse(parts[selected["QC Dashboard"]])
    for address in DASH_DYNAMIC: set_cell(dashboard, address, None)
    parts[selected["QC Dashboard"]] = xml(dashboard)
    for name in ("Analysis", "Summary"):
        sheet = parse(parts[selected[name]])
        starts = {start for start, _ in BLOCKS[name]}
        headers = {start + (5 if start == 40 and name == "Analysis" else 4) for start in starts}
        for row in sheet.findall("m:sheetData/m:row", NS):
            r = int(row.get("r"))
            for cell in row:
                address = cell.get("r", "")
                col = "".join(c for c in address if c.isalpha())
                # Keep only fixed labels. All values, dates, names and rank data go.
                fixed = (r in starts and col == "A") or (r in headers and col in {"A", "B", "C", "D", "E", "F"})
                fixed |= any(r == s + 1 and col in {"A", "E", "K", "I"} or
                             r == s + 2 and col in {"D", "G", "J", "L"} or
                             r == s + 3 and col in {"A", "H"} for s in starts)
                fixed |= name == "Analysis" and address == "A44"
                if not fixed or len(col) > 1 or col > "M": clear_cell(cell)
        parts[selected[name]] = xml(sheet)
    # The source has one unused, broken Summary chart. Drop its drawing anchor.
    for name, data in list(parts.items()):
        if "/charts/" in name and name.endswith(".xml") and "/_rels/" not in name:
            chart = parse(data)
            refresh_chart(chart, lambda f, kind: [])
            parts[name] = xml(chart)
    # Import effective content types for the detail graph and rels.
    ct, ct_extra = parse(parts["[Content_Types].xml"]), parse(extra["[Content_Types].xml"])
    defaults = {n.get("Extension"): n.get("ContentType") for n in ct_extra if n.tag.endswith("Default")}
    overrides = {n.get("PartName").lstrip("/"): n.get("ContentType") for n in ct_extra if n.tag.endswith("Override")}
    for source, dest in mapping.items():
        kind = overrides.get(source, defaults.get(source.rsplit(".", 1)[-1]))
        ET.SubElement(ct, "{" + T + "}Override", PartName="/" + dest, ContentType=kind)
    parts["[Content_Types].xml"] = xml(ct)
    for name, data in list(parts.items()):
        if "/drawings/" not in name or not name.endswith(".xml") or "/_rels/" in name:
            continue
        relpath = relationships(name)
        if relpath not in parts:
            continue
        drawing, rels = parse(data), parse(parts[relpath])
        changed = False
        for rel in list(rels):
            chart_part = target(name, rel.get("Target"))
            if rel.get("Type").endswith("/chart") and b"#REF!" in parts[chart_part]:
                for anchor in list(drawing):
                    if any(c.get("{" + R + "}id") == rel.get("Id") for c in anchor.findall(".//c:chart", NS)):
                        drawing.remove(anchor)
                rels.remove(rel)
                changed = True
        if changed:
            parts[name], parts[relpath] = xml(drawing), xml(rels)
    compact_strings(parts)
    parts = prune(parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_package(parts, destination)
    record_manifest(reference, detail_reference, destination)
    return parts


def dashboard_profile(sheet):
    """Non-dynamic presentation fingerprint used by the fidelity regression."""
    def element(value):
        return ET.tostring(value.to_tree(), method="c14n").decode()
    cells = {}
    for row in sheet:
        for cell in row:
            if cell.value is None and not cell.has_style:
                continue
            cells[cell.coordinate] = {
                "value": None if cell.coordinate in DASH_DYNAMIC else cell.value,
                "font": element(cell.font), "fill": element(cell.fill),
                "border": element(cell.border), "alignment": element(cell.alignment),
                "format": cell.number_format, "hyperlink": cell.hyperlink.target if cell.hyperlink else None}
    return {"cells": cells, "merges": sorted(str(r) for r in sheet.merged_cells),
            "rows": {str(k): dict(v) for k, v in sheet.row_dimensions.items()},
            "columns": {k: dict(v) for k, v in sheet.column_dimensions.items()},
            "freeze": sheet.freeze_panes, "print_area": str(sheet.print_area),
            "page_setup": element(sheet.page_setup), "margins": element(sheet.page_margins),
            "print_rows": sheet.print_title_rows, "print_cols": sheet.print_title_cols,
            "validation": element(sheet.data_validations),
            "conditional": [(str(k), [element(r) for r in v]) for k, v in sheet.conditional_formatting._cf_rules.items()],
            "chart_types": [type(c).__name__ for c in sheet._charts], "images": len(sheet._images)}


def record_manifest(reference, detail_reference, destination):
    import hashlib
    import openpyxl
    source = openpyxl.load_workbook(reference, keep_links=False)
    sanitized = openpyxl.load_workbook(destination, keep_links=False)
    try:
        profile = dashboard_profile(source["QC Dashboard"])
        if profile != dashboard_profile(sanitized["QC Dashboard"]):
            raise ValueError("Canonical dashboard presentation changed during sanitization")
    finally:
        source.close(); sanitized.close()
    parts = read_package(reference)
    sheet = sheet_parts(parts)["QC Dashboard"]
    links = parse(parts[relationships(sheet)])
    drawing = next(target(sheet, n.get("Target")) for n in links if n.get("Type").endswith("/drawing"))
    preserved = {drawing: hashlib.sha256(parts[drawing]).hexdigest()}
    chart_styles = {}
    for node in parse(parts[relationships(drawing)]):
        if node.get("Type").endswith("/image"):
            name = target(drawing, node.get("Target"))
            preserved[name] = hashlib.sha256(parts[name]).hexdigest()
        elif node.get("Type").endswith("/chart"):
            name = target(drawing, node.get("Target"))
            chart_styles[name] = chart_fingerprint(parts[name])
    manifest = {"sources": {Path(p).name: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                            for p in (reference, detail_reference)},
                "asset_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "dashboard_dynamic_cells": sorted(DASH_DYNAMIC), "dashboard_profile": profile,
                "dashboard_artifacts": preserved,
                "dashboard_chart_styles": chart_styles,
                "manpower": "Aggregate blank by explicit user decision; date-linked source values only",
                "detail_adaptations": "Raw records replace calendar projection; B/C exposed as Factory/Style; extra metadata to right; canonical defect/quantity styles retained"}
    destination.with_suffix(".json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def chart_fingerprint(data):
    import hashlib
    root = parse(data)
    for node in root.xpath("//c:numCache|//c:strCache", namespaces=NS):
        node.getparent().remove(node)
    return hashlib.sha256(ET.tostring(root, method="c14n")).hexdigest()
