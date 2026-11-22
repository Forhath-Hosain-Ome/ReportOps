"""Preview boundary, source authority and workbook parity regressions."""
import hashlib
import json
import os
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import openpyxl
from django.utils import timezone
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from inspection_summary import storage
from inspection_summary.models import InspectionSummaryJob as Job
from inspection_summary.parser import DefectColumn, parse_inspection_workbook
from inspection_summary.preview import (block_preview, build_preview, dashboard_preview,
    detail_preview, reconciliation_preview)
from inspection_summary.report_data import dashboard_scope, manpower, ranked_groups
from inspection_summary.services import create_job, generate_job
from .helpers import JobFixture, raw_workbook, reference_summary, summary_workbook, upload
from .test_writer import WorkbookWriterFixture


class PreviewApiTests(TransactionTestCase):
    # Streaming response.close emits request_finished. Real committed transactions
    # keep connection cleanup valid on PostgreSQL as well as SQLite.
    def setUp(self):
        JobFixture.setUp(self)

    def make_job(self):
        with patch('inspection_summary.services.publish_inspection_summary_job'):
            job = create_job(self.user, upload(summary_workbook()), upload(raw_workbook()))
        job.dispatch_state = job.Dispatch.QUEUED
        job.save(update_fields=['dispatch_state'])
        return job

    def complete(self):
        job = self.make_job()
        generate_job(job.pk, job.dispatch_generation, str(job.dispatch_token))
        job.refresh_from_db()
        return job

    def url(self, job):
        return f"/inspection-summary/jobs/{job.pk}/preview/"

    def test_completed_owner_preview_is_read_only_and_not_cached(self):
        job = self.complete()
        before = Job.objects.values().get(pk=job.pk)
        checksums = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in storage.job_root(job.pk).rglob('*') if p.is_file()}
        with patch('inspection_summary.tasks.generate_inspection_summary.apply_async') as dispatch, patch('inspection_summary.services.write_report') as writer:
            response = self.client.get(self.url(job))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(set(response.data), {'job', 'overview', 'dashboard', 'analysis', 'summary', 'detail', 'reconciliation', 'available_sections', 'sources'})
        self.assertEqual(response.data['job']['job_id'], str(job.pk))
        self.assertTrue(response.data['job']['download_ready'])
        self.assertEqual(Job.objects.values().get(pk=job.pk), before)
        self.assertEqual(checksums, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in checksums})
        dispatch.assert_not_called(); writer.assert_not_called()
        self.assertNotIn(str(self.media), response.content.decode())
        self.assertEqual([b['id'] for b in response.data['analysis']], [b['id'] for b in response.data['summary']])
        self.assertFalse(any('manpower' in b for b in response.data['summary']))

    def test_authentication_owner_and_missing_job(self):
        job = self.complete()
        self.assertEqual(APIClient().get(self.url(job)).status_code, 401)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url(job)).status_code, 404)
        self.assertEqual(self.client.get('/inspection-summary/jobs/00000000-0000-0000-0000-000000000000/preview/').status_code, 404)

    def test_incomplete_states_are_409_and_expiry_is_410(self):
        job = self.make_job()
        for status in ['PENDING', 'PROCESSING', 'FAILED']:
            Job.objects.filter(pk=job.pk).update(status=status)
            self.assertEqual(self.client.get(self.url(job)).status_code, 409)
        Job.objects.filter(pk=job.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.client.get(self.url(job)).status_code, 410)

    def test_missing_output_or_input_is_404(self):
        for missing in ['output', 'input']:
            job = self.complete()
            (storage.output_path(job.pk) if missing == 'output' else storage.input_path(job.pk, 'raw')).unlink()
            response = self.client.get(self.url(job))
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.data['code'], 'PREVIEW_UNAVAILABLE')
            self.assertNotIn(str(self.media), response.content.decode())

    def test_changed_input_and_foreign_output_authority_rejected(self):
        job = self.complete()
        storage.input_path(job.pk, 'raw').write_bytes(b'changed')
        self.assertEqual(self.client.get(self.url(job)).status_code, 404)
        other = self.complete()
        Job.objects.filter(pk=job.pk).update(output_path=other.output_path)
        self.assertEqual(self.client.get(self.url(job)).status_code, 404)

    def test_corrupt_output_and_deleted_authority_rejected(self):
        job = self.complete()
        original = storage.output_path(job.pk).read_bytes()
        storage.output_path(job.pk).write_bytes(b'not a workbook')
        self.assertEqual(self.client.get(self.url(job)).status_code, 404)
        storage.output_path(job.pk).write_bytes(original)
        for field in ['input_deleted_at', 'output_deleted_at']:
            Job.objects.filter(pk=job.pk).update(**{field: timezone.now()})
            self.assertEqual(self.client.get(self.url(job)).status_code, 404)
            Job.objects.filter(pk=job.pk).update(**{field: None})

    def test_internal_error_is_sanitized_and_download_survives(self):
        job = self.complete()
        with patch('inspection_summary.preview.build_preview', side_effect=RuntimeError('secret C:/private/report.xlsx')):
            response = self.client.get(self.url(job))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('secret', response.content.decode())
        result = self.client.get(f'/inspection-summary/jobs/{job.pk}/download/')
        self.assertEqual(result.status_code, 200); result.close()

    def test_expiry_during_read_fails_closed(self):
        job = self.complete()
        def expire(current):
            result = build_preview(current)
            Job.objects.filter(pk=current.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
            return result
        with patch('inspection_summary.preview.build_preview', side_effect=expire):
            self.assertEqual(self.client.get(self.url(job)).status_code, 410)


class PreviewParityTests(WorkbookWriterFixture):
    def check_parity(self, blocks):
        wb = openpyxl.load_workbook(self.output(blocks), data_only=True)
        try:
            for index, block in enumerate(blocks):
                for sheet, mode, prefix in [('Analysis', 'analysis', 'AnalysisBlock_'), ('Summary', 'summary', 'InspectionBlock_')]:
                    preview = block_preview(block, index, mode)
                    start = wb[sheet][list(wb.defined_names[prefix + f'{index:03d}'].destinations)[0][1]].row
                    header = next(r for r in range(start, start+7) if wb[sheet].cell(r,3).value == 'Categories')
                    for offset, group in enumerate(preview['top_defects'], header+1):
                        self.assertEqual(group['quantity'], wb[sheet].cell(offset,5).value)
                        expected = wb[sheet].cell(offset,6).value
                        if expected is None: self.assertIsNone(group['ratio'])
                        else: self.assertAlmostEqual(float(group['ratio']), expected, places=12)
                    self.assertEqual(len(preview['top_defects']), len(ranked_groups(block)) if not block.empty_state else 0)
            raw = next(b for b in blocks if b.kind == 'raw')
            preview = detail_preview(raw)
            for number, row in enumerate(preview['rows'], 4):
                for col, actual in enumerate(row['values'].values(), 1):
                    expected = wb['100%'].cell(number,col).value
                    if hasattr(expected, 'date'): expected = expected.date()
                    if hasattr(expected, 'isoformat'): expected = expected.isoformat()
                    self.assertEqual(actual, expected)
            self.assertEqual(preview['record_count'], len(raw.raw_rows))
            self.assertEqual([c['number'] for c in preview['columns'] if c['number']], list(range(1,36)))
            self.assertEqual([c['label'] for c in preview['columns'] if c['number']], [d.label for d in raw.defect_schema])
            dashboard = dashboard_preview(blocks)
            self.assertEqual(dashboard['matched_styles'], dashboard_scope(blocks)[0])
            if dashboard['final_available']:
                self.assertEqual(dashboard['team_100']['inspected_qty'], wb['QC Dashboard']['G9'].value)
                self.assertEqual(dashboard['final']['inspected_qty'], wb['QC Dashboard']['W9'].value)
            return wb
        finally: wb.close()

    def test_all_blocks_detail_ratios_and_manpower_match_workbook(self):
        raw = raw_workbook(); raw.active.cell(5,8,52); raw.active.cell(6,8,20)
        raw.active.cell(5,2,'2026-10-05'); raw.active.cell(6,2,'2026-10-05')
        blocks = self.blocks(['Final','Re-Final','Random','INLINE-SPL','INLINE'], raw=raw)
        self.check_parity(blocks)
        a = block_preview(blocks[-1], len(blocks)-1, 'analysis')
        self.assertEqual(a['manpower']['entries'], [{'date': day, 'values': vals} for day, vals in manpower(blocks[-1])])
        self.assertEqual(a['manpower']['entries'][-1]['values'], ['52','20'])
        self.assertIsNone(a['manpower']['aggregate_persons'])
        self.assertNotIn('manpower', block_preview(blocks[-1], 0, 'summary'))

    def test_ties_and_missing_values_preserved(self):
        blocks = self.blocks(); block = blocks[0]
        block.defect_schema = [DefectColumn(i+1,'A',f'Defect {i}') for i in range(9)]
        block.defect_totals = [7,6,4,4,3,2,2,1,None]
        groups = block_preview(block,0,'analysis')['top_defects']
        self.assertEqual([g['quantity'] for g in groups], [7,6,4,3,2])
        self.assertEqual([d['label'] for d in groups[2]['defects']], ['Defect 2','Defect 3'])
        block.inspected_qty = None
        self.assertIsNone(block_preview(block,0,'analysis')['top_defects'][0]['ratio'])
        raw = raw_workbook(); raw.active.cell(5,6).value = None
        r = reconciliation_preview(self.blocks(raw=raw)[-1])
        self.assertIsNone(r['pass_qty']); self.assertTrue(r['pass_matches_detail'])

    def test_no_match_and_absent_final_and_empty_blocks(self):
        blocks = self.blocks(['Final','Empty'], empty=['Empty'])
        blocks[0].records[0]['style'] = 'Style-suffix'
        blocks[0].records[1]['style'] = 'style'
        d = dashboard_preview(blocks)
        self.assertEqual(d['matched_styles'], [])
        self.assertEqual(d['team_100']['inspected_qty'],0)
        self.assertIsNone(d['team_100']['defect_ratio'])
        self.assertIsNone(d['comparison']['inspection_factor'])
        self.assertEqual(block_preview(blocks[1],1,'analysis')['top_defects'], [])
        self.assertIsNone(dashboard_preview(blocks[1:])['final']['inspected_qty'])

    def test_real_reference_preview_workbook_acceptance(self):
        folder = os.environ.get('INSPECTION_SUMMARY_REFERENCE_DIR')
        if not folder: self.skipTest('External business files required; never commit them.')
        blocks = parse_inspection_workbook(reference_summary(folder),Path(folder)/'Raw.xlsx')
        self.check_parity(blocks)
        final = next(b for b in blocks if b.report_name == 'Final'); raw = blocks[-1]
        for block, quantity, inspected, defects in [(final,7,2120,36),(raw,5020,156132,16575)]:
            a = block_preview(block,0,'analysis'); s = block_preview(block,0,'summary')
            self.assertEqual(a['top_defects'][0]['quantity'], quantity)
            self.assertAlmostEqual(float(a['top_defects'][0]['ratio']),quantity/inspected,places=12)
            self.assertAlmostEqual(float(s['top_defects'][0]['ratio']),quantity/defects,places=12)
        r = reconciliation_preview(raw)
        self.assertEqual([r[k] for k in ['inspection_qty','pass_qty','defect_qty','defect_category_total','record_count','inspection_day_count','style_count']],
                         [156132,139557,16575,16575,83,13,12])
        self.assertEqual(len(detail_preview(raw)['columns']),54)
        self.assertEqual(dashboard_preview(blocks)['matched_styles'],[])
        # Exercise normalized HTTP serialization against the complete real data.
        # Same outward nested serializers used by JobPreviewView.
        from inspection_summary.preview_serializers import BlockSerializer, DetailSerializer
        json.dumps(BlockSerializer([block_preview(b,i,'analysis') for i,b in enumerate(blocks)],many=True).data)
        encoded = json.dumps(DetailSerializer(detail_preview(raw)).data)
        self.assertNotIn('NaN',encoded); self.assertNotIn('Infinity',encoded)
