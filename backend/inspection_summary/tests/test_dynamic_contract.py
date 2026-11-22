"""Independent dynamic-schema, quantity-preservation and optional-source gates."""
import io
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import openpyxl
from django.test import SimpleTestCase, TransactionTestCase
from django.utils import timezone
from openpyxl.utils.cell import get_column_letter, range_boundaries

from inspection_summary import canonical as tpl, storage
from inspection_summary.models import InspectionSummaryJob as Job
from inspection_summary.parser import parse_inspection_workbook, semantic
from inspection_summary.preview import block_preview, detail_preview, reconciliation_preview
from inspection_summary.raw_parser import parse_raw_workbook
from inspection_summary.report_data import ranked_groups
from inspection_summary.services import cleanup_expired_jobs, generate_job, validated_inputs
from inspection_summary.workbook_security import WorkbookValidationError
from inspection_summary.writer import write_report, verify_report
from .helpers import JobFixture, ordinary, raw_workbook, summary_workbook, upload


def structured_workbook(count=37, *, numbered=True, repeated=True):
    """Result quantities follow the defects: a tail-N mapping would lose data."""
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'Unrelated name'
    headers = ['Factory Name','Inspection Date','Style No','Item Name','Inspectors']
    labels = ['Other' if repeated and i in (0,1,count-1) else f'Field {i+1}' for i in range(count)]
    headers += labels + ['Inspection Qty','Pass Qty','Defect Qty']
    for col, value in enumerate(headers,1): ws.cell(3,col,value)
    split = count//2
    for start,end,label in [(6,5+split,'Material Defects'),(6+split,5+count,'Sewing Defects')]:
        ws.merge_cells(start_row=1,start_column=start,end_row=1,end_column=end)
        ws.cell(1,start,label)
    if numbered:
        for i in range(count): ws.cell(2,6+i,i+1)
    for row,day,person in [(4,'2026-10-01',52),(5,'2026-10-03',20)]:
        quantities=[1,2]+[0]*(count-3)+[3]
        for col,value in enumerate(['Factory',day,'Style','Item',person]+quantities+[100,94,6],1):
            ws.cell(row,col,value)
    return wb


class DynamicSchemaTests(SimpleTestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)

    def parse(self,wb):
        path=self.root/'arbitrary.xlsx'; wb.save(path); wb.close(); return parse_raw_workbook(path)

    def rejected(self,wb,code):
        with self.assertRaises(WorkbookValidationError) as caught: self.parse(wb)
        self.assertEqual(caught.exception.code,code)

    def test_raw_and_structured_counts_output_preview_and_independent_bounds(self):
        for count in [28,35,37,42,60]:
            for format_name,source in [('raw',raw_workbook(categories=count)),('structured',structured_workbook(count))]:
                with self.subTest(count=count,format=format_name):
                    block=self.parse(source)
                    self.assertEqual(block.format,format_name)
                    self.assertEqual(len(block.defect_schema),count)
                    self.assertEqual([d.ordinal for d in block.defect_schema],list(range(1,count+1)))
                    self.assertEqual([d.column for d in block.defect_schema],sorted(d.column for d in block.defect_schema))
                    self.assertEqual(sum(block.defect_totals),block.defect_qty)
                    out=self.root/'Result.xlsx'; write_report([block],out); verify_report(out,[block])
                    wb=openpyxl.load_workbook(out,data_only=True); self.addCleanup(wb.close)
                    self.assertEqual(wb.sheetnames,['Analysis','Summary','100%'])
                    ws=wb['100%']; end=4+count
                    self.assertEqual([ws.cell(2,c).value for c in range(5,end+1)],list(range(1,count+1)))
                    self.assertEqual([ws.cell(3,c).value for c in range(5,end+1)],[d.label for d in block.defect_schema])
                    self.assertIsNone(ws.cell(2,end+1).value)
                    for c,d in enumerate(block.defect_schema,5):
                        band=next((r for r in ws.merged_cells if r.min_row==r.max_row==1 and r.min_col<=c<=r.max_col),None)
                        self.assertEqual(semantic(ws.cell(1,band.min_col if band else c).value),semantic(d.category))
                    preview=detail_preview(block)
                    defects=[c for c in preview['columns'] if c['kind']=='defect']
                    self.assertEqual(len(defects),count)
                    self.assertEqual(len({c['key'] for c in defects}),count)
                    details=[r for r in preview['rows'] if r['kind']=='detail']
                    totals=[r for r in preview['rows'] if r['kind']=='total']
                    for r,source_row in zip(details,block.raw_rows):
                        self.assertEqual([r['values'][c['key']] for c in defects],[source_row[d.column-1] for d in block.defect_schema])
                    self.assertEqual([totals[0]['values'][c['key']] for c in defects],block.defect_totals)
                    for number,row in enumerate(preview['rows'],4):
                        self.assertEqual([ws.cell(number,c).value for c in range(5,end+1)],[row['values'][c['key']] for c in defects])
                    self.assertEqual(ws.freeze_panes,'E4')
                    self.assertGreaterEqual(max(range_boundaries(r.split('!')[-1])[2] for r in str(ws.print_area).split(',')),end+3)
                    self.assertEqual(len(ws._charts),2)
                    parts=tpl.read_package(out); ranges=[]
                    app=tpl.parse(parts['docProps/app.xml'])
                    ns={'p':'http://schemas.openxmlformats.org/officeDocument/2006/extended-properties','v':'http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes'}
                    self.assertEqual([n.text for n in app.findall('p:HeadingPairs/v:vector/v:variant/v:lpstr',ns)],['Worksheets'])
                    self.assertEqual([n.text for n in app.findall('p:HeadingPairs/v:vector/v:variant/v:i4',ns)],['3'])
                    self.assertEqual([n.text for n in app.findall('p:TitlesOfParts/v:vector/v:lpstr',ns)],wb.sheetnames)
                    for name,data in parts.items():
                        if '/charts/' in name and name.endswith('.xml'):
                            chart=tpl.parse(data)
                            ranges += [n.text for n in chart.findall('.//c:f',tpl.NS) if n.text and "'100%'!$E$" in n.text]
                    self.assertEqual(len(ranges),2)
                    self.assertTrue(all(f':${get_column_letter(end)}$' in r for r in ranges))
                    r=reconciliation_preview(block)
                    self.assertEqual(r['defect_field_count'],count); self.assertTrue(r['defect_matches_categories'])
                    for mode,denom in [('analysis',block.inspected_qty),('summary',block.defect_qty)]:
                        p=block_preview(block,0,mode)
                        self.assertAlmostEqual(float(p['top_defects'][0]['ratio']),p['top_defects'][0]['quantity']/denom)
                        self.assertEqual('manpower' in p,mode=='analysis')

    def test_total_as_business_text_is_not_a_subtotal_marker(self):
        wb=structured_workbook()
        for col in [1,3,4]: wb.active.cell(4,col,'Total')
        block=self.parse(wb)
        self.assertEqual(block.inspection_count,2)
        self.assertEqual(block.defect_qty,12)

    def test_optional_factory_and_pass_headers_do_not_shift_defects(self):
        wb=structured_workbook()
        # Delete the result Pass column and the Factory column with openpyxl's
        # merge-coordinate adjustment made explicit in this synthetic source.
        ws=wb.active
        for band in list(ws.merged_cells): ws.unmerge_cells(str(band))
        ws.delete_cols(44); ws.delete_cols(1)
        ws.merge_cells('E1:V1');ws['E1']='Material Defects'
        ws.merge_cells('W1:AO1');ws['W1']='Sewing Defects'
        block=self.parse(wb)
        self.assertIsNone(block.pass_qty);self.assertEqual(block.factories,[])
        out=self.root/'optional.xlsx';write_report([block],out);verify_report(out,[block])
        self.assertEqual(block.defect_qty,12)

    def test_five_distinct_ranks_and_all_ties_for_every_dynamic_count(self):
        for count in [28,35,37,42,60]:
            wb=structured_workbook(count);ws=wb.active
            values=[7,6,4,4,3,2,2]+[1]*(count-7)
            for row in [4,5]:
                for col,qty in enumerate(values,6):ws.cell(row,col,qty)
                ws.cell(row,count+8,sum(values))
            block=self.parse(wb);groups=ranked_groups(block)
            self.assertEqual([q for q,_ in groups],[14,12,8,6,4])
            self.assertEqual([d.ordinal for _,members in groups for d in members],list(range(1,8)))

    def test_repeated_labels_across_and_inside_categories_remain_distinct(self):
        block=self.parse(structured_workbook())
        other=[d for d in block.defect_schema if d.label=='Other']
        self.assertEqual([(d.column,d.ordinal,d.occurrence) for d in other],[(6,1,1),(7,2,2),(42,37,1)])
        self.assertEqual([block.defect_totals[d.ordinal-1] for d in other],[2,4,6])
        self.assertEqual([members[0].ordinal for _,members in ranked_groups(block)],[37,2,1])

    def test_numbered_sparse_and_dense_no_number_policies(self):
        for numbered in [True,False]:
            wb=structured_workbook(numbered=numbered); wb.active.cell(4,8).value=None
            if numbered: self.assertEqual(self.parse(wb).records[0]['categories'][2],0)
            else: self.rejected(wb,'DEFECT_QUANTITY_INVALID')
        self.assertFalse(self.parse(structured_workbook(numbered=False)).blank_defects_are_zero)

    def test_bad_numbering_ambiguous_tables_unmapped_columns_and_quantities(self):
        for marker in [None,True,'1',0,2,1.5]:
            wb=structured_workbook(); wb.active.cell(2,6).value=marker
            self.rejected(wb,'DEFECT_NUMBERING_INVALID')
        for value in ['bad',-1,0.5,True]:
            wb=structured_workbook(); wb.active.cell(4,8).value=value
            self.rejected(wb,'DEFECT_QUANTITY_INVALID')
        for total in [5,7]:
            wb=structured_workbook(); wb.active.cell(4,45,total)
            self.rejected(wb,'DEFECT_TOTAL_MISMATCH')
        wb=structured_workbook(); wb.copy_worksheet(wb.active); self.rejected(wb,'AMBIGUOUS_100_FORMAT')
        wb=structured_workbook(); wb.active.cell(3,46,'Unknown'); self.rejected(wb,'DEFECT_COLUMN_INVALID')
        wb=structured_workbook(); wb.active.cell(4,46,1); self.rejected(wb,'DEFECT_COLUMN_INVALID')
        wb=structured_workbook(); wb.active.cell(3,8).value=None; self.rejected(wb,'DEFECT_COLUMN_INVALID')
        wb=openpyxl.Workbook(); wb.active['A1']='Unsupported'; self.rejected(wb,'UNSUPPORTED_100_FORMAT')


class OptionalSourceApiTests(TransactionTestCase):
    def setUp(self): JobFixture.setUp(self)

    def post(self,payload):
        with patch('inspection_summary.services.publish_inspection_summary_job'):
            return self.client.post('/inspection-summary/jobs/',payload,format='multipart')

    def complete(self,payload):
        response=self.post(payload); self.assertEqual(response.status_code,202,response.data)
        job=Job.objects.get(pk=response.data['job_id']); job.dispatch_state=job.Dispatch.QUEUED; job.save(update_fields=['dispatch_state'])
        generate_job(job.pk,job.dispatch_generation,str(job.dispatch_token)); job.refresh_from_db()
        self.assertEqual(job.status,'COMPLETED',job.error_detail)
        return job

    def test_conditional_source_and_format_matrix_preview_download_and_retention(self):
        cases=[('summary',True,None,False),('raw',False,'raw',False),('structured',False,'structured',False),
               ('both',True,'structured',True),('no-final',True,'structured',False),('legacy',True,'raw',True)]
        for name,summary,format_name,dashboard in cases:
            with self.subTest(case=name):
                payload={}
                if summary:
                    wb=summary_workbook()
                    if name=='no-final': wb.active.title='Random'
                    payload['inspection_summary']=upload(wb)
                if format_name:
                    payload['raw' if name=='legacy' else 'hundred_percent']=upload(raw_workbook() if format_name=='raw' else structured_workbook())
                job=self.complete(payload)
                paths=validated_inputs(job); self.assertEqual([p is not None for p in paths],[summary,format_name is not None])
                preview=self.client.get(f'/inspection-summary/jobs/{job.pk}/preview/')
                self.assertEqual(preview.status_code,200,preview.data)
                p=preview.data
                self.assertEqual(p['available_sections'],dict(qc_dashboard=dashboard,analysis=True,summary=True,detail_100=format_name is not None))
                self.assertEqual(p['sources'],dict(inspection_summary=summary,hundred_percent=format_name is not None,hundred_percent_format=format_name))
                self.assertEqual(p['dashboard'] is not None,dashboard)
                self.assertEqual(p['detail'] is not None,format_name is not None)
                self.assertEqual([b['report_type'] for b in p['analysis']],[b['report_type'] for b in p['summary']])
                response=self.client.get(f'/inspection-summary/jobs/{job.pk}/download/')
                self.assertEqual(response.status_code,200)
                contents=b''.join(response.streaming_content); response.close()
                wb=openpyxl.load_workbook(io.BytesIO(contents)); self.assertEqual(wb.sheetnames,p['overview']['sections']); wb.close()
                self.client.force_authenticate(self.other)
                self.assertEqual(self.client.get(f'/inspection-summary/jobs/{job.pk}/preview/').status_code,404)
                self.client.force_authenticate(self.user)
                Job.objects.filter(pk=job.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
                self.assertEqual(self.client.get(f'/inspection-summary/jobs/{job.pk}/preview/').status_code,410)
                self.assertEqual(cleanup_expired_jobs()['errors'],0)
                job.refresh_from_db(); self.assertIsNotNone(job.input_deleted_at); self.assertIsNotNone(job.output_deleted_at)
                self.assertFalse(storage.input_path(job.pk,'raw').exists()); self.assertFalse(storage.input_path(job.pk,'inspection_summary').exists())

    def test_none_duplicate_unknown_and_conflicting_alias_are_rejected(self):
        for payload in [{},{'unknown':upload(raw_workbook())},{'hundred_percent':[upload(raw_workbook()),upload(raw_workbook())]},
                        {'raw':upload(raw_workbook()),'hundred_percent':upload(raw_workbook())},
                        {'hundred_percent':[upload(raw_workbook()),'unexpected text']},
                        {'inspection_summary':[upload(summary_workbook()),upload(summary_workbook())]},
                        {'inspection_summary':upload(summary_workbook()),'extra':'unrecognized'}]:
            with self.subTest(fields=list(payload)):
                response=self.post(payload); self.assertEqual(response.status_code,400,response.data)
        self.assertIn('At least one Inspection Summary or 100% workbook is required.',str(self.post({}).data))
        self.assertEqual(Job.objects.count(),0)

    def test_omitted_authority_cannot_be_forged_by_partial_persisted_identity(self):
        job=self.complete({'hundred_percent':upload(structured_workbook())})
        job.inspection_summary_name='forged.xlsx'
        with self.assertRaises(ValueError): validated_inputs(job)
