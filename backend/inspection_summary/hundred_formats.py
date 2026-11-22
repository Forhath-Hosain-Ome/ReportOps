"""Positive, bounded 100% format recognition and explicit source mappings.

The legacy canonical header profile and compact single-category detail tables are
Raw. Other supported category-banded operational tables are Structured. Both use
one quantity/date/reconciliation implementation; filenames are never evidence.
"""
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import re

from .parser import ALIASES, PREFIX_LABELS, DefectColumn, fail, semantic
from .workbook_security import bounded_sheet


@dataclass(frozen=True)
class HundredMapping:
    header: int
    fields: dict
    defects: tuple
    headers: tuple
    numbered: bool


def category_spans(ws, header):
    spans = []
    for band in ws.merged_cells.ranges:
        if band.max_row >= header:
            continue
        label = ws.cell(band.min_row,band.min_col).value
        if isinstance(label,str) and re.search(r"^[A-Z]\s*[:.]|\bdefects?\b",label.strip(),re.I):
            spans.append((band.min_col,band.max_col,label.strip()))
    # A category containing one field has no merged range. Its explicit caption
    # still proves that column; ignore cells already covered by a merged band.
    covered={col for start,end,_ in spans for col in range(start,end+1)}
    for row in ws.iter_rows(max_row=header-1):
        for cell in row:
            if cell.column not in covered and isinstance(cell.value,str) and re.search(r"^[A-Z]\s*[:.]|\bdefects?\b",cell.value.strip(),re.I):
                spans.append((cell.column,cell.column,cell.value.strip()))
                covered.add(cell.column)
    return spans


def resolve_mapping(ws):
    bounded_sheet(ws)
    candidates=[]
    for row in ws.iter_rows(max_row=min(ws.max_row,40)):
        fields={}
        for cell in row:
            for key, aliases in ALIASES.items():
                if semantic(cell.value) in aliases:
                    if key in fields:
                        # Only a row which proves the full table is a candidate.
                        fields[key]=None
                    else: fields[key]=cell.column
        if {'date','style','item','inspected','defect'}.issubset(fields):
            if any(v is None for v in fields.values()):
                fail('AMBIGUOUS_100_FORMAT','A business field has multiple possible source columns.',ws,input='hundred_percent')
            candidates.append((row[0].row,fields))
    if not candidates:
        return None
    if len(candidates)!=1:
        fail('AMBIGUOUS_100_FORMAT','Multiple supported detail-table headers were found.',ws,input='hundred_percent')
    header,fields=candidates[0]
    spans=category_spans(ws,header)
    if not spans:
        fail('DEFECT_SCHEMA_UNRECOGNIZED','No identifiable category-banded defect region was found.',ws,input='hundred_percent')
    last=max([c.column for c in ws[header] if c.value is not None]+[end for _,end,_ in spans])
    defects=[];occurrences=Counter()
    for col in range(1,last+1):
        cell=ws.cell(header,col);label=cell.value
        categories={name for start,end,name in spans if start<=col<=end}
        if len(categories)>1:
            fail('DEFECT_COLUMN_INVALID','Overlapping categories make a defect column ambiguous.',ws,cell.coordinate,'hundred_percent')
        if categories:
            if not isinstance(label,str) or not label.strip() or semantic(label) in PREFIX_LABELS:
                fail('DEFECT_COLUMN_INVALID','A defect column needs an unambiguous label.',ws,cell.coordinate,'hundred_percent')
            category=next(iter(categories));key=(semantic(category),semantic(label));occurrences[key]+=1
            defects.append(DefectColumn(col,category,label.strip(),len(defects)+1,occurrences[key]))
        elif label is not None and semantic(label) not in PREFIX_LABELS:
            fail('DEFECT_COLUMN_INVALID','An unclassified source column cannot be omitted.',ws,cell.coordinate,'hundred_percent')
    if not defects:
        fail('DEFECT_SCHEMA_UNRECOGNIZED','No supported defect fields were identified.',ws,input='hundred_percent')
    markers=[ws.cell(header-1,d.column).value if header>1 else None for d in defects]
    numbered=any(isinstance(v,(int,float)) or isinstance(v,str) and v.strip().isdigit() for v in markers)
    if numbered and not all(type(v) is int and v==i for i,v in enumerate(markers,1)):
        fail('DEFECT_NUMBERING_INVALID','Defect numbering must cover every field once in source order.',ws,input='hundred_percent')
    if not numbered:
        for d,v in zip(defects,markers):
            if v is not None and semantic(v)!=semantic(d.category):
                fail('DEFECT_NUMBERING_INVALID','The band above the defects is not a supported numbering or category band.',ws,input='hundred_percent')
    return HundredMapping(header,fields,tuple(defects),tuple(str(ws.cell(header,c).value).strip() if ws.cell(header,c).value is not None else '' for c in range(1,last+1)),numbered)


@lru_cache(maxsize=1)
def legacy_labels():
    # A template-specific recognizer signature, never a normalized count rule.
    from . import canonical as tpl
    parts=tpl.read_package(tpl.ASSET);sheet=tpl.parse(parts[tpl.sheet_parts(parts)['100%']])
    row=sheet.find("m:sheetData/m:row[@r='3']",tpl.NS)
    return tuple(semantic(''.join(c.itertext())) for c in row if re.fullmatch(r'(?:[E-Z]|A[A-M])3',c.get('r','')))


class Raw100Adapter:
    name='raw'
    @staticmethod
    def recognizes(mapping):
        return isinstance(mapping, HundredMapping) and (len({d.category for d in mapping.defects})==1 or
                tuple(semantic(d.label) for d in mapping.defects)==legacy_labels())


class Structured100Adapter:
    name='structured'
    @staticmethod
    def recognizes(mapping):
        return isinstance(mapping, HundredMapping) and len({d.category for d in mapping.defects})>1 and not Raw100Adapter.recognizes(mapping)


from .monthly_100 import StructuredMonthly100Adapter

ADAPTERS=(Raw100Adapter,Structured100Adapter,StructuredMonthly100Adapter)


def resolve_supported_mapping(ws):
    mappings = [mapping for mapping in (resolve_mapping(ws), StructuredMonthly100Adapter.resolve(ws))
                if mapping is not None]
    if len(mappings) > 1:
        fail('AMBIGUOUS_100_FORMAT', 'Multiple incompatible format mappings were found.', ws, input='hundred_percent')
    return mappings[0] if mappings else None


def detect_format(mapping,ws):
    matches=[adapter for adapter in ADAPTERS if adapter.recognizes(mapping)]
    if len(matches)>1:
        fail('AMBIGUOUS_100_FORMAT','The workbook matches incompatible 100% formats.',ws,input='hundred_percent')
    if not matches:
        fail('UNSUPPORTED_100_FORMAT','The workbook does not match a supported 100% format.',ws,input='hundred_percent')
    return matches[0]
