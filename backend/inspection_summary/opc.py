"""Resolve consumed OPC parts before openpyxl; never infer their role from names."""
import posixpath
from urllib.parse import urlsplit

TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
BASE = "application/vnd.openxmlformats-officedocument."
CT_BOOK = BASE + "spreadsheetml.sheet.main+xml"
CT_SHEET = BASE + "spreadsheetml.worksheet+xml"
CT_CHARTSHEET = BASE + "spreadsheetml.chartsheet+xml"
CT_STRINGS = BASE + "spreadsheetml.sharedStrings+xml"
CT_RELS = "application/vnd.openxmlformats-package.relationships+xml"
CT_VML = BASE + "vmlDrawing"
CT_PRINTER = BASE + "spreadsheetml.printerSettings"


def part_uri(target, source=None):
    """Canonical internal target, with bounded package-root navigation.

    Encoded URIs are explicitly unsupported: openpyxl does not consistently URI-
    decode manifest and relationship names. Reject instead of resolving differently.
    """
    if (not target or "\\" in target or "%" in target or ":" in target
            or any(ord(c) < 32 for c in target)):
        raise ValueError("Unsupported package URI")
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Non-package target")
    parts = [] if target.startswith("/") else posixpath.dirname(source or "").split("/")
    parts = [p for p in parts if p]
    for component in target.lstrip("/").split("/"):
        if component == ".":
            continue
        if component == "..":
            if not parts:
                raise ValueError("Relationship escapes package root")
            parts.pop()
        elif not component:
            raise ValueError("Ambiguous package URI")
        else:
            parts.append(component)
    if not parts:
        raise ValueError("Empty package target")
    return "/".join(parts)


def relationship_source(name):
    if name == "_rels/.rels":
        return None
    parent, filename = posixpath.split(name)
    if posixpath.basename(parent) != "_rels" or not filename.endswith(".rels"):
        raise ValueError("Unsupported relationship part")
    return posixpath.join(posixpath.dirname(parent), filename[:-5])


def is_xml(content_type):
    return content_type.endswith("+xml") or content_type in {"application/xml", "text/xml", CT_VML}


class Package:
    def __init__(self, entries, read):
        manifest = read("[Content_Types].xml", "types")
        defaults, overrides = {}, {}
        for item in manifest["defaults"]:
            extension, kind = item.get("Extension", "").casefold(), item.get("ContentType", "")
            if not extension or "." in extension or "/" in extension or extension in defaults or not kind:
                raise ValueError("Ambiguous default content type")
            defaults[extension] = kind
        for item in manifest["overrides"]:
            name = item.get("PartName", "")
            if not name.startswith("/"):
                raise ValueError("Override must name an absolute package part")
            normalized = part_uri(name)
            if name != "/" + normalized:
                raise ValueError("Noncanonical manifest part name")
            name = normalized
            if name in overrides or name not in entries or not item.get("ContentType"):
                raise ValueError("Ambiguous/missing overridden part")
            overrides[name] = item["ContentType"]
        self.types = {}
        for name in entries:
            if name == "[Content_Types].xml" or name.endswith("/"):
                continue
            kind = overrides.get(name, defaults.get(name.rsplit(".", 1)[-1].casefold(), ""))
            if (not kind or "macroenabled" in kind.casefold() or "vbaproject" in kind.casefold()
                    or not (is_xml(kind) or kind.startswith("image/") or kind == CT_PRINTER)):
                raise ValueError("Unsupported part content type")
            if name.endswith(".rels") and kind != CT_RELS:
                raise ValueError("Relationship part has wrong content type")
            self.types[name] = kind

        # Parse each relationship part exactly once, including orphaned metadata.
        self.relationships = {}
        for name, kind in self.types.items():
            if kind != CT_RELS:
                continue
            source = relationship_source(name)
            if source is not None and source not in entries:
                raise ValueError("Relationship source missing")
            rels = {}
            for rel in read(name, "relationships")["relationships"]:
                identifier, reltype = rel.get("Id"), rel.get("Type")
                if not identifier or not reltype or identifier in rels:
                    raise ValueError("Ambiguous relationship identity")
                mode = rel.get("TargetMode", "Internal")
                if mode == "External":
                    if reltype.rsplit("/", 1)[-1] not in {"externalLinkPath", "hyperlink"}:
                        raise ValueError("External authority forbidden")
                    target = None  # Inert metadata only; keep_links=False at load.
                elif mode == "Internal":
                    target = part_uri(rel.get("Target", ""), source)
                    if target not in self.types:
                        raise ValueError("Relationship target missing/unsupported")
                else:
                    raise ValueError("Unsupported relationship target mode")
                rels[identifier] = (reltype, target)
            if source in self.relationships:
                raise ValueError("Multiple relationship authorities")
            self.relationships[source] = rels

        books = [p for p, t in self.types.items() if t == CT_BOOK]
        authorities = [target for reltype, target in self.relationships.get(None, {}).values()
                       if reltype == REL_NS + "/officeDocument"]
        if len(books) != 1 or authorities != books:
            raise ValueError("Ambiguous workbook authority")
        self.book = books[0]
        workbook_rels = self.relationships.get(self.book, {})
        self.sheets = read(self.book, "workbook")["sheets"]
        if not self.sheets:
            raise ValueError("No workbook sheet identities")
        targets, names = set(), set()
        for sheet in self.sheets:
            identifier, name = sheet.get("{" + REL_NS + "}id"), sheet.get("name")
            if not identifier or not name or name.casefold() in names or identifier not in workbook_rels:
                raise ValueError("Ambiguous workbook sheet identity")
            reltype, target = workbook_rels[identifier]
            expected = {REL_NS + "/worksheet": CT_SHEET, REL_NS + "/chartsheet": CT_CHARTSHEET}.get(reltype)
            if not target or target in targets or not expected or self.types[target] != expected:
                raise ValueError("Duplicate/unsupported sheet target")
            names.add(name.casefold())
            targets.add(target)
        string_parts = [p for p, t in self.types.items() if t == CT_STRINGS]
        string_rels = [target for reltype, target in workbook_rels.values()
                       if reltype == REL_NS + "/sharedStrings"]
        if len(string_parts) > 1 or len(string_rels) > 1 or string_parts != string_rels:
            raise ValueError("Ambiguous shared-string authority")
        # Relationship role and effective content type must agree even for unused
        # relationships; readers must not see a second, differently typed authority.
        expected_types = {REL_NS + "/worksheet": CT_SHEET, REL_NS + "/chartsheet": CT_CHARTSHEET,
                          REL_NS + "/sharedStrings": CT_STRINGS, REL_NS + "/officeDocument": CT_BOOK}
        expected_types.update({REL_NS + "/" + role: BASE + subtype for role, subtype in {
            "styles": "spreadsheetml.styles+xml", "theme": "theme+xml", "calcChain": "spreadsheetml.calcChain+xml",
            "externalLink": "spreadsheetml.externalLink+xml", "drawing": "drawing+xml", "chart": "drawingml.chart+xml",
            "comments": "spreadsheetml.comments+xml", "table": "spreadsheetml.table+xml",
            "pivotTable": "spreadsheetml.pivotTable+xml", "pivotCacheDefinition": "spreadsheetml.pivotCacheDefinition+xml",
            "pivotCacheRecords": "spreadsheetml.pivotCacheRecords+xml"}.items()})
        expected_types[REL_NS + "/vmlDrawing"] = CT_VML
        expected_types[REL_NS + "/printerSettings"] = CT_PRINTER
        for rels in self.relationships.values():
            for reltype, target in rels.values():
                if reltype in expected_types and (not target or self.types[target] != expected_types[reltype]):
                    raise ValueError("Relationship/content-type mismatch")

    def kind(self, name):
        return {CT_SHEET: "worksheet", CT_CHARTSHEET: "chartsheet", CT_STRINGS: "strings"}.get(
            self.types.get(name), "generic")
