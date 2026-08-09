"""Docling wrapper: parse PDF/HTML/DOCX into a DoclingDocument with provenance."""

from functools import lru_cache
from io import BytesIO
from pathlib import Path

from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.settings import settings as docling_settings
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DocItemLabel, DoclingDocument

from app.config import settings
from ingestion.html_clean import MIN_YIELD, clean_html, text_projection, visible_text

SUPPORTED_SUFFIXES = {".pdf", ".html", ".docx"}


@lru_cache(maxsize=1)
def _converter() -> DocumentConverter:
    # 100+ page PDFs OOM the container on the defaults (4-page batches,
    # unbounded threads): keep the memory peak low instead.
    docling_settings.perf.page_batch_size = 1
    pdf_options = PdfPipelineOptions()
    pdf_options.do_ocr = settings.ingest_ocr
    pdf_options.do_table_structure = True
    pdf_options.accelerator_options = AcceleratorOptions(num_threads=4, device="cpu")
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options)}
    )


def parse_document(path: Path) -> DoclingDocument:
    if path.suffix.lower() in {".html", ".htm"}:
        return _parse_html(path)
    return _converter().convert(path).document


def _parse_html(path: Path) -> DoclingDocument:
    cleaned = clean_html(path.read_text(encoding="utf-8", errors="ignore"))
    reference = visible_text(cleaned)
    doc = _convert_html_string(cleaned, path.stem)
    # Markup Docling cannot traverse yields a nearly empty document even though
    # the page has visible text: index the text projection instead.
    if len(reference) > 200 and len(doc.export_to_markdown()) < MIN_YIELD * len(
        reference
    ):
        doc = _convert_html_string(text_projection(cleaned), path.stem)
    return doc


def _convert_html_string(html: str, stem: str) -> DoclingDocument:
    stream = DocumentStream(name=f"{stem}.html", stream=BytesIO(html.encode("utf-8")))
    return _converter().convert(stream).document


def document_title(doc: DoclingDocument) -> str | None:
    for item, _level in doc.iterate_items():
        if getattr(item, "label", None) in (
            DocItemLabel.TITLE,
            DocItemLabel.SECTION_HEADER,
        ):
            text = (getattr(item, "text", "") or "").strip()
            if text:
                return text[:200]
    return None
