"""Review regressions: derived filesystem work and worker preparation aliases."""
from unittest.mock import patch
from django.test import TestCase
from image_processor import archive_upload
from image_processor.models import FolderBatch
from image_processor.tests import test_archive_upload as archive_tests
from image_processor.tests import test_upload_containment as folder_tests


class ReviewBoundaryTests(TestCase):
    setUp = folder_tests.UploadContainmentTests.setUp
    upload = folder_tests.UploadContainmentTests.upload
    upload_archive = archive_tests.ArchiveUploadTests.upload_archive
    rejected = archive_tests.ArchiveUploadTests.rejected

    def test_exact_depth_limit_succeeds_and_excess_is_rejected_before_write(self):
        depth = archive_upload.MAX_PATH_DEPTH
        path = '/'.join(['Style'] + ['nested'] * (depth - 1) + ['photo.jpg'])
        response = self.upload_archive([(path, b'image')])
        self.assertEqual(response.status_code, 201, response.data)
        batch = FolderBatch.objects.get()
        self.assertEqual(batch.total_folders, 1)
        # Independent rejected request must not affect the successful job.
        from pathlib import Path
        saved = Path(batch.source_folder) / path
        bad = 'extra/' + path
        with patch(archive_tests.ARCHIVE + '.open_upload_file') as writer:
            response = self.upload_archive([(bad, b'image')])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'archive_limit_exceeded')
        self.assertNotIn(bad, str(response.data))
        writer.assert_not_called()
        self.assertEqual(FolderBatch.objects.count(), 1)
        self.delay.assert_called_once()
        self.assertEqual(saved.read_bytes(), b'image')
        self.assertEqual(len(list(self.staging.iterdir())), 1)

    def test_derived_directory_limit_is_incremental_and_preflighted(self):
        paths = ['A/x/a.jpg', 'B/y/b.jpg']  # Four implicit directories, two entries.
        with patch(archive_tests.ARCHIVE + '.MAX_DERIVED_DIRECTORIES', 3):
            with patch(archive_tests.ARCHIVE + '.open_upload_file') as writer:
                response = self.upload_archive([(p, b'image') for p in paths])
            self.rejected(response)
            self.assertEqual(response.data['code'], 'archive_limit_exceeded')
            self.assertNotIn(paths[1], str(response.data))
            writer.assert_not_called()
        identities = set()
        with patch(archive_tests.ARCHIVE + '.MAX_DERIVED_DIRECTORIES', 1):
            with self.assertRaises(archive_upload.ArchiveValidationError):
                archive_upload._track_directories('A/B/C/photo.jpg', False, identities)
        self.assertEqual(identities, {'a'})

    def test_shared_parents_and_exact_directory_budget_succeed(self):
        with patch(archive_tests.ARCHIVE + '.MAX_DERIVED_DIRECTORIES', 3):
            response = self.upload_archive([('A/x/one.jpg', b'image'), ('A/y/two.png', b'image')])
        self.assertEqual(response.status_code, 201, response.data)

    def test_preparation_collisions_rejected_in_both_modes_before_writes(self):
        for names in (['photo.jpg', 'photo.png'], ['A.JPG', 'a.png'], ['a b.jpg', 'a_b.png']):
            paths = [f'Style-A/{group}/{name}' for group, name in zip(('Front', 'Front'), names)]
            for renamed in ('false', 'true'):
                for mode in ('folder', 'archive'):
                    with self.subTest(names=names, renamed=renamed, mode=mode):
                        with patch(folder_tests.VIEW + '.open_upload_file') as folder_writer:
                            with patch(archive_tests.ARCHIVE + '.open_upload_file') as archive_writer:
                                response = (self.upload(names=names, paths=paths, is_renamed_file=renamed)
                                            if mode == 'folder' else
                                            self.upload_archive([(p, b'image') for p in paths], is_renamed_file=renamed))
                        self.rejected(response)
                        folder_writer.assert_not_called()
                        archive_writer.assert_not_called()

    def test_same_preparation_name_in_distinct_logical_folders_stays_valid(self):
        paths = ['Style-A/photo.jpg', 'Style-B/photo.png']
        for mode in ('folder', 'archive'):
            response = (self.upload(names=['photo.jpg', 'photo.png'], paths=paths)
                        if mode == 'folder' else self.upload_archive([(p, b'image') for p in paths]))
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data['total_folders'], 2)
