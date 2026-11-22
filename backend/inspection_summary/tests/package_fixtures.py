"""Trusted fixture builders; deliberately independent of production OPC resolver."""
import io
import posixpath
import struct
import zipfile
from xml.etree import ElementTree as ET

from .helpers import raw_workbook, workbook_bytes

CT = "http://schemas.openxmlformats.org/package/2006/content-types"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOCREL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml."


def parts():
    with zipfile.ZipFile(io.BytesIO(workbook_bytes(raw_workbook()))) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def archive(items, compression=zipfile.ZIP_STORED):
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=compression) as output:
        for name, data in items.items():
            output.writestr(name, data)
    result.seek(0)
    return result


def declare(items, name, content_type):
    tree = ET.fromstring(items["[Content_Types].xml"])
    ET.SubElement(tree, "{" + CT + "}Override", PartName="/" + name, ContentType=content_type)
    items["[Content_Types].xml"] = ET.tostring(tree)


def add_strings(items, name="xl/sharedStrings.xml", count=4):
    declare(items, name, MIME + "sharedStrings+xml")
    tree = ET.fromstring(items["xl/_rels/workbook.xml.rels"])
    ET.SubElement(tree, "{" + REL + "}Relationship", Id="string-authority",
                  Type=DOCREL + "/sharedStrings", Target="/" + name)
    items["xl/_rels/workbook.xml.rels"] = ET.tostring(tree)
    items[name] = ('<sst xmlns="' + MAIN + '">' + '<si><t>x</t></si>' * count + '</sst>').encode()


def relocate(items, old, new):
    # Absolutize targets before moving any relationship source.
    for name in list(items):
        if not name.endswith(".rels"):
            continue
        source_dir = "" if name == "_rels/.rels" else posixpath.dirname(posixpath.dirname(name))
        tree = ET.fromstring(items[name])
        for rel in tree:
            if rel.get("TargetMode") == "External":
                continue
            target = rel.get("Target", "")
            target = posixpath.normpath(posixpath.join(source_dir, target)) if not target.startswith("/") else target
            rel.set("Target", "/" + (new if target.lstrip("/") == old else target.lstrip("/")))
        items[name] = ET.tostring(tree)
    items[new] = items.pop(old)
    tree = ET.fromstring(items["[Content_Types].xml"])
    for node in tree:
        if node.get("PartName") == "/" + old:
            node.set("PartName", "/" + new)
    items["[Content_Types].xml"] = ET.tostring(tree)
    old_rels = posixpath.join(posixpath.dirname(old), "_rels", posixpath.basename(old) + ".rels")
    if old_rels in items:
        new_rels = posixpath.join(posixpath.dirname(new), "_rels", posixpath.basename(new) + ".rels")
        items[new_rels] = items.pop(old_rels)


def aliases(items, count=2):
    tree = ET.fromstring(items["xl/workbook.xml"])
    sheets = tree.find("{" + MAIN + "}sheets")
    for index in range(1, count):
        clone = ET.fromstring(ET.tostring(sheets[0]))
        clone.set("name", "Alias" + str(index))
        clone.set("sheetId", str(index + 1))
        sheets.append(clone)
    items["xl/workbook.xml"] = ET.tostring(tree)


def corrupt(kind):
    items = parts()
    if kind == "xml":
        items["xl/worksheets/sheet1.xml"] = b"<worksheet>"
        return archive(items).getvalue()
    if kind == "crc":
        name = "media/picture.bin"
        declare(items, name, "image/png")
        items[name] = b"0123456789"
        result = archive(items).getvalue()
    else:
        result = archive(items, zipfile.ZIP_DEFLATED).getvalue()
        name = next(iter(items))
    if kind == "truncated":
        return result[:-30]
    data = bytearray(result)
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        info = source.getinfo(name)
        namesize, extrasize = struct.unpack_from("<HH", data, info.header_offset + 26)
        offset = info.header_offset + 30 + namesize + extrasize
    data[offset] = 7 if kind == "deflate" else data[offset] ^ 1
    return bytes(data)
