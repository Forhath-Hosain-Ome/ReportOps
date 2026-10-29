"""Report image-quality regressions across preparation, DOCX, and PDF."""
import io
import shutil
import tempfile
import zipfile
from pathlib import Path
from unittest import skipUnless

from django.test import SimpleTestCase
from docx import Document
from PIL import Image, ImageDraw
from pypdf import PdfReader

from image_processor.tasks.process_image import _generate_docx, _prepare_image
from image_processor.views.folder_pdf_download_view import convert_docx_to_pdf


class ImageQualityTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.prepared_dir = Path("prepared")
        (self.root / self.prepared_dir).mkdir()
        self.template = self.root / "template.docx"
        document = Document()
        document.add_table(rows=1, cols=1)
        document.save(self.template)

    def source(self, name="source.jpg", size=(1200, 1600), color=(80, 120, 180)):
        path = self.root / name
        image = Image.new("RGB", size, color)
        draw = ImageDraw.Draw(image)
        for offset in range(0, min(size), 12):
            draw.line((0, offset, size[0] - 1, offset), fill=(240, 220, 40), width=2)
        image.save(path, "JPEG", quality=95)
        return path

    def prepare(self, source, dimensions=(80, 60)):
        return _prepare_image(
            str(source), self.prepared_dir, output_root=self.root, dimensions=dimensions,
        )

    def make_docx(self, prepared, name="report.docx"):
        _generate_docx(
            str(self.template), "Sample", "2026-10-29", "Defect Fabric",
            [str(path) for path in prepared], name, output_root=self.root,
        )
        return self.root / name

    def test_high_resolution_is_not_thumbnailized_and_low_resolution_is_not_upscaled(self):
        high = self.source()
        high_prepared = self.prepare(high)
        with Image.open(high_prepared) as image:
            self.assertEqual(image.size, (1200, 1600))
            self.assertAlmostEqual(image.width / image.height, 0.75, places=3)
        self.assertEqual(high.read_bytes(), high_prepared.read_bytes())

        low = self.source("low.jpg", (80, 60))
        low_prepared = self.prepare(low, dimensions=(4096, 4096))
        with Image.open(low_prepared) as image:
            self.assertEqual(image.size, (80, 60))

    def test_docx_embeds_useful_raster_with_fixed_report_layout(self):
        prepared = self.prepare(self.source())
        docx_path = self.make_docx([prepared])
        with zipfile.ZipFile(docx_path) as archive:
            payload = archive.read("word/media/image1.jpg")
        with Image.open(io.BytesIO(payload)) as embedded:
            self.assertEqual(embedded.size, (1200, 1600))
            self.assertGreaterEqual(max(embedded.size), 1200)

        shape = Document(docx_path).inline_shapes[0]
        self.assertAlmostEqual(shape.width.inches, 4.51, places=2)
        self.assertAlmostEqual(shape.height.inches, 3.68, places=2)

    @skipUnless(shutil.which("libreoffice"), "LibreOffice is required for raster-preservation verification")
    def test_libreoffice_pdf_keeps_useful_raster_resolution(self):
        prepared = self.prepare(self.source())
        docx_path = self.make_docx([prepared])
        pdf_path = self.root / "report.pdf"
        convert_docx_to_pdf(docx_path, pdf_path)
        images = [entry for page in PdfReader(pdf_path).pages for entry in page.images]
        self.assertTrue(images)
        with Image.open(io.BytesIO(max(images, key=lambda entry: len(entry.data)).data)) as embedded:
            self.assertGreaterEqual(embedded.width, 700)
            self.assertGreaterEqual(embedded.height, 900)
            self.assertAlmostEqual(embedded.width / embedded.height, 0.75, places=2)

    def test_multi_image_docx_file_size_growth_is_bounded(self):
        sources = [
            self.source(f"source-{index}.jpg", color=(40 + index * 20, 90, 160))
            for index in range(6)
        ]
        prepared = [self.prepare(source) for source in sources]
        docx_path = self.make_docx(prepared)
        source_bytes = sum(source.stat().st_size for source in sources)
        self.assertLessEqual(docx_path.stat().st_size, int(source_bytes * 1.10) + 500_000)
