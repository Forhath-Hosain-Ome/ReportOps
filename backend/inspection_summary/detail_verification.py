"""Independent checks of the generated dynamic detail extent and source values."""
from itertools import groupby
from openpyxl.utils.cell import get_column_letter, range_boundaries
from . import canonical as tpl
from .parser import semantic
from .report_data import detail_values


def verify_detail(package, sheet, block):
    count=len(block.defect_schema); end=count+4
    if [sheet.cell(2,c).value for c in range(5,end+1)] != list(range(1,count+1)):
        raise ValueError('Dynamic defect numbering')
    if sheet.cell(2,end+1).value is not None:
        raise ValueError('Unexpected extra defect field')
    if [sheet.cell(3,c).value for c in range(5,end+1)] != [d.label for d in block.defect_schema]:
        raise ValueError('Dynamic defect labels/order')
    for _,members in groupby(enumerate(block.defect_schema,5),key=lambda v:v[1].category):
        members=list(members);first,definition=members[0];last=members[-1][0]
        if semantic(sheet.cell(1,first).value) != semantic(definition.category):
            raise ValueError('Dynamic defect category')
        if first!=last and f'{get_column_letter(first)}1:{get_column_letter(last)}1' not in sheet.merged_cells:
            raise ValueError('Dynamic defect category extent')
    for number,(_,row) in enumerate(detail_values(block),4):
        actual=[sheet.cell(number,c).value for c in range(5,end+1)]
        expected=[row[d.column-1] for d in block.defect_schema]
        if actual!=expected:
            raise ValueError('Dynamic defect quantities/subtotals')
    print_ranges=[range_boundaries(r.split('!')[-1]) for r in str(sheet.print_area).split(',')]
    if not print_ranges or print_ranges[0][2] < end+3:
        raise ValueError('Dynamic detail print extent')
    if range_boundaries(sheet.auto_filter.ref)[2] < end+3:
        raise ValueError('Dynamic detail filter extent')
    formulas=[]
    for name,data in package.items():
        if '/charts/' in name and name.endswith('.xml'):
            formulas.extend(n.text for n in tpl.parse(data).findall('.//c:f',tpl.NS)
                            if n.text and n.text.startswith("'100%'!$E$"))
    if len(formulas)!=2 or any(f':${get_column_letter(end)}$' not in f for f in formulas):
        raise ValueError('Dynamic detail chart extent')
