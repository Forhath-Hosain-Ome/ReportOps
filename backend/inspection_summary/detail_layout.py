"""Adapt only the canonical detail stencil to a resolved, ordered defect schema.

Canonical indices below describe style prototypes, not business field counts.
The workbook asset, dashboard and Analysis/Summary presentation remain untouched.
"""
from copy import deepcopy
from itertools import groupby
import re
from openpyxl.utils.cell import get_column_letter,range_boundaries,column_index_from_string,coordinate_from_string
from . import canonical as tpl
from .parser import semantic


def prepare_detail(root,block):
    data=root.find('m:sheetData',tpl.NS)
    original={int(r.get('r')):deepcopy(r) for r in data}
    # Source template has four identifying columns, its defect styles, then three
    # quantity/result styles. Derive the defect prototype extent from numbering.
    header=original[2]
    numbered=[c for c in header if c.find('m:v',tpl.NS) is not None]
    first=5; old_count=len(numbered); old_end=first+old_count-1; old_core=old_end+3
    new_count=len(block.defect_schema); new_end=first+new_count-1; core_end=new_end+3
    spans=[]
    merges=root.find('m:mergeCells',tpl.NS)
    for merge in merges:
        lo,top,hi,bottom=range_boundaries(merge.get('ref'))
        if top==bottom==1 and lo>=first and hi<=old_end:
            cell=original[1].find(f"m:c[@r='{get_column_letter(lo)}1']",tpl.NS)
            spans.append((lo,hi,semantic(''.join(cell.itertext())) if cell is not None else ''))
    source_columns=list(range(1,first)); occurrences={}
    for i,d in enumerate(block.defect_schema):
        key=semantic(d.category); offset=occurrences.get(key,0);occurrences[key]=offset+1
        matching=next(((lo,hi) for lo,hi,name in spans if name==key),None)
        source_columns.append(min(matching[0]+offset,matching[1]) if matching else min(first+i,old_end))
    source_columns+=list(range(old_end+1,old_core+1))
    for row in data:
        r=int(row.get('r'));lookup={column_index_from_string(coordinate_from_string(c.get('r'))[0]):c for c in original[r] if tpl.ET.QName(c).localname=='c'}
        for cell in list(row): row.remove(cell)
        for target,source in enumerate(source_columns,1):
            cell=deepcopy(lookup.get(source,lookup.get(first)))
            if cell is None: continue
            cell.set('r',f'{get_column_letter(target)}{r}')
            row.append(cell)
    # Rebuild only header merges. Old body merges are removed by render_detail.
    for node in list(merges): merges.remove(node)
    for ref in ['A1:C3','D1:D3',*[f'{get_column_letter(c)}1:{get_column_letter(c)}3' for c in range(new_end+1,core_end+1)]]:
        tpl.ET.SubElement(merges,'{'+tpl.M+'}mergeCell',ref=ref)
    for _,members in groupby(enumerate(block.defect_schema,first),key=lambda item:item[1].category):
        members=list(members);lo,definition=members[0];hi=members[-1][0]
        if hi>lo: tpl.ET.SubElement(merges,'{'+tpl.M+'}mergeCell',ref=f'{get_column_letter(lo)}1:{get_column_letter(hi)}1')
        current=data[0].find(f"m:c[@r='{get_column_letter(lo)}1']",tpl.NS)
        old_text=''.join(current.itertext()) if current is not None else ''
        # Preserve exact canonical caption bytes when source semantics are equal.
        text=old_text if semantic(old_text)==semantic(definition.category) else definition.category
        for col in range(lo,hi+1): tpl.set_cell(root,f'{get_column_letter(col)}1',text if col==lo else None)
    cols=root.find('m:cols',tpl.NS)
    old_cols=list(cols)
    for n in list(cols): cols.remove(n)
    for new,old in enumerate(source_columns,1):
        prototype=next((n for n in old_cols if int(n.get('min'))<=old<=int(n.get('max'))),None)
        node=deepcopy(prototype) if prototype is not None else tpl.ET.Element('{'+tpl.M+'}col',width='12',customWidth='1')
        node.set('min',str(new));node.set('max',str(new));cols.append(node)
    return new_end,core_end
