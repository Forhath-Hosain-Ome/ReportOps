"""Bounded ZIP intake into the existing Phase 01 upload boundary."""
import struct
import stat
import zipfile
import zlib
from pathlib import PurePosixPath

from rest_framework.exceptions import ValidationError
from image_processor.serializers.folder_upload_serializer import MAX_FILE_SIZE, VALID_IMAGE_EXTENSIONS
from image_processor.upload_paths import (
    open_upload_file, validate_upload_path, validate_upload_destinations,
    validate_preparation_destinations,
)
from utils import normalize_filename

MAX_ARCHIVE_SIZE = 50 * 1024 * 1024
MAX_ENTRIES = 1000
MAX_TOTAL_SIZE = 200 * 1024 * 1024
MAX_RATIO = 100
MAX_DIRECTORY_SIZE = 2 * 1024 * 1024
MAX_PATH_LENGTH = 1024
MAX_PATH_DEPTH = 8  # Logical folder plus up to seven nested inspection groupings.
MAX_DERIVED_DIRECTORIES = 1000  # Do not amplify the 1,000-entry budget into more directories.
CHUNK_SIZE = 64 * 1024


class ArchiveValidationError(ValidationError):
    def __init__(self, code='invalid_archive'):
        super().__init__({'code': code, 'detail': 'Invalid, unsupported or oversized image archive.'})


def _check_directory_budget(upload):
    """Bound central-directory allocation before ZipFile parses entry objects.

    Accept single-volume classic ZIP only; ZIP64 is unnecessary for these limits.
    Require the declared directory to terminate at EOCD (no trailing records).
    """
    if not 0 < upload.size <= MAX_ARCHIVE_SIZE:
        raise ArchiveValidationError('archive_limit_exceeded')
    upload.seek(0, 2)
    size = upload.tell()
    if size != upload.size:
        raise ArchiveValidationError()
    upload.seek(max(0, size - 65557))
    tail = upload.read(65557)
    end = tail.rfind(b'PK\x05\x06')
    if end < 0 or len(tail) - end < 22:
        raise ArchiveValidationError()
    disk, start_disk, disk_count, count, length, offset, comment = struct.unpack_from('<4H2LH', tail, end + 4)
    end_offset = size - len(tail) + end
    if (disk or start_disk or disk_count != count or count == 65535
            or offset + length != end_offset or end + 22 + comment != len(tail)):
        raise ArchiveValidationError()
    if count > MAX_ENTRIES or length > MAX_DIRECTORY_SIZE:
        raise ArchiveValidationError('archive_limit_exceeded')
    upload.seek(0)


def _track_directories(path, is_directory, identities):
    parts = path.split('/')
    depth = len(parts) if is_directory else len(parts) - 1
    if depth > MAX_PATH_DEPTH:
        raise ArchiveValidationError('archive_limit_exceeded')
    for level in range(1, depth + 1):
        identity = '/'.join(parts[:level]).casefold()
        if identity not in identities:
            if len(identities) >= MAX_DERIVED_DIRECTORIES:
                raise ArchiveValidationError('archive_limit_exceeded')
            identities.add(identity)


def _plan(archive, style):
    entries = archive.infolist()
    if not entries:
        raise ArchiveValidationError()
    if len(entries) > MAX_ENTRIES:
        raise ArchiveValidationError('archive_limit_exceeded')
    files, directories = [], []
    derived_directories = set()
    total = 0
    for entry in entries:
        raw = entry.orig_filename
        if raw != entry.filename or len(raw) > MAX_PATH_LENGTH:
            raise ArchiveValidationError()
        path = validate_upload_path(raw[:-1] if raw.endswith('/') else raw)
        mode = (entry.external_attr >> 16) & 0xFFFF
        kind = stat.S_IFMT(mode)
        is_dir = entry.is_dir()
        _track_directories(path, is_dir, derived_directories)
        # Reject Unix links/devices and DOS volume/reparse attributes, even on POSIX.
        if (kind not in (0, stat.S_IFREG, stat.S_IFDIR)
                or (kind == stat.S_IFDIR and not is_dir)
                or (is_dir and kind == stat.S_IFREG)
                or entry.external_attr & (0x08 | 0x400)
                or (entry.external_attr & 0x10 and not is_dir)
                or entry.flag_bits & 1
                or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
            raise ArchiveValidationError()
        if is_dir:
            if entry.file_size:
                raise ArchiveValidationError()
            directories.append(path)
            continue
        if PurePosixPath(path).suffix.lower() not in VALID_IMAGE_EXTENSIONS or not entry.file_size:
            raise ArchiveValidationError()
        total += entry.file_size
        if (entry.file_size > MAX_FILE_SIZE or total > MAX_TOTAL_SIZE
                or entry.file_size > max(1, entry.compress_size) * MAX_RATIO):
            raise ArchiveValidationError('archive_limit_exceeded')
        destination = str(PurePosixPath(path).parent / normalize_filename(PurePosixPath(path).name))
        files.append((entry, destination))
    if not files:
        raise ArchiveValidationError()
    # A synthetic non-image leaf lets the existing helper validate explicit dirs
    # against files, duplicates and case aliases without creating empty folders.
    validate_upload_destinations([p for _, p in files] + [p + '/.zip_directory' for p in directories])
    flat = [('/' not in p) for _, p in files]
    if all(flat):
        files = [(entry, f"{style or 'uploaded'}/{path}") for entry, path in files]
        for _, path in files:
            _track_directories(path, False, derived_directories)
    validate_upload_destinations([p for _, p in files])
    validate_preparation_destinations([p for _, p in files])
    return files


def stage_archive(upload, root, style=''):
    """Preflight all metadata, then stream; caller owns cleanup and dispatch."""
    try:
        _check_directory_budget(upload)
        with zipfile.ZipFile(upload) as archive:
            plan = _plan(archive, style)
            total = 0
            for entry, path in plan:
                expanded = 0
                with archive.open(entry) as source, open_upload_file(root, path) as target:
                    while chunk := source.read(CHUNK_SIZE):
                        expanded += len(chunk)
                        total += len(chunk)
                        if expanded > min(entry.file_size, MAX_FILE_SIZE) or total > MAX_TOTAL_SIZE:
                            raise ArchiveValidationError('archive_limit_exceeded')
                        target.write(chunk)
                if expanded != entry.file_size:
                    raise ArchiveValidationError()
            return [{"relative_path": path, "original_filename": PurePosixPath(entry.filename).name}
                    for entry, path in plan]
    except ArchiveValidationError:
        raise
    except (ValidationError, zipfile.BadZipFile, zipfile.LargeZipFile, NotImplementedError,
            RuntimeError, EOFError, ValueError, struct.error, zlib.error) as exc:
        raise ArchiveValidationError() from exc
