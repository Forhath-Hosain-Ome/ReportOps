import tempfile
import os
import stat
import subprocess
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError

from image_processor.models import FolderBatch
from image_processor.upload_paths import contained_upload_path, open_upload_file

VIEW = "image_processor.views.folder_upload_view"
PATHS = "image_processor.upload_paths"


class UploadContainmentTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.sandbox = Path(self.temporary.name).resolve()
        self.staging = self.sandbox / "batch_uploads"
        self.staging_override = override_settings(IMAGE_PROCESSOR_STAGING_ROOT=self.staging)
        self.staging_override.enable()
        self.addCleanup(self.staging_override.disable)
        # Redirect the original hard-coded /tmp path, never touch real uploads.
        real_path = Path
        self.path_patch = patch(
            VIEW + ".Path",
            side_effect=lambda value: self.sandbox if value == "/tmp" else real_path(value),
        )
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.dispatch = patch(VIEW + ".process_folder_task.delay")
        self.delay = self.dispatch.start()
        self.delay.return_value.id = "isolated-test-task"
        self.addCleanup(self.dispatch.stop)
        self.client = APIClient()
        self.user = User.objects.create_user(username="upload-owner")
        self.client.force_authenticate(self.user)

    def upload(self, names=("photo.jpg",), paths=None, **fields):
        data = {"files": [SimpleUploadedFile(n, b"synthetic image") for n in names], **fields}
        if paths is not None:
            data["paths"] = paths
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post("/image/folder/upload/", data, format="multipart")

    def test_normal_flat_upload_persists_owner_and_dispatches_contained_root(self):
        response = self.upload(style="Style-A")
        self.assertEqual(response.status_code, 201, response.data)
        batch = FolderBatch.objects.get(pk=response.data["batch_id"])
        root = Path(batch.source_folder).resolve()
        self.assertEqual(root.parent, self.staging)
        self.assertEqual(batch.created_by, self.user)
        self.assertEqual((root / "Style-A/photo.jpg").read_bytes(), b"synthetic image")
        self.delay.assert_called_once_with(batch.id, str(root), "", is_renamed_file=False, dispatch_generation=batch.dispatch_generation, dispatch_token=str(batch.dispatch_token))

    def test_parent_style_cannot_write_outside_job(self):
        response = self.upload(style="../escaped")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse((self.staging / "escaped/photo.jpg").exists())
        self.assertFalse(FolderBatch.objects.exists())
        self.delay.assert_not_called()

    def test_absolute_style_cannot_write_outside_job(self):
        destination = self.sandbox / "escaped"
        response = self.upload(style=str(destination))
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(destination.exists())
        self.assertFalse(FolderBatch.objects.exists())
        self.delay.assert_not_called()

    def assert_rejected(self, response):
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(FolderBatch.objects.exists())
        self.delay.assert_not_called()
        self.assertEqual(list(self.sandbox.rglob("*.jpg")), [])

    def test_unsafe_style_matrix(self):
        for style in (
            "..", "../escape", "a/../../escape", "a/../escape", "/escape",
            "C:\\escape", "C:/escape", "C:escape", "\\\\server\\share",
            "a\\..//escape", "a/b", "a\\b", "name.", "NUL", "x:stream",
            "x\x00y", "x" * 256,
        ):
            with self.subTest(style=style):
                self.assert_rejected(self.upload(style=style))

    def test_unsafe_relative_path_matrix_in_both_naming_modes(self):
        for renamed in ("true", "false"):
            for path in (
                "../escape/photo.jpg", "a/../../escape/photo.jpg",
                "a/../photo.jpg", "/escape/photo.jpg", "C:/escape/photo.jpg",
                "C:\\escape\\photo.jpg", "C:photo.jpg",
                "\\\\server\\share\\photo.jpg", "a\\..\\photo.jpg",
                "a//photo.jpg", "./photo.jpg", "a./photo.jpg",
                "NUL/photo.jpg", "a:stream/photo.jpg", "a\x00b/photo.jpg",
                "a" * 256 + "/photo.jpg",
            ):
                with self.subTest(path=path, renamed=renamed):
                    self.assert_rejected(self.upload(paths=[path], is_renamed_file=renamed))

    def test_existing_folder_upload_preserves_normalized_filename(self):
        response = self.upload(names=["image one.jpg"], paths=["Style A/image one.jpg"])
        self.assertEqual(response.status_code, 201, response.data)
        root = Path(FolderBatch.objects.get().source_folder)
        self.assertTrue((root / "Style A/image_one.jpg").is_file())

    def test_existing_nested_and_multiple_folder_payload_is_preserved(self):
        response = self.upload(
            names=["one.jpg", "two.jpg"],
            paths=["Style-A/nested/one.jpg", "Style-B/two.jpg"],
        )
        self.assertEqual(response.status_code, 201, response.data)
        batch = FolderBatch.objects.get()
        root = Path(batch.source_folder)
        self.assertEqual(batch.total_folders, 2)
        self.assertTrue((root / "Style-A/nested/one.jpg").is_file())
        self.assertTrue((root / "Style-B/two.jpg").is_file())

    def test_mixed_separators_are_canonical_in_named_mode(self):
        response = self.upload(paths=["Style-A\\nested/photo.jpg"], is_renamed_file="true")
        self.assertEqual(response.status_code, 201, response.data)
        root = Path(FolderBatch.objects.get().source_folder)
        self.assertTrue((root / "Style-A/nested/photo.jpg").is_file())

    def test_blank_style_retains_default_folder(self):
        response = self.upload(style="")
        self.assertEqual(response.status_code, 201, response.data)
        root = Path(FolderBatch.objects.get().source_folder)
        self.assertTrue((root / "uploaded/photo.jpg").is_file())

    def test_paths_bracket_alias_remains_supported(self):
        response = self.upload(**{"paths[]": ["Style-A/photo.jpg"]})
        self.assertEqual(response.status_code, 201, response.data)
        root = Path(FolderBatch.objects.get().source_folder)
        self.assertTrue((root / "Style-A/photo.jpg").is_file())

    def test_batch_detail_and_list_remain_owner_scoped_after_upload(self):
        response = self.upload()
        batch_id = response.data["batch_id"]
        detail_url = f"/image/folder/batches/{batch_id}/"
        detail = self.client.get(detail_url)
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data["status"], "PENDING")
        self.assertEqual(detail.data["created_by"]["id"], self.user.pk)
        self.assertEqual(self.client.get("/image/folder/batches/").data[0]["id"], batch_id)
        other_user = User.objects.create_user(username="other-owner")
        self.client.force_authenticate(other_user)
        self.assertEqual(self.client.get(detail_url).status_code, 404)
        self.assertEqual(self.client.get("/image/folder/batches/").data, [])

    def test_file_size_limit_is_preserved(self):
        with patch("image_processor.serializers.folder_upload_serializer.MAX_FILE_SIZE", 1):
            self.assert_rejected(self.upload())

    def test_colliding_normalized_filenames_are_rejected_before_writing(self):
        for names in (["a b.jpg", "a_b.jpg"], ["A.jpg", "a.jpg"], ["a.jpg", "a.jpg"]):
            with self.subTest(names=names):
                response = self.upload(names=names)
                self.assert_rejected(response)
                self.assertEqual(response.data["code"], "upload_destination_conflict")

    def test_file_directory_conflict_is_rejected_in_either_order(self):
        for names, paths in (
            (["a.jpg", "b.jpg"], ["a.jpg", "a.jpg/b.jpg"]),
            (["b.jpg", "a.jpg"], ["a.jpg/b.jpg", "a.jpg"]),
        ):
            with self.subTest(paths=paths):
                self.assert_rejected(self.upload(names=names, paths=paths))

    def test_same_filename_in_distinct_folders_remains_valid(self):
        response = self.upload(names=["a.jpg", "a.jpg"], paths=["A/a.jpg", "B/a.jpg"])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(FolderBatch.objects.get().total_folders, 2)

    def test_case_aliased_folder_names_cannot_merge_on_windows(self):
        self.assert_rejected(self.upload(
            names=["a.jpg", "b.jpg"], paths=["Style/a.jpg", "style/b.jpg"],
        ))

    def test_repeated_uploads_have_distinct_private_roots(self):
        for _ in range(2):
            response = self.upload()
            self.assertEqual(response.status_code, 201, response.data)
        roots = [Path(b.source_folder) for b in FolderBatch.objects.all()]
        self.assertNotEqual(roots[0], roots[1])
        for root in roots:
            self.assertEqual(root.parent, self.staging)
            self.assertTrue((root / "uploaded/photo.jpg").is_file())
            if os.name != "nt":
                self.assertEqual(root.stat().st_mode & 0o777, 0o700)

    def test_existing_file_at_final_destination_is_not_overwritten(self):
        captured = []
        real_open = os.open
        def existing_file(path, flags, mode=0o777, **kwargs):
            if not flags & os.O_CREAT:
                return real_open(path, flags, mode, **kwargs)
            with os.fdopen(real_open(path, flags, mode, **kwargs), "wb") as stream:
                stream.write(b"existing")
            try:
                return real_open(path, flags, mode, **kwargs)
            finally:
                with os.fdopen(real_open(path, os.O_RDONLY, **kwargs), "rb") as stream:
                    captured.append(stream.read())
        with patch(PATHS + ".os.open", side_effect=existing_file):
            response = self.upload()
        self.assert_rejected(response)
        self.assertEqual(captured, [b"existing"])

    def test_resolver_result_outside_root_is_rejected(self):
        root = self.sandbox / "job"
        outside = self.sandbox / "escape.jpg"
        real_resolve = Path.resolve
        def escaped(path, *args, **kwargs):
            if path.name == "photo.jpg":
                return outside
            return real_resolve(path, *args, **kwargs)
        with patch.object(Path, "resolve", escaped):
            with self.assertRaises(ValidationError):
                contained_upload_path(root, "photo.jpg")
        self.assertFalse(outside.exists())

    def test_actual_filename_cannot_bypass_type_check_using_a_jpg_path(self):
        response = self.upload(names=["payload.py"], paths=["photo.jpg"])
        self.assert_rejected(response)
        self.assertEqual(list(self.sandbox.rglob("*.py")), [])

    def test_zip_remains_unsupported(self):
        self.assert_rejected(self.upload(names=["images.zip"]))

    def test_empty_upload_and_path_count_mismatch(self):
        self.assert_rejected(self.upload(names=[]))
        self.assert_rejected(self.upload(paths=["a.jpg", "b.jpg"]))

    def test_unauthenticated_request_does_not_create_files_or_batch(self):
        self.client = APIClient()
        response = self.upload()
        self.assertEqual(response.status_code, 401)
        self.assertFalse(self.staging.exists())
        self.assertFalse(FolderBatch.objects.exists())
        self.delay.assert_not_called()

    def test_root_collision_does_not_overwrite_or_delete_existing_job(self):
        root = self.staging / "existing-job"
        root.mkdir(parents=True)
        sentinel = root / "sentinel.txt"
        sentinel.write_text("existing job")
        with patch(VIEW + ".uuid.uuid4", return_value="existing-job"):
            response = self.upload()
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["code"], "upload_destination_conflict")
        self.assertEqual(sentinel.read_text(), "existing job")
        self.assertFalse(FolderBatch.objects.exists())
        self.delay.assert_not_called()

    def make_directory_link(self, link, target):
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        else:
            link.symlink_to(target, target_is_directory=True)

    def test_resolved_destination_rejects_real_directory_link(self):
        root = self.sandbox / "job"
        root.mkdir()
        outside = self.sandbox / "outside"
        outside.mkdir()
        self.make_directory_link(root / "link", outside)
        with self.assertRaises(ValidationError):
            contained_upload_path(root, "link/photo.jpg")
        self.assertEqual(list(outside.iterdir()), [])

    def test_view_rejects_planted_directory_link_and_does_not_dispatch(self):
        outside = self.sandbox / "outside"
        outside.mkdir()
        sentinel = outside / "sentinel.txt"
        sentinel.write_text("untouched")
        real_containment = contained_upload_path
        def plant_link(root, relative_path):
            link = root / "Style-A"
            if not link.exists():
                self.make_directory_link(link, outside)
            return real_containment(root, relative_path)
        with patch(PATHS + ".contained_upload_path", side_effect=plant_link):
            response = self.upload(paths=["Style-A/photo.jpg"])
        self.assert_rejected(response)
        self.assertEqual(sentinel.read_text(), "untouched")

    def test_write_failure_cleans_only_its_job_and_does_not_dispatch(self):
        sentinel = self.sandbox / "sentinel.txt"
        sentinel.write_text("untouched")
        secret_path = str(self.sandbox / "private-job-uuid")
        with patch(VIEW + ".open_upload_file", side_effect=OSError(secret_path)):
            with self.assertLogs(VIEW, level="WARNING") as logs:
                response = self.upload()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data["code"], "upload_failed")
        self.assertNotIn(secret_path, str(response.data) + str(logs.output))
        self.assertEqual(list(self.staging.iterdir()), [])
        self.assertEqual(sentinel.read_text(), "untouched")
        self.assertFalse(FolderBatch.objects.exists())
        self.delay.assert_not_called()

    def test_concurrent_writers_have_one_winner_without_overwrite(self):
        root = self.sandbox / "job"
        root.mkdir(mode=0o700)
        barrier = Barrier(4)
        def write(index):
            barrier.wait(timeout=10)
            try:
                with open_upload_file(root, "nested/photo.jpg") as stream:
                    stream.write(str(index).encode())
                return index
            except FileExistsError:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            winners = [i for i in pool.map(write, range(4)) if i is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual((root / "nested/photo.jpg").read_bytes(), str(winners[0]).encode())

    def test_parent_replaced_with_link_during_mkdir_is_rejected(self):
        root, outside = self.sandbox / "job", self.sandbox / "outside"
        root.mkdir(mode=0o700)
        outside.mkdir()
        real_mkdir = os.mkdir
        def replace_parent(*args, **kwargs):
            real_mkdir(*args, **kwargs)
            (root / "nested").rmdir()
            self.make_directory_link(root / "nested", outside)
        with patch(PATHS + ".os.mkdir", side_effect=replace_parent):
            with self.assertRaises((ValidationError, OSError)):
                with open_upload_file(root, "nested/photo.jpg"):
                    self.fail("A replaced parent must never be opened for writing")
        self.assertEqual(list(outside.iterdir()), [])

    @skipUnless(os.name == "nt", "Windows ACL contract; POSIX modes are tested separately")
    def test_windows_job_and_file_acl_allow_only_owner_system_and_administrators(self):
        root = self.sandbox / "private-job"
        root.mkdir(mode=0o700)
        with open_upload_file(root, "photo.jpg") as stream:
            stream.write(b"private")
        script = """
        $ErrorActionPreference = 'Stop'
        $allowed = @([System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value,
                     'S-1-5-18', 'S-1-5-32-544', 'S-1-3-4') # SYSTEM, Administrators, OWNER RIGHTS
        foreach ($item in @($env:UQ_TEST_JOB, (Join-Path $env:UQ_TEST_JOB 'photo.jpg'))) {
            $acl = if ([IO.Directory]::Exists($item)) { [IO.Directory]::GetAccessControl($item) } else { [IO.File]::GetAccessControl($item) }
            foreach ($ace in $acl.Access) {
                $sid = $ace.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
                if ($ace.AccessControlType -eq 'Allow' -and $sid -notin $allowed) {
                    throw 'Unexpected principal has access to the upload job'
                }
            }
        }
        """
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            env={**os.environ, "UQ_TEST_JOB": str(root)}, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    @skipUnless(os.name == "posix", "POSIX dir_fd/umask contract; Windows uses private job ACLs")
    def test_parent_swap_before_file_open_stays_anchored_and_private(self):
        root = self.sandbox / "job"
        outside = self.sandbox / "outside"
        root.mkdir(mode=0o700)
        outside.mkdir()
        real_open = os.open
        def swap_parent(path, flags, mode=0o777, **kwargs):
            if flags & os.O_CREAT:
                (root / "nested").rename(root / "original")
                (root / "nested").symlink_to(outside, target_is_directory=True)
            return real_open(path, flags, mode, **kwargs)
        previous_umask = os.umask(0)
        try:
            with patch(PATHS + ".os.open", side_effect=swap_parent):
                with open_upload_file(root, "nested/photo.jpg") as stream:
                    stream.write(b"contained")
        finally:
            os.umask(previous_umask)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual((root / "original/photo.jpg").read_bytes(), b"contained")
        self.assertEqual(stat.S_IMODE((root / "original").stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((root / "original/photo.jpg").stat().st_mode), 0o600)
