"""On-demand conversion; the response owns the complete temporary tree."""
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from django.http import FileResponse, Http404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from image_processor.models import FolderReport
from image_processor.lifecycle import authoritative_path, invalidate_missing_authority
from image_processor.output_paths import OutputPathError
from .folder_docx_download_view import _resolve_docx_path

logger = logging.getLogger(__name__)


def validate_pdf(path):
    from pypdf import PdfReader
    with open(path, "rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise ValueError("PDF conversion produced invalid output.")
        stream.seek(0)
        reader = PdfReader(stream, strict=True)
        if not reader.pages:
            raise ValueError("PDF conversion produced no pages.")


def convert_docx_to_pdf(docx_path, pdf_path):
    # Private profile avoids collisions with another LibreOffice conversion.
    root = Path(pdf_path).parent
    result = subprocess.run([
        "libreoffice", f"-env:UserInstallation={(root / 'profile').as_uri()}",
        "--headless", "--convert-to", "pdf", "--outdir", str(root), str(docx_path),
    ], env={**os.environ, "SAL_USE_VCLPLUGIN": "svp"}, timeout=120,
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    generated = root / (Path(docx_path).stem + ".pdf")
    if result.returncode != 0 or not generated.is_file() or generated.stat().st_size < 5:
        raise ValueError("PDF conversion produced no usable output.")
    validate_pdf(generated)
    if generated != Path(pdf_path):
        generated.replace(pdf_path)


class _TempFileWrapper:
    def __init__(self, file_handle, pdf_path, temp_dir):
        self._fh, self._temp_dir = file_handle, temp_dir

    def read(self, size=-1):
        return self._fh.read(size)

    def close(self):
        try:
            self._fh.close()
        finally:
            shutil.rmtree(self._temp_dir)


class FolderPDFDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            report = FolderReport.objects.select_related("current_attempt").get(pk=pk, batch__created_by=request.user)
        except FolderReport.DoesNotExist:
            raise Http404("Report not found.")
        try:
            docx_path = authoritative_path(report)
        except (OutputPathError, OSError):
            invalidate_missing_authority(report)
            return Response({"code": "ARTIFACT_UNAVAILABLE", "detail": "No valid DOCX is available."}, status=404)
        temp_dir = tempfile.mkdtemp(prefix="image-pdf-")
        wrapped = None
        try:
            pdf_path = str(Path(temp_dir) / (docx_path.stem + ".pdf"))
            convert_docx_to_pdf(str(docx_path), pdf_path)
            validate_pdf(pdf_path)
            wrapped = _TempFileWrapper(open(pdf_path, "rb"), pdf_path, temp_dir)
            return FileResponse(wrapped, content_type="application/pdf", as_attachment=True,
                                filename=Path(pdf_path).name)
        except Exception as exc:
            if wrapped is not None:
                wrapped.close()
            else:
                shutil.rmtree(temp_dir)
            logger.warning("Image PDF conversion failed: %s", type(exc).__name__)
            return Response({"code": "PDF_CONVERSION_FAILED", "detail": "PDF conversion failed."}, status=503)
