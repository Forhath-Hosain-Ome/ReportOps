"""
image_processor/tasks/process_defect_docx.py

Celery task that turns one or more image folders into DOCX defect-picture
reports.  Output is always saved as DOCX; PDF export is handled separately
by a download view that calls LibreOffice on demand.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from celery import shared_task
from django.conf import settings
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Inches, Pt, RGBColor
from PIL import Image

from image_processor.models import FolderBatch, FolderReport, FolderFailedPDF
from image_processor.output_paths import (
    OutputPathError, open_output_file, output_directory, output_path,
    report_filename, validate_report_date,
)

logger = logging.getLogger(__name__)


def _get_channel_layer():
    from channels.layers import get_channel_layer
    return get_channel_layer()


def _group_name(batch_id: int) -> str:
    return f"image_batch_{batch_id}"


def _push(group: str, message: dict):
    try:
        from asgiref.sync import async_to_sync
        layer = _get_channel_layer()
        async_to_sync(layer.group_send)(group, message)
    except Exception as e:
        if "cannot schedule new futures after interpreter shutdown" in str(e):
            logger.debug("Skipping channel push during shutdown: %s", e)
        else:
            logger.warning("Channel push failed: %s", e)


def _push_progress(batch: FolderBatch, stage: str = ""):
    from image_processor.progress import progress_payload
    _push(_group_name(batch.pk), {**progress_payload(batch), "type": "batch.progress", "stage": stage})


def _push_complete(batch: FolderBatch):
    from image_processor.progress import progress_payload
    _push(_group_name(batch.pk), {**progress_payload(batch), "type": "batch.complete"})


def _push_error(batch: FolderBatch, message: str):
    _push(_group_name(batch.pk), {
        "type":          "batch.error",
        "batch_id":      batch.pk,
        "status":        FolderBatch.Status.FAILED,
        "error_message": message,
    })


# ── Constants ─────────────────────────────────────────────────────────────────

LABEL_TYPES = [
    "Defect Picture",
    "Defect Goods",
    "Defect Footwear",
    "Defect Accessories",
    "Defect Fabric",
]

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp", ".ico"}

IMG_WIDTH_INCHES  =  4.51
IMG_HEIGHT_INCHES =  3.68

IMAGES_PER_PAGE = 2


# ── Image helpers ─────────────────────────────────────────────────────────────

def _is_valid_image(filename: str) -> bool:
    return Path(filename).suffix.lower() in VALID_EXTENSIONS


def _prepare_image(image_path: str, dest_dir: Path, *, output_root: Path, dimensions=(325, 265)) -> Optional[Path]:
    """
    Convert and resize an image to JPEG at 325x265 px.
    dest_dir is relative to output_root. Return the dest Path or None on failure.
    """
    source = Path(image_path)
    relative = str(dest_dir / (source.stem + ".jpg"))
    dest = output_path(output_root, relative)
    created = False

    try:
        if not source.is_file():
            raise FileNotFoundError("Accepted source image is unavailable.")
        try:
            with Image.open(source) as original:
                original.load()
                img = original.copy()
        except (Image.UnidentifiedImageError, Image.DecompressionBombError, ValueError):
            return None
        except OSError as exc:
            if exc.errno is not None:
                raise  # Permission, missing source and I/O failures are infrastructure failures.
            return None  # Pillow's truncated/unsupported decoder errors have no OS errno.

        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            mask = img.split()[-1] if img.mode == "RGBA" else None
            bg.paste(img, mask=mask)
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        img = img.resize(dimensions, Image.Resampling.LANCZOS)

        import io as _io
        buf = _io.BytesIO()
        img.save(buf, "JPEG", quality=95)
        with open_output_file(output_root, relative) as stream:
            created = True
            stream.write(buf.getvalue())
        return dest

    except OutputPathError:
        raise
    except Exception as exc:
        logger.error("Image prepare failed for %s: %s", image_path, exc)
        if created and dest.exists():
            dest.unlink(missing_ok=True)
        raise


# ── DOCX helpers ──────────────────────────────────────────────────────────────

def _replace_placeholders(doc: Document, replacements: dict[str, str]) -> None:
    def _replace_in_paragraph(para):
        full = "".join(r.text for r in para.runs)
        changed = full
        for key, val in replacements.items():
            changed = changed.replace("{" + key + "}", val)
        if changed != full and para.runs:
            para.runs[0].text = changed
            for r in para.runs[1:]:
                r.text = ""

    def _replace_in_container(container):
        for para in container.paragraphs:
            _replace_in_paragraph(para)
        for table in container.tables:
            for row in table.rows:
                for cell in row.cells:
                    _replace_in_container(cell)

    _replace_in_container(doc)
    for section in doc.sections:
        _replace_in_container(section.header)
        _replace_in_container(section.footer)

    # for key in replacements:
    #     _remove_empty_paragraphs_after_placeholder(doc, "{" + key + "}")


def _remove_empty_paragraphs_after_placeholder(doc: Document, placeholder: str) -> None:
    """Remove empty paragraphs that follow a specific placeholder."""
    def is_empty_paragraph(para):
        text = "".join(r.text for r in para.runs).strip()
        return not text

    paragraphs = list(doc.paragraphs)
    for i, para in enumerate(paragraphs):
        if placeholder in para.text:
            for j in range(i + 1, len(paragraphs)):
                if is_empty_paragraph(paragraphs[j]):
                    p = paragraphs[j]._element
                    p.getparent().remove(p)
                else:
                    break


def _remove_empty_paragraphs_before_first_element(doc: Document) -> None:
    """Remove empty paragraphs before the first table in the document."""
    body = doc.element.body
    paragraphs = list(body.iter(qn("w:p")))
    for p in paragraphs:
        text = "".join(t.text for t in p.iter(qn("w:t"))).strip()
        if not text:
            body.remove(p)
        else:
            break


def _set_cell_top_border(cell, thickness: int = 3) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tc = cell._element
    tcPr = tc.get_or_add_tcPr()
    
    tcBdr = tcPr.find(qn("w:tcBdr"))
    if tcBdr is None:
        tcBdr = OxmlElement("w:tcBdr")
        tcPr.append(tcBdr)
    
    for border_name in ["w:top"]:
        border = OxmlElement(border_name)
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), str(thickness * 8))
        border.set(qn("w:color"), "000000")
        border.set(qn("w:space"), "0")
        tcBdr.append(border)


def _set_table_borders(table, thickness: int = 3) -> None:
    """Set table-level borders that work better with LibreOffice."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    
    tbl = table._element
    tblPr = tbl.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)
    
    tblBorders = tblPr.find(qn("w:tblBorders"))
    if tblBorders is None:
        tblBorders = OxmlElement("w:tblBorders")
        tblPr.append(tblBorders)
    
    for border_name in ["w:top"]:
        border = OxmlElement(border_name)
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), str(thickness * 8))
        border.set(qn("w:color"), "000000")
        tblBorders.append(border)


def _add_label_paragraph(
    doc: Document,
    text: str,
    font_name: str = "Verdana",
    font_size_pt: int = 11,
    color_hex: str = "000000",
    bold: bool = False,
    highlight_color: Optional[str] = None,
) -> None:
    para = doc.add_paragraph()
    run = para.add_run(text)
    run.font.name = font_name
    run.font.size = Pt(font_size_pt)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color_hex)

    if highlight_color:
        # Add text highlight color via XML
        rPr = run._element.get_or_add_rPr()
        highlight = OxmlElement('w:highlight')
        highlight.set(qn('w:val'), highlight_color)
        rPr.append(highlight)


def _add_image_paragraph(doc: Document, image_path: str) -> None:
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = para.add_run()
    run.add_picture(image_path, width=Inches(IMG_WIDTH_INCHES))


# ── Per-folder DOCX generation ────────────────────────────────────────────────

def _generate_docx(
    template_path: str,
    style_name: str,
    date_str: str,
    label_type: str,
    image_paths: list[str],
    output_docx_path: str,
    *,
    output_root: Path,
    mode: str = "basic",
    label_style: Optional[dict] = None,
    translations: Optional[dict[str, str]] = None,
) -> None:
    if label_style is None:
        label_style = {}
    if translations is None:
        translations = {}

    label_type = label_type if label_type in LABEL_TYPES else LABEL_TYPES[0]

    doc = Document(template_path)

    _replace_placeholders(doc, {
        "date":  f"{label_type} Dated {date_str}",
        "style": f"STYLE NO : {style_name}",
    })

    doc.tables[0]._element.getparent().remove(doc.tables[0]._element)

    # Remove empty paragraphs after table removal
    body = doc.element.body
    empty_paras = [p for p in body.iter(qn("w:p")) 
                   if not "".join(t.text for t in p.iter(qn("w:t"))).strip()]
    for p in empty_paras:
        body.remove(p)

    pages = [image_paths[i:i + IMAGES_PER_PAGE]
             for i in range(0, len(image_paths), IMAGES_PER_PAGE)]

    for page_idx, page_images in enumerate(pages):
        if page_idx > 0:
            doc.add_page_break()

        new_sep = doc.add_table(rows=1, cols=1)
        new_sep.rows[0].cells[0].text = ""
        _set_cell_top_border(new_sep.rows[0].cells[0], thickness=3)
        _set_table_borders(new_sep, thickness=3)

        for img_path in page_images:
            stem = Path(img_path).stem

            if mode == "named":
                _add_label_paragraph(
                    doc, stem,
                    font_name        = label_style.get("font_name",    "Verdana"),
                    font_size_pt     = label_style.get("font_size_pt", 11),
                    color_hex        = label_style.get("color_hex",    "000000"),
                    bold             = label_style.get("bold",         False),
                    highlight_color  = label_style.get("highlight_color"),
                )
            elif mode == "translated":
                translated = translations.get(stem, "")
                label_text = f"{stem} / {translated}" if translated else stem
                _add_label_paragraph(
                    doc, label_text,
                    font_name        = label_style.get("font_name",    "Verdana"),
                    font_size_pt     = label_style.get("font_size_pt", 11),
                    color_hex        = label_style.get("color_hex",    "000000"),
                    bold             = label_style.get("bold",         False),
                    highlight_color  = label_style.get("highlight_color"),
                )

            _add_image_paragraph(doc, img_path)
    with open_output_file(output_root, output_docx_path) as stream:
        doc.save(stream)
    logger.info("DOCX saved for report")


# ── Translation helper ────────────────────────────────────────────────────────

def _translate_names(names: list[str], target_language: str) -> dict[str, str]:
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source="auto", target=target_language)
        result = {}
        for name in names:
            try:
                result[name] = translator.translate(name)
            except Exception as exc:
                logger.warning("Translation failed for '%s': %s", name, exc)
                result[name] = name
        return result
    except ImportError:
        logger.error("deep-translator not installed — returning originals")
        return {n: n for n in names}


# ── Temp-dir cleanup ─────────────────────────────────────────────────────────

# Main task identity and public alias remain compatible with existing routing.
@shared_task(bind=True, max_retries=0, soft_time_limit=1200, time_limit=1500,
             name="image_processor.process_defect_docx")
def process_defect_docx_task(
    self, batch_id: int, source_folder: str, date: str = "",
    is_renamed_file: bool = False,
    label_type: str = "Defect_GMTS_pictures_report_for_Style", mode: str = "basic",
    label_style: Optional[dict] = None, use_translation: bool = False,
    translation_language: str = "en", template_path: Optional[str] = None,
    dispatch_generation=None, dispatch_token=None,
) -> dict:
    from image_processor.coordination import batch_lock, StaleExecution
    from image_processor.lifecycle import (
        claim_execution, finish_report, fail_execution, reconcile, reconciliation_failed,
    )
    from image_processor.retention_paths import source_directory, output_root
    from image_processor.upload_paths import contained_upload_path
    from image_processor.models import ProcessingAttempt

    if dispatch_generation is None or dispatch_token is None:
        return {"ignored": "Missing durable dispatch identity"}
    with batch_lock(batch_id) as acquired:
        if not acquired:
            return {"ignored": "Batch busy"}
        batch = claim_execution(batch_id, dispatch_generation, dispatch_token)
        if batch is None:
            return {"ignored": "Dispatch is no longer claimable"}
        reconciling = False
        try:
            # All fallible initialization is inside terminal failure handling.
            image_settings = getattr(settings, "IMAGE_PROCESSOR_SETTINGS", {})
            output_base = output_root()
            source = source_directory(batch)
            if not source.is_dir() or str(source) != str(Path(source_folder).resolve()):
                raise FileNotFoundError("Retained source is unavailable.")
            date = validate_report_date(batch.job_options.get("date", date))
            template_path = template_path or str(image_settings.get(
                "DEFECT_IMAGE_TEMPLATE_PATH", settings.BASE_DIR / "media/templates/defect_image.docx"))
            if not Path(template_path).is_file():
                raise FileNotFoundError("Image report template is unavailable.")
            effective_mode = "named" if is_renamed_file else mode
            effective_style = dict(label_style or {})
            if is_renamed_file:
                effective_style.update(color_hex="FFFFFF", font_size_pt=14, highlight_color="red")
            _push_progress(batch, stage="PROCESSING")
            attempts = ProcessingAttempt.objects.filter(
                report__batch=batch, generation=dispatch_generation,
                dispatch_token=dispatch_token, run_token=batch.active_run_token,
                status="PROCESSING", report_id__in=batch.intended_reports,
            ).select_related("report")
            for attempt in attempts:
                report = attempt.report
                folder_label = Path(report.folder_name).name if report.folder_name != "." else "uploaded"
                name = report_filename(folder_label, date, label_type)
                relative_dir = f"{batch.pk}/{report.pk}/{attempt.pk}"
                output_directory(output_base, relative_dir)
                prepared_dir = Path(relative_dir) / "_prepared"
                output_directory(output_base, prepared_dir.as_posix())
                prepared, results = [], []
                for image in report.images.all():
                    path = contained_upload_path(source, image.relative_path)
                    out = _prepare_image(str(path), prepared_dir, output_root=output_base,
                                         dimensions=(batch.settings_snapshot["image_width_px"],
                                                     batch.settings_snapshot["image_height_px"]))
                    results.append({"image_id": image.pk, "status": "SUCCEEDED" if out else "FAILED",
                                    "stage": "PREPARED" if out else "IMAGE_PREPARATION",
                                    "failure_reason": "" if out else "Image could not be decoded or prepared."})
                    if out:
                        prepared.append(str(out))
                relative_output = ""
                if prepared:
                    translations = _translate_names([Path(p).stem for p in prepared], translation_language) \
                        if effective_mode == "translated" and use_translation else {}
                    docx_relative = f"{relative_dir}/{name}"
                    _generate_docx(template_path, folder_label, date, label_type, prepared,
                                   docx_relative, output_root=output_base, mode=effective_mode,
                                   label_style=effective_style, translations=translations)
                    relative_output = output_path(output_base, docx_relative).relative_to(
                        Path(settings.MEDIA_ROOT).resolve()).as_posix()
                finish_report(batch, attempt.pk, results, relative_output)
                _push_progress(FolderBatch.objects.get(pk=batch.pk), stage="PROCESSING")
            reconciling = True
            finished = reconcile(batch)
            _push_complete(finished)
            return {"batch_id": batch_id, "status": finished.status,
                    "processed": finished.processed_folders, "failed": finished.failed_folders}
        except StaleExecution:
            # A stale process must never attempt terminal failure writes either.
            raise
        except Exception:
            logger.exception("Image execution failed for batch %s", batch_id)
            if reconciling:
                reconciliation_failed(batch)
                raise
            try:
                fail_execution(batch)
                finished = reconcile(batch)
                _push_complete(finished)
            except StaleExecution:
                raise
            except Exception:
                reconciliation_failed(batch)
            raise
