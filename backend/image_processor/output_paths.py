"""Report output rules shared by intake and the worker."""
from contextlib import contextmanager
from datetime import date as calendar_date
from pathlib import Path
import re
import os
import zipfile

from rest_framework.exceptions import ValidationError

from image_processor.upload_paths import (
    contained_upload_path, open_upload_file, validate_upload_path,
)


class OutputPathError(ValueError):
    """A generic error safe to persist in report failure records."""


def stored_output_path(relative: str) -> Path:
    from django.conf import settings
    if not relative:
        raise OutputPathError("No report output available.")
    return output_path(Path(settings.MEDIA_ROOT), relative)


def validate_docx(relative: str) -> Path:
    from docx import Document
    path = stored_output_path(relative)
    try:
        if not path.is_file() or path.stat().st_size == 0 or path.suffix.lower() != ".docx":
            raise OutputPathError("Report artifact is unavailable.")
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() or not {"[Content_Types].xml", "word/document.xml"}.issubset(archive.namelist()):
                raise OutputPathError("Report artifact is invalid.")
        Document(path)
    except Exception as exc:
        raise OutputPathError("Report artifact is invalid.") from exc
    return path


def validate_report_date(value: str) -> str:
    if not isinstance(value, str):
        raise OutputPathError("Invalid report date.")
    value = value.strip()
    if not value:
        return value
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise OutputPathError("Invalid report date.")
    try:
        calendar_date.fromisoformat(value)
    except ValueError as exc:
        raise OutputPathError("Invalid report date.") from exc
    return value


def report_filename(folder: str, date: str, label: str) -> str:
    date = validate_report_date(date)
    try:
        for component in (folder, label):
            if not isinstance(component, str):
                raise OutputPathError("Invalid report output path.")
            validate_upload_path(component, single_component=True)
        name = f"{label}_{folder.replace(' ', '_')}_dated on {date or 'no-date'}.docx"
        return validate_upload_path(name, single_component=True)
    except (ValidationError, UnicodeError) as exc:
        raise OutputPathError("Invalid report output path.") from exc


def output_path(root: Path, relative: str) -> Path:
    try:
        return contained_upload_path(root, relative)
    except (ValidationError, OSError, ValueError, RuntimeError) as exc:
        raise OutputPathError("Invalid report output path.") from exc


def output_directory(root: Path, relative: str) -> Path:
    destination = output_path(root, relative)
    try:
        destination.mkdir(parents=True, exist_ok=True, mode=0o755)
    except OSError as exc:
        raise OutputPathError("Invalid report output path.") from exc
    return output_path(root, relative)


@contextmanager
def open_output_file(root: Path, relative: str):
    """Reuse exclusive/no-follow writes; never truncate an existing target."""
    try:
        with open_upload_file(root, relative) as stream:
            yield stream
            if os.name == "posix":
                os.fchmod(stream.fileno(), 0o644)
    except (ValidationError, OSError, ValueError, RuntimeError) as exc:
        raise OutputPathError("Invalid report output path.") from exc
