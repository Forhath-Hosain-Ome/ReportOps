"""Monthly-layout authority, adversarial schemas and common-consumer regressions."""
import io
import os
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

import openpyxl
from django.test import SimpleTestCase, TransactionTestCase
from openpyxl.utils.cell import get_column_letter, range_boundaries

from inspection_summary import canonical as tpl
from inspection_summary.hundred_formats import ADAPTERS, detect_format, resolve_supported_mapping
from inspection_summary.models import InspectionSummaryJob as Job
from inspection_summary.parser import parse_inspection_workbook, semantic
from inspection_summary.preview import block_preview, build_preview, detail_preview, reconciliation_preview
from inspection_summary.raw_parser import parse_raw_workbook
from inspection_summary.report_data import dashboard_scope, ranked_groups, report_sheets
from inspection_summary.services import generate_job
from inspection_summary.workbook_security import WorkbookValidationError
from inspection_summary.writer import write_report, verify_report
from .helpers import JobFixture, raw_workbook, summary_workbook, upload
from .test_dynamic_contract import structured_workbook


def monthly_workbook(count=35):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'Unrelated current name'
    ws.merge_cells('A1:B3'); ws['A1'] = 'Arbitrary organization and reporting period'
    fields = {3:'Style NO.',4:'Iteam',5:'Person',6:'Inspection QTY',
              count+7:'Defect QTY',count+8:'Passed QTY',count+9:'Defect Ratio'}
    for col,label in fields.items():
        ws.merge_cells(start_row=1,start_column=col,end_row=3,end_column=col)
        ws.cell(1,col,label)
    split = count//2
    for lo,hi,label in [(7,6+split,'Panel group'),(7+split,6+count,'Assembly group')]:
        ws.merge_cells(start_row=1,start_column=lo,end_row=1,end_column=hi); ws.cell(1,lo,label)
    values = [1,2]+[0]*(count-3)+[3]
    for i in range(count):
        ws.cell(2,7+i,i+1)
        ws.cell(3,7+i,'Other' if i in (0,1,count-2,count-1) else f'Defect {i+1}')
    for row,day,style,person in [(5,date(2026,10,1),' Style ',52),(6,date(2026,10,1),'style',20),
                                 (9,date(2026,10,3),'Style-variant',None)]:
        ws.cell(row,1,f'=B{row}'); ws.cell(row,2,day); ws.cell(row,3,style)
        ws.cell(row,4,'Item'); ws.cell(row,5,person); ws.cell(row,6,100)
        for col,value in enumerate(values,7):
            if value: ws.cell(row,col,value)  # Complete numbered sparse schema.
        ws.cell(row,count+7,6); ws.cell(row,count+8,94); ws.cell(row,count+9,'=1/0')
    for row,day in [(4,None),(8,date(2026,10,2))]:
        ws.cell(row,1,f'=B{row}'); ws.cell(row,2,day)
        ws.cell(row,count+7,f'=SUM(G{row}:{get_column_letter(count+6)}{row})')
        ws.cell(row,count+8,f'=F{row}-{get_column_letter(count+7)}{row}')
    ws.merge_cells('A7:B7'); ws['A7']='Weekly Subtotal'
    ws.cell(7,6,'=SUM(F5:F6)'); ws.cell(7,count+7,'=1/0')
    ws['A10']='TOTAL'; ws.cell(10,6,300); ws.cell(10,count+7,18); ws.cell(10,count+8,282)
    for col,value in enumerate(values,7): ws.cell(10,col,value*3)
    ws['A12']='Top 5 Defect / Categories'
    ws['C13']='Defects Name'; ws['D13']='Defect Qty'; ws['E13']='Defects%'
    ws['C14']='Fabricated presentation winner'; ws['D14']='=1/0'; ws['F14']=999999
    ws.cell(1,count+17,'=1/0'); ws.cell(2,count+17,'=1/0')
    historical=wb.create_sheet('Historical first',0); historical['A1']='#REF!'; historical.sheet_state='hidden'
    wb.active=ws
    return wb


def cache_values(path, updates):
    """Write explicit formula caches for fixtures; never recalculate Excel."""
    with ZipFile(path) as package: parts={n:package.read(n) for n in package.namelist()}
    # The synthetic operational worksheet was created first, before the hidden one.
    name=tpl.sheet_parts(parts)['Unrelated current name']
    root=ET.fromstring(parts[name]); ns='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    for coordinate,value in updates.items():
        cell=root.find(f'.//{ns}c[@r="{coordinate}"]')
        node=cell.find(ns+'v')
        if node is not None: cell.remove(node)
        if value is not None: ET.SubElement(cell,ns+'v').text=str(value)
    parts[name]=ET.tostring(root)
    with ZipFile(path,'w',ZIP_DEFLATED) as package:
        for name,data in parts.items(): package.writestr(name,data)


class MonthlyTests(SimpleTestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)

    def save(self, wb):
        path=self.root/'arbitrary-name.xlsx'; wb.save(path); wb.close(); return path

    def parse(self, wb): return parse_raw_workbook(self.save(wb))

    def rejected(self, wb, code):
        with self.assertRaises(WorkbookValidationError) as caught: self.parse(wb)
        self.assertEqual(caught.exception.code,code)
        self.assertNotIn(str(self.root),str(caught.exception.detail))

    def test_dynamic_counts_all_fields_output_preview_top5_charts_and_print(self):
        for count in [28,35,37,42,60]:
            with self.subTest(count=count):
                wb=monthly_workbook(count); ws=wb['Unrelated current name']
                values=[7,6,4,4,3,2,2]+[1]*(count-7)
                for row in [5,6,9]:
                    for col,value in enumerate(values,7): ws.cell(row,col,value)
                    ws.cell(row,6,1000); ws.cell(row,count+7,sum(values)); ws.cell(row,count+8,1000-sum(values))
                ws.cell(10,6,3000);ws.cell(10,count+7,sum(values)*3);ws.cell(10,count+8,3000-sum(values)*3)
                for col,value in enumerate(values,7): ws.cell(10,col,value*3)
                mapping=resolve_supported_mapping(ws)
                self.assertEqual(detect_format(mapping,ws).name,'structured_monthly_100')
                self.assertEqual(sum(adapter.recognizes(mapping) for adapter in ADAPTERS),1)
                block=self.parse(wb)
                self.assertEqual(block.format,'structured_monthly_100')
                self.assertEqual(block.inspection_count,3);self.assertEqual(block.inspection_days,2)
                self.assertEqual(block.defect_totals,[v*3 for v in values])
                self.assertEqual([d.column for d in block.defect_schema],list(range(7,count+7)))
                self.assertEqual([d.source_number for d in block.defect_schema],list(range(1,count+1)))
                self.assertEqual([q for q,_ in ranked_groups(block)],[21,18,12,9,6])
                self.assertEqual([d.ordinal for _,members in ranked_groups(block) for d in members],list(range(1,8)))
                path=self.root/'Result.xlsx';write_report([block],path);verify_report(path,[block])
                result=openpyxl.load_workbook(path,data_only=True);self.addCleanup(result.close)
                self.assertEqual(result.sheetnames,['Analysis','Summary','100%'])
                detail=detail_preview(block);columns=[c for c in detail['columns'] if c['kind']=='defect']
                self.assertEqual(len(columns),count);self.assertEqual(len({c['key'] for c in columns}),count)
                self.assertEqual([c['source_number'] for c in columns],list(range(1,count+1)))
                out=result['100%'];end=count+4
                self.assertEqual([out.cell(2,c).value for c in range(5,end+1)],list(range(1,count+1)))
                self.assertEqual([out.cell(3,c).value for c in range(5,end+1)],[d.label for d in block.defect_schema])
                for row,preview_row in enumerate(detail['rows'],4):
                    actual=[out.cell(row,c).value for c in range(5,end+1)]
                    self.assertEqual(actual,[preview_row['values'][c['key']] for c in columns])
                for col,d in enumerate(block.defect_schema,5):
                    band=next((r for r in out.merged_cells if r.min_row==r.max_row==1 and r.min_col<=col<=r.max_col),None)
                    self.assertEqual(semantic(out.cell(1,band.min_col if band else col).value),semantic(d.category))
                formulas=[]
                for name,data in tpl.read_package(path).items():
                    if '/charts/' in name and name.endswith('.xml'):
                        formulas.extend(n.text for n in tpl.parse(data).findall('.//c:f',tpl.NS)
                                        if n.text and n.text.startswith("'100%'!$E$"))
                self.assertEqual(len(formulas),2)
                self.assertTrue(all(f':${get_column_letter(end)}$' in f for f in formulas))
                self.assertGreaterEqual(range_boundaries(str(out.print_area).split(',')[0].split('!')[-1])[2],end+3)
                for mode,denom in [('analysis',block.inspected_qty),('summary',block.defect_qty)]:
                    p=block_preview(block,0,mode)
                    self.assertAlmostEqual(float(p['top_defects'][0]['ratio']),21/denom)
                    self.assertEqual('manpower' in p,mode=='analysis')
                self.assertTrue(reconciliation_preview(block)['defect_matches_categories'])

    def test_duplicate_labels_blank_policy_personnel_and_presentation_exclusion(self):
        block=self.parse(monthly_workbook())
        other=[d for d in block.defect_schema if d.label=='Other']
        self.assertEqual([d.occurrence for d in other],[1,2,1,2])
        self.assertEqual([block.defect_totals[d.ordinal-1] for d in other],[3,6,0,9])
        self.assertEqual(block.inspected_qty,300);self.assertEqual(block.defect_qty,18)
        self.assertEqual(block.pass_qty,282);self.assertEqual(block.personnel,['52','20'])
        self.assertTrue(block.blank_defects_are_zero)
        p=block_preview(block,0,'analysis')
        self.assertEqual(p['manpower']['entries'][0]['values'],['52','20'])
        self.assertIsNone(p['manpower']['aggregate_persons'])
        self.assertIsNone(p['manpower']['entries'][1]['values'][0])
        self.assertNotIn('manpower',block_preview(block,0,'summary'))
        self.assertNotIn('Fabricated presentation winner',[d.label for d in block.defect_schema])

    def test_bad_numbering_categories_labels_and_quantities_fail_closed(self):
        for marker in [None,True,'1',2,0,1.5]:
            wb=monthly_workbook();wb['Unrelated current name']['G2']=marker
            self.rejected(wb,'DEFECT_NUMBERING_INVALID')
        wb=monthly_workbook();wb['Unrelated current name']['G3']=None;self.rejected(wb,'DEFECT_COLUMN_INVALID')
        wb=monthly_workbook();ws=wb['Unrelated current name'];ws.unmerge_cells('G1:W1');ws['G1']=None
        self.rejected(wb,'DEFECT_COLUMN_INVALID')
        for value in [-1,True,0.5,'invalid']:
            wb=monthly_workbook();wb['Unrelated current name']['G5']=value
            self.rejected(wb,'DEFECT_QUANTITY_INVALID')
        for coordinate,value,code in [('AP5',7,'DEFECT_TOTAL_MISMATCH'),('AQ5',1,'DEFECT_TOTAL_MISMATCH'),
                                       ('B5','10/01/26','INVALID_INSPECTION_DATE'),('C5',None,'REQUIRED_VALUE_MISSING'),
                                       ('F5',None,'REQUIRED_VALUE_MISSING'),('AP10',19,'DEFECT_TOTAL_MISMATCH'),
                                       ('G10',4,'DEFECT_TOTAL_MISMATCH')]:
            wb=monthly_workbook();wb['Unrelated current name'][coordinate]=value;self.rejected(wb,code)

    def test_cached_detail_formulas_required_and_source_total_caches_are_verification_only(self):
        wb=monthly_workbook();ws=wb['Unrelated current name']
        ws['AP5']='=SUM(G5:AO5)';ws['AQ5']='=F5-AP5';ws['AP10']='=SUM(AP5:AP9)'
        path=self.save(wb)
        cache_values(path,{'AP5':6,'AQ5':94,'AP10':18})
        self.assertEqual(parse_raw_workbook(path).defect_qty,18)
        cache_values(path,{'AP10':None})
        self.assertEqual(parse_raw_workbook(path).defect_qty,18)
        cache_values(path,{'AP10':19})
        with self.assertRaises(WorkbookValidationError) as caught:parse_raw_workbook(path)
        self.assertEqual(caught.exception.code,'DEFECT_TOTAL_MISMATCH')
        cache_values(path,{'AP10':18,'AP5':None})
        with self.assertRaises(WorkbookValidationError) as caught:parse_raw_workbook(path)
        self.assertEqual(caught.exception.code,'FORMULA_VALUE_UNAVAILABLE')

    def test_unclassified_columns_are_not_silently_dropped(self):
        for coordinate,value,code in [('AZ3','Extra defect','DEFECT_COLUMN_INVALID'),
                                       ('AZ5',1,'DEFECT_COLUMN_INVALID'),
                                       ('AZ2',36,'DEFECT_NUMBERING_INVALID')]:
            wb=monthly_workbook();wb['Unrelated current name'][coordinate]=value
            self.rejected(wb,code)

    def test_category_formulas_and_adapter_ambiguity_are_rejected(self):
        wb=monthly_workbook();wb['Unrelated current name']['G1']='=1+1'
        self.rejected(wb,'DEFECT_COLUMN_INVALID')
        wb=monthly_workbook();ws=wb['Unrelated current name'];mapping=resolve_supported_mapping(ws)
        with patch.object(ADAPTERS[0],'recognizes',return_value=True):
            with self.assertRaises(WorkbookValidationError) as caught:detect_format(mapping,ws)
        self.assertEqual(caught.exception.code,'AMBIGUOUS_100_FORMAT')
        wb.close()
        wb=monthly_workbook()
        from inspection_summary.monthly_100 import StructuredMonthly100Adapter
        with patch.object(StructuredMonthly100Adapter,'blank_defects_are_zero',False):
            self.rejected(wb,'DEFECT_QUANTITY_INVALID')

    def test_visible_authority_ambiguity_missing_boundary_and_raw_disjointness(self):
        wb=monthly_workbook();wb.copy_worksheet(wb['Unrelated current name'])
        self.rejected(wb,'AMBIGUOUS_100_FORMAT')
        wb=monthly_workbook();wb['Unrelated current name']['A10']=None
        self.rejected(wb,'DEFECT_SCHEMA_UNRECOGNIZED')
        wb=monthly_workbook();wb['Unrelated current name']['A11']='TOTAL'
        self.rejected(wb,'AMBIGUOUS_100_FORMAT')
        for wb,expected in [(raw_workbook(),'raw'),(structured_workbook(),'structured')]:
            mapping=resolve_supported_mapping(wb.active)
            self.assertEqual(detect_format(mapping,wb.active).name,expected)
            self.assertEqual(sum(a.recognizes(mapping) for a in ADAPTERS),1)
            self.assertEqual(self.parse(wb).format,expected)
        wb=raw_workbook();wb.active['D3']='Iteam'
        self.rejected(wb,'UNSUPPORTED_100_FORMAT')

    def test_qc_exact_matching_remains_case_sensitive_trim_only_and_duplicates_contribute(self):
        summary=summary_workbook();summary.save(self.root/'summary.xlsx');summary.close()
        monthly=self.save(monthly_workbook())
        blocks=parse_inspection_workbook(self.root/'summary.xlsx',monthly)
        styles,final,hundred=dashboard_scope(blocks)
        self.assertEqual(styles,['Style']);self.assertEqual(final.inspected_qty,200)
        self.assertEqual(hundred.inspected_qty,100)
        self.assertEqual(report_sheets(blocks),['QC Dashboard','Analysis','Summary','100%'])

    def test_supplied_monthly_fixture_independent_detail_totals_and_output(self):
        source=os.environ.get('INSPECTION_SUMMARY_MONTHLY_FILE')
        if not source:self.skipTest('External supplied monthly workbook required; never commit business data.')
        block=parse_raw_workbook(Path(source))
        self.assertEqual(block.format,'structured_monthly_100')
        self.assertEqual((block.inspection_count,block.inspection_days,len(block.styles)),(34,16,3))
        self.assertEqual((block.inspected_qty,block.pass_qty,block.defect_qty),(37874,28249,9625))
        self.assertEqual(len(block.defect_schema),35);self.assertEqual(len({d.category for d in block.defect_schema}),5)
        wb=openpyxl.load_workbook(source,data_only=True,keep_links=False);ws=wb['100%']
        expected=[row for row in ws.iter_rows(min_row=4,max_row=61,values_only=True)
                  if row[2] is not None and isinstance(row[5],(int,float))]
        self.assertEqual(len(expected),34)
        self.assertEqual([r['categories'] for r in block.records],[[v or 0 for v in row[6:41]] for row in expected])
        self.assertEqual(sum(row[5] for row in expected),37874)
        self.assertEqual(sum(sum(v or 0 for v in row[6:41]) for row in expected),9625)
        wb.close()
        path=self.root/'actual-monthly.xlsx';write_report([block],path);verify_report(path,[block])
        output=openpyxl.load_workbook(path,data_only=True);self.assertEqual(output.sheetnames,['Analysis','Summary','100%']);output.close()


class MonthlyApiTests(TransactionTestCase):
    def setUp(self):JobFixture.setUp(self)

    def test_monthly_source_matrix_preview_download_and_owner_boundary(self):
        for summary_name in [None,'Final','Random']:
            with self.subTest(summary=summary_name):
                payload={'hundred_percent':upload(monthly_workbook(60))}
                if summary_name:
                    wb=summary_workbook();wb.active.title=summary_name;payload['inspection_summary']=upload(wb)
                with patch('inspection_summary.services.publish_inspection_summary_job'):
                    response=self.client.post('/inspection-summary/jobs/',payload,format='multipart')
                self.assertEqual(response.status_code,202,response.data)
                job=Job.objects.get(pk=response.data['job_id']);job.dispatch_state=job.Dispatch.QUEUED;job.save(update_fields=['dispatch_state'])
                generate_job(job.pk,job.dispatch_generation,str(job.dispatch_token));job.refresh_from_db()
                self.assertEqual(job.status,'COMPLETED',job.error_detail)
                response=self.client.get(f'/inspection-summary/jobs/{job.pk}/preview/')
                self.assertEqual(response.status_code,200,response.data)
                self.assertEqual(response.data['sources']['hundred_percent_format'],'structured_monthly_100')
                self.assertEqual(response.data['available_sections']['qc_dashboard'],summary_name=='Final')
                self.assertEqual(response.data['reconciliation']['defect_field_count'],60)
                self.assertEqual(response.data['detail']['record_count'],3)
                self.assertEqual(len([c for c in response.data['detail']['columns'] if c['kind']=='defect']),60)
                self.assertTrue(all(c.get('source_number')==c['ordinal'] for c in response.data['detail']['columns'] if c['kind']=='defect'))
                result=self.client.get(f'/inspection-summary/jobs/{job.pk}/download/')
                data=b''.join(result.streaming_content);result.close()
                wb=openpyxl.load_workbook(io.BytesIO(data));self.assertEqual(wb.sheetnames,response.data['overview']['sections']);wb.close()
                self.client.force_authenticate(self.other)
                self.assertEqual(self.client.get(f'/inspection-summary/jobs/{job.pk}/preview/').status_code,404)
                self.client.force_authenticate(self.user)
