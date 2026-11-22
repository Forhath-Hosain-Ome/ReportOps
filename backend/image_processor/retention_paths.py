"""Exact batch directory identity shared by retry and destructive maintenance."""
from pathlib import Path
from django.conf import settings
from image_processor.upload_paths import contained_upload_path
from image_processor.output_paths import output_path


def staging_root():
    return Path(getattr(settings, "IMAGE_PROCESSOR_STAGING_ROOT", "/tmp/batch_uploads")).absolute()


def source_directory(batch):
    if not batch.source_folder or not batch.staging_id:
        raise ValueError("Missing batch source identity.")
    root = staging_root()
    expected = contained_upload_path(root, str(batch.staging_id))
    supplied = Path(batch.source_folder)
    if (not supplied.is_absolute() or ".." in supplied.parts or supplied.name != str(batch.staging_id)
            or supplied.parent.resolve() != root.resolve()
            or contained_upload_path(supplied.parent, supplied.name) != expected):
        raise ValueError("Source does not match batch staging identity.")
    return expected


def output_root():
    media = Path(settings.MEDIA_ROOT).absolute()
    configured = Path(getattr(settings, "IMAGE_PROCESSOR_SETTINGS", {}).get(
        "OUTPUT_DIR", media / "output" / "defect_image",
    )).absolute()
    relative = configured.relative_to(media)
    if not relative.parts or ".." in relative.parts:
        raise ValueError("Output root must be a strict media descendant.")
    return output_path(media, relative.as_posix())


def output_directory_for_batch(batch):
    return output_path(output_root(), str(batch.pk))
