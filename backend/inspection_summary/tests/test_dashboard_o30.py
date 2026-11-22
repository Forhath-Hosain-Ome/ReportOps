"""QC Dashboard O30 semantic summary; source/detail O30 coordinates are unrelated."""
from copy import copy
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import openpyxl
from django.test import SimpleTestCase
from inspection_summary import canonical as tpl
from inspection_summary.parser import parse_inspection_workbook
from inspection_summary.preview import dashboard_preview
from inspection_summary.report_data import dashboard_scope
from inspection_summary.writer import write_report,verify_report

"""Synthetic source workbooks with matched duplicates and unmatched controls."""
from .helpers import ordinary, raw_workbook
from .test_monthly_100 import monthly_workbook


def source_pair(format_name='raw', count=37, *, final_defects=3,
                final_quantities=(100,200), hundred_quantities=(600,300), matched=True):
    summary=openpyxl.Workbook();summary.remove(summary.active)
    final=ordinary(summary,count=3,defects=count)
    for row,qty in [(4,final_quantities[0]),(5,final_quantities[1]),(6,10000)]:
        final.cell(row,5,' STYLE-001 ' if row==4 else 'STYLE-001' if row==5 else 'FINAL-ONLY')
        final.cell(row,6,qty);defects=final_defects if row<6 else 900;final.cell(row,7,defects)
        for col in range(10,10+count):final.cell(row,col,0)
        final.cell(row,10,1 if defects==3 else defects)
        if defects==3:final.cell(row,9+count,2)
    monthly=format_name=='structured_monthly_100'
    hundred=monthly_workbook(count) if monthly else raw_workbook(categories=count)
    ws=hundred['Unrelated current name'] if monthly else hundred.active
    rows=[5,6,9] if monthly else [5,6,7]
    defect_start=7 if monthly else 9
    inspected_col=6 if monthly else 5
    defect_col=count+7 if monthly else 7
    pass_col=count+8 if monthly else 6
    style_col=3
    all_counts=[]
    for index,row in enumerate(rows):
        qty=hundred_quantities[index] if index<2 else 1000
        style=(' STYLE-001 ' if index==0 else 'STYLE-001') if matched else ('style-001' if index==0 else 'STYLE-001-SUFFIX')
        ws.cell(row,style_col,style if index<2 else 'HUNDRED-ONLY')
        values=[0]*count
        if qty:values[0]=1;values[-1]=2
        for col,value in enumerate(values,defect_start):ws.cell(row,col,value)
        ws.cell(row,inspected_col,qty);ws.cell(row,defect_col,sum(values));ws.cell(row,pass_col,qty-sum(values))
        all_counts.append(values)
    if monthly:
        ws.cell(10,inspected_col,sum(hundred_quantities)+1000)
        ws.cell(10,defect_col,sum(map(sum,all_counts)))
        ws.cell(10,pass_col,sum(hundred_quantities)+1000-sum(map(sum,all_counts)))
        for offset in range(count):ws.cell(10,defect_start+offset,sum(r[offset] for r in all_counts))
    return summary,hundred


class DashboardO30Tests(SimpleTestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def blocks(self,format_name='raw',count=37,**kwargs):
        final,hundred=source_pair(format_name,count,**kwargs)
        final.save(self.root/'final.xlsx');hundred.save(self.root/'hundred.xlsx');final.close();hundred.close()
        return parse_inspection_workbook(self.root/'final.xlsx',self.root/'hundred.xlsx')

    def output(self,blocks):
        path=self.root/'Result.xlsx';write_report(blocks,path);verify_report(path,blocks)
        wb=openpyxl.load_workbook(path,data_only=False);self.addCleanup(wb.close)
        return wb

    def test_positive_matched_summary_is_written_for_raw_and_monthly(self):
        for format_name in ['raw','structured_monthly_100']:
            with self.subTest(format=format_name):
                blocks=self.blocks(format_name)
                matched,final,hundred=dashboard_scope(blocks)
                self.assertEqual(matched,['STYLE-001'])
                self.assertEqual(final.inspection_count,2);self.assertEqual(hundred.inspection_count,2)
                self.assertEqual((final.inspected_qty,final.defect_qty,hundred.inspected_qty),(300,6,900))
                # Independent source quantities: duplicate records contribute;
                # unmatched source records must not influence this comparison.
                expected=Decimal(3+3)*Decimal(600+300)/Decimal(100+200)
                self.assertEqual(expected,18)
                ws=self.output(blocks)['QC Dashboard']
                self.assertEqual(ws['O30'].value,f'{round(expected)} Defect-Equivalent Pcs')
                self.assertEqual(ws['O30'].data_type,'s')
                self.assertEqual(ws['O30'].number_format,'General')
                self.assertIn('O30:X31',str(ws.merged_cells))
                self.assertNotIn('Inspector',ws['O30'].value)
                self.assertEqual(ws['T26'].value,3)
                self.assertEqual(ws['T27'].value,6)
                self.assertEqual(ws['T28'].value,'6 × 3.00 = 18.00')
                self.assertEqual(ws['T29'].value,'18 defect-equivalent pcs')

    def test_valid_zero_final_defects_remains_formatted_zero(self):
        for format_name in ['raw','structured_monthly_100']:
            with self.subTest(format=format_name):
                blocks=self.blocks(format_name,final_defects=0)
                ws=self.output(blocks)['QC Dashboard']
                self.assertEqual(ws['O30'].value,'0 Defect-Equivalent Pcs')
                self.assertEqual(ws['T27'].value,0)
                self.assertEqual(ws['T28'].value,'0 × 3.00 = 0.00')
                self.assertEqual(ws['T29'].value,'0 defect-equivalent pcs')

    def test_valid_zero_inspection_factor_is_not_missing(self):
        blocks=self.blocks(hundred_quantities=(0,0))
        ws=self.output(blocks)['QC Dashboard']
        self.assertEqual(ws['T26'].value,0)
        self.assertEqual(ws['O30'].value,'0 Defect-Equivalent Pcs')

    def test_zero_denominator_and_missing_quantity_remain_unavailable(self):
        for format_name in ['raw','structured_monthly_100']:
            with self.subTest(format=format_name):
                blocks=self.blocks(format_name,final_quantities=(0,0),final_defects=0)
                ws=self.output(blocks)['QC Dashboard']
                self.assertIsNone(ws['O30'].value);self.assertIsNone(ws['T26'].value)
                self.assertIsNone(ws['T29'].value)
        blocks=self.blocks()
        for row in blocks[0].records[:2]:row['defect']=None
        ws=self.output(blocks)['QC Dashboard']
        self.assertIsNone(ws['O30'].value);self.assertIsNone(ws['T27'].value)

    def test_no_exact_match_keeps_dashboard_and_explicit_no_match_state(self):
        for format_name in ['raw','structured_monthly_100']:
            with self.subTest(format=format_name):
                blocks=self.blocks(format_name,matched=False)
                self.assertEqual(dashboard_scope(blocks)[0],[])
                wb=self.output(blocks);self.assertIn('QC Dashboard',wb.sheetnames)
                self.assertEqual(wb['QC Dashboard']['I12'].value,'No exact style matches')
                self.assertIsNone(wb['QC Dashboard']['O30'].value)
                self.assertIsNone(wb['QC Dashboard']['T29'].value)

    def test_missing_either_authority_omits_dashboard(self):
        for format_name in ['raw','structured_monthly_100']:
            with self.subTest(format=format_name):
                self.blocks(format_name)
                for inputs in [(self.root/'final.xlsx',None),(None,self.root/'hundred.xlsx')]:
                    blocks=parse_inspection_workbook(*inputs)
                    self.assertNotIn('QC Dashboard',self.output(blocks).sheetnames)

    def test_dynamic_defects_and_neighboring_values_do_not_shift_o30(self):
        for count in [28,35,37,42,60]:
            for format_name in ['raw','structured_monthly_100']:
                with self.subTest(count=count,format=format_name):
                    blocks=self.blocks(format_name,count)
                    _,final,hundred=dashboard_scope(blocks)
                    self.assertEqual(final.defect_totals[-1],4)
                    self.assertEqual(hundred.defect_totals[-1],4)
                    ws=self.output(blocks)['QC Dashboard']
                    expected={'P29':'Final Team findings =','O30':'18 Defect-Equivalent Pcs'}
                    for row in ws.iter_rows(min_row=29,max_row=31,min_col=14,max_col=16):
                        for cell in row:self.assertEqual(cell.value,expected.get(cell.coordinate),cell.coordinate)
                    self.assertEqual(ws['G11'].value,6);self.assertEqual(ws['W10'].value,6)
                    self.assertEqual(ws['H31'].value,6);self.assertEqual(ws['I31'].value,'18.00 ≈ 18 pcs')

    def test_fractional_equivalent_retains_existing_rounding_and_preview_fields(self):
        blocks=self.blocks(hundred_quantities=(600,325))
        expected=Decimal(6)*Decimal(925)/Decimal(300)
        self.assertEqual(expected,Decimal('18.5'))
        ws=self.output(blocks)['QC Dashboard']
        self.assertEqual(ws['O30'].value,f'{round(expected)} Defect-Equivalent Pcs')
        self.assertEqual(ws['T29'].value,f'{round(expected)} defect-equivalent pcs')
        preview=dashboard_preview(blocks)
        self.assertEqual(preview['comparison']['equivalent_findings'],ws['T29'].value)
        self.assertEqual(preview['comparison']['equivalent_calculation'],ws['T28'].value)
        self.assertEqual(preview['comparison']['inspection_factor'],expected/6)

    def test_existing_o30_allowlist_and_presentation_are_sufficient(self):
        manifest=json.loads(tpl.MANIFEST.read_text(encoding='utf-8'))
        self.assertIn('O30',tpl.DASH_DYNAMIC)
        self.assertIn('O30',manifest['dashboard_dynamic_cells'])
        blocks=self.blocks();wb=self.output(blocks)
        reference=openpyxl.load_workbook(tpl.ASSET);self.addCleanup(reference.close)
        self.assertEqual(copy(wb['QC Dashboard']['O30'].font),copy(reference['QC Dashboard']['O30'].font))
        self.assertEqual(copy(wb['QC Dashboard']['O30'].alignment),copy(reference['QC Dashboard']['O30'].alignment))
        self.assertEqual(copy(wb['QC Dashboard']['O30'].fill),copy(reference['QC Dashboard']['O30'].fill))
        self.assertEqual(tpl.dashboard_profile(wb['QC Dashboard']),tpl.dashboard_profile(reference['QC Dashboard']))
